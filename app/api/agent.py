import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.checkpointer import get_checkpointer
from app.agent.workflow import build_support_graph, initial_state
from app.db.models import ApprovalRequest, WorkflowExecution
from app.db.session import get_db
from app.embeddings.provider import Embedder, EmbeddingProviderError, get_embedder
from app.llm.gemini_provider import get_answer_provider
from app.llm.provider import AnswerProviderError
from app.rag.qdrant_store import QdrantVectorStore, VectorStoreError, get_vector_store
from app.schemas.agent import (
    AgentRequest,
    AgentResponse,
    ApprovalDecisionRequest,
    WorkflowStatusResponse,
)
from app.tools.knowledge import build_knowledge_search_tool
from app.tools.support_records import build_order_lookup_tool, build_ticket_lookup_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["support agent"])


def _graph(
    db: Session,
    embedder: Embedder,
    vector_store: QdrantVectorStore,
    checkpointer: BaseCheckpointSaver,
):
    return build_support_graph(
        build_knowledge_search_tool(db, embedder, vector_store),
        get_answer_provider,
        build_order_lookup_tool(db),
        build_ticket_lookup_tool(db),
        checkpointer=checkpointer,
    )


def _state_for_storage(state: dict) -> dict:
    """Persist only public workflow fields needed to inspect and resume a run."""
    keys = (
        "tenant_id", "message", "intent", "priority", "rationale", "route", "status",
        "next_action", "answer", "citations", "events", "order_id", "ticket_id",
    )
    return {key: state[key] for key in keys if key in state}


def _response(state: dict, workflow_id: UUID, approval_id: UUID | None = None, **overrides) -> AgentResponse:
    body = _state_for_storage(state)
    body.update(overrides)
    body["workflow_id"] = workflow_id
    body["approval_id"] = approval_id
    return AgentResponse.model_validate(body)


def _mark_failed(db: Session, workflow_id: UUID, exc: Exception) -> None:
    try:
        db.rollback()
        workflow = db.get(WorkflowExecution, workflow_id)
        if workflow is not None:
            workflow.status = "failed"
            workflow.current_node = None
            workflow.error_code = type(exc).__name__[:80]
            db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("could not persist failed workflow status")


def _raise_dependency_error(exc: Exception) -> None:
    if isinstance(exc, VectorStoreError):
        raise HTTPException(status_code=503, detail="Knowledge search is temporarily unavailable") from exc
    if isinstance(exc, EmbeddingProviderError):
        raise HTTPException(status_code=503, detail="The embedding model is temporarily unavailable") from exc
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(status_code=503, detail="Support data is temporarily unavailable") from exc
    if isinstance(exc, AnswerProviderError):
        raise HTTPException(status_code=503, detail="The answer provider is temporarily unavailable") from exc
    logger.error("support workflow failed", exc_info=(type(exc), exc, exc.__traceback__))
    raise HTTPException(status_code=500, detail="The support workflow could not be completed") from exc


@router.post("/run", response_model=AgentResponse)
def run_support_agent(
    request: AgentRequest,
    http_request: Request,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
    checkpointer: Annotated[BaseCheckpointSaver, Depends(get_checkpointer)],
) -> AgentResponse:
    workflow_id = uuid4()
    state = initial_state(
        tenant_id=request.tenant_id,
        message=request.message,
        order_id=request.order_id,
        ticket_id=request.ticket_id,
        limit=request.limit,
    )
    workflow = WorkflowExecution(
        id=workflow_id,
        tenant_id=request.tenant_id,
        status="running",
        correlation_id=http_request.state.correlation_id,
        current_node="classify",
        state_json=_state_for_storage(state),
    )
    db.add(workflow)
    try:
        db.commit()
        graph = _graph(db, embedder, vector_store, checkpointer)
        result = graph.invoke(state, {"configurable": {"thread_id": str(workflow_id)}})
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_value = interrupts[0].value
            approval = ApprovalRequest(
                id=uuid4(),
                tenant_id=request.tenant_id,
                workflow_id=workflow_id,
                status="pending",
                reason=interrupt_value["message"],
            )
            db.add(approval)
            workflow.status = "waiting_approval"
            workflow.current_node = "human_review"
            workflow.state_json = _state_for_storage(result)
            workflow.state_json.update({
                "status": "approval_pending",
                "next_action": "human_review",
                "answer": "This request is waiting for human review. No reply has been sent.",
                "events": workflow.state_json.get("events", []) + [
                    "Paused for human review before drafting or sending a reply."
                ],
                "review": interrupt_value,
            })
            db.commit()
            return _response(
                result,
                workflow_id,
                approval.id,
                status="approval_pending",
                answer="This request is waiting for human review. No reply has been sent.",
                next_action="human_review",
                review=interrupt_value,
            )

        workflow.status = result["status"]
        workflow.current_node = None
        workflow.state_json = _state_for_storage(result)
        db.commit()
        return _response(result, workflow_id)
    except Exception as exc:
        _mark_failed(db, workflow_id, exc)
        _raise_dependency_error(exc)


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
def get_workflow_status(
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: str = Query(default="demo", min_length=1, max_length=100),
) -> WorkflowStatusResponse:
    workflow = db.scalar(select(WorkflowExecution).where(
        WorkflowExecution.id == workflow_id,
        WorkflowExecution.tenant_id == tenant_id,
    ))
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    approval = db.scalar(select(ApprovalRequest).where(
        ApprovalRequest.workflow_id == workflow_id,
        ApprovalRequest.tenant_id == tenant_id,
    ))
    return WorkflowStatusResponse(
        workflow_id=workflow.id,
        tenant_id=workflow.tenant_id,
        status="approval_pending" if workflow.status == "waiting_approval" else workflow.status,
        current_node=workflow.current_node,
        correlation_id=workflow.correlation_id,
        state=workflow.state_json,
        approval_id=approval.id if approval else None,
        approval_status=approval.status if approval else None,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.post("/{workflow_id}/decision", response_model=AgentResponse)
def decide_human_review(
    workflow_id: UUID,
    decision: ApprovalDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    vector_store: Annotated[QdrantVectorStore, Depends(get_vector_store)],
    checkpointer: Annotated[BaseCheckpointSaver, Depends(get_checkpointer)],
) -> AgentResponse:
    workflow = db.scalar(select(WorkflowExecution).where(
        WorkflowExecution.id == workflow_id,
        WorkflowExecution.tenant_id == decision.tenant_id,
    ))
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    approval = db.scalar(select(ApprovalRequest).where(
        ApprovalRequest.workflow_id == workflow_id,
        ApprovalRequest.tenant_id == decision.tenant_id,
    ).with_for_update())
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="This approval request has already been decided")

    try:
        graph = _graph(db, embedder, vector_store, checkpointer)
        result = graph.invoke(
            Command(resume={
                "decision": decision.decision,
                "edited_answer": decision.edited_answer,
            }),
            {"configurable": {"thread_id": str(workflow_id)}},
        )
        if result.get("__interrupt__"):
            raise RuntimeError("Workflow paused again before completing the human decision")
        approval.status = "approved" if decision.decision == "approve" else "rejected"
        approval.decision_note = decision.decision_note
        approval.decided_at = datetime.now(timezone.utc)
        workflow.status = result["status"]
        workflow.current_node = None
        workflow.state_json = _state_for_storage(result)
        db.commit()
        return _response(result, workflow_id, approval.id)
    except Exception as exc:
        db.rollback()
        _raise_dependency_error(exc)
