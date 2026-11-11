"""Local Streamlit console for the SupportPilot API."""

from __future__ import annotations

from typing import Any

import streamlit as st

from api_client import ApiError, request_json


st.set_page_config(page_title="SupportPilot AI", page_icon="🛟", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 2rem;}
      .hero {padding: 1.4rem 1.6rem; border-radius: 18px; background: linear-gradient(120deg,#102a43,#175c77); color: white; margin-bottom: 1rem;}
      .hero h1 {margin: 0; font-size: 2rem;}
      .hero p {margin: .45rem 0 0; color: #d8edf5;}
      [data-testid="stMetric"] {background: #f5f8fb; padding: 12px 16px; border-radius: 12px;}
    </style>
    <div class="hero"><h1>SupportPilot AI</h1>
    <p>Local support workflow console · knowledge answers · synthetic lookups · human review</p></div>
    """,
    unsafe_allow_html=True,
)

for key, default in (("last_support_result", None), ("last_workflow_status", None), ("documents", None)):
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.subheader("Connection")
    api_base_url = st.text_input("FastAPI URL", "http://127.0.0.1:8000").strip().rstrip("/")
    tenant_id = st.text_input("Tenant ID", "demo").strip() or "demo"
    st.caption("Demo tenant only. Authentication is not enabled.")
    if st.button("Check API", use_container_width=True):
        try:
            health = request_json(api_base_url, "GET", "/health/ready", timeout=5)
            st.success(f"API ready · database {health.get('database', 'unknown')}")
        except ApiError as exc:
            st.error(str(exc))
    st.divider()
    st.caption("Gemini credentials stay on the API server; they are never sent to this UI.")


def show_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    st.markdown("#### Sources")
    for number, citation in enumerate(citations, 1):
        label = citation.get("filename", "Source")
        location = " · ".join(
            str(item) for item in (
                citation.get("section"),
                f"page {citation['page_number']}" if citation.get("page_number") else None,
            ) if item
        )
        with st.expander(f"{number}. {label}" + (f" — {location}" if location else "")):
            st.write(citation.get("text", ""))
            st.caption(f"Score {citation.get('score', 0):.3f} · Chunk {citation.get('chunk_id', 'n/a')}")


def show_run_result(result: dict[str, Any]) -> None:
    status = result.get("status", "unknown")
    if status in {"answered", "approved"}:
        st.success(f"Workflow status: {status}")
    elif status in {"approval_pending", "needs_input", "record_not_found"}:
        st.warning(f"Workflow status: {status}")
    else:
        st.info(f"Workflow status: {status}")
    first, second = st.columns(2)
    first.metric("Intent", result.get("intent", "unknown"))
    second.metric("Priority", result.get("priority", "unknown"))
    st.markdown("#### Suggested response")
    st.write(result.get("answer") or "No response draft was generated.")
    if result.get("rationale"):
        st.caption(result["rationale"])
    if result.get("workflow_id"):
        st.code(f"Workflow ID: {result['workflow_id']}", language=None)
    if result.get("approval_id"):
        st.caption(f"Approval ID: {result['approval_id']}")
    if result.get("review"):
        with st.expander("Human review context"):
            st.json(result["review"])
    show_citations(result.get("citations", []))
    if result.get("events"):
        with st.expander("Agent activity"):
            for event in result["events"]:
                st.markdown(f"- {event}")


ask_tab, records_tab, approvals_tab, docs_tab = st.tabs(
    ["Ask SupportPilot", "Orders & Tickets", "Human Review", "Knowledge Documents"]
)

with ask_tab:
    st.subheader("Run a support request")
    st.write("Ask a policy or product question, report an issue, or request a record lookup.")
    with st.form("support_request"):
        message = st.text_area("Customer message", placeholder="What if my item arrived damaged?", height=105)
        left, middle, right = st.columns(3)
        order_id = left.text_input("Order number (optional)", placeholder="ORD-1001")
        ticket_id = middle.text_input("Ticket number (optional)", placeholder="TKT-2001")
        limit = right.number_input("Evidence limit", 1, 10, 5)
        submitted = st.form_submit_button("Run support workflow", type="primary", use_container_width=True)
    if submitted:
        if not message.strip():
            st.warning("Enter a customer message first.")
        else:
            body = {"tenant_id": tenant_id, "message": message.strip(), "limit": int(limit)}
            if order_id.strip():
                body["order_id"] = order_id.strip()
            if ticket_id.strip():
                body["ticket_id"] = ticket_id.strip()
            with st.spinner("Running the support workflow…"):
                try:
                    st.session_state.last_support_result = request_json(
                        api_base_url, "POST", "/agent/run", json=body, timeout=120
                    )
                except ApiError as exc:
                    st.error(str(exc))
    if st.session_state.last_support_result:
        st.divider()
        show_run_result(st.session_state.last_support_result)

with records_tab:
    st.subheader("Synthetic record lookups")
    st.write("These exact-ID lookups use the demo tenant and do not change records.")
    order_col, ticket_col = st.columns(2)
    with order_col, st.form("order_lookup"):
        st.markdown("#### Order status")
        order_lookup_id = st.text_input("Order ID", "ORD-1001")
        order_submit = st.form_submit_button("Look up order", use_container_width=True)
    with ticket_col, st.form("ticket_lookup"):
        st.markdown("#### Ticket status")
        ticket_lookup_id = st.text_input("Ticket ID", "TKT-2001")
        ticket_submit = st.form_submit_button("Look up ticket", use_container_width=True)
    if order_submit or ticket_submit:
        is_order = order_submit
        identifier = order_lookup_id.strip() if is_order else ticket_lookup_id.strip()
        if not identifier:
            st.warning("Enter a record ID.")
        else:
            body = {"tenant_id": tenant_id, "message": "Where is my order?" if is_order else "Check my ticket"}
            body["order_id" if is_order else "ticket_id"] = identifier
            try:
                st.session_state.last_support_result = request_json(
                    api_base_url, "POST", "/agent/run", json=body, timeout=60
                )
            except ApiError as exc:
                st.error(str(exc))
    last = st.session_state.last_support_result or {}
    if last.get("route") in {"order_lookup", "ticket_lookup"}:
        show_run_result(last)

with approvals_tab:
    st.subheader("Human review queue")
    last = st.session_state.last_support_result or {}
    pending_id = last.get("workflow_id", "") if last.get("status") == "approval_pending" else ""
    if pending_id and not st.session_state.get("approval_workflow_id"):
        st.session_state.approval_workflow_id = pending_id
    workflow_id = st.text_input("Workflow ID", key="approval_workflow_id", placeholder="Paste a workflow ID")
    if st.button("Load workflow"):
        if not workflow_id.strip():
            st.warning("Enter a workflow ID or first create a sensitive request in Ask SupportPilot.")
        else:
            try:
                st.session_state.last_workflow_status = request_json(
                    api_base_url, "GET", f"/agent/{workflow_id.strip()}", params={"tenant_id": tenant_id}
                )
            except ApiError as exc:
                st.error(str(exc))
    workflow = st.session_state.last_workflow_status
    if workflow:
        st.write(f"Status: **{workflow.get('status')}** · approval: **{workflow.get('approval_status')}**")
        state = workflow.get("state", {})
        review = state.get("review", {})
        if review:
            st.warning(review.get("message", "This workflow needs review."))
            st.markdown("**Customer message**")
            st.write(review.get("customer_message", ""))
            st.markdown("**Draft for review**")
            st.write(review.get("draft_answer", ""))
        if workflow.get("approval_status") == "pending":
            edited = st.text_area(
                "Approved reply draft (editable)",
                value=review.get("draft_answer", "A support specialist will review and follow up."),
                key=f"edited_reply_{workflow['workflow_id']}",
                height=120,
            )
            note = st.text_input("Reviewer note (optional)")
            approve_col, reject_col = st.columns(2)
            approve = approve_col.button("Approve draft", type="primary", use_container_width=True)
            reject = reject_col.button("Reject · send to triage", use_container_width=True)
            if approve or reject:
                body = {"tenant_id": tenant_id, "decision": "approve" if approve else "reject", "decision_note": note}
                if approve:
                    body["edited_answer"] = edited
                try:
                    decision_result = request_json(
                        api_base_url, "POST", f"/agent/{workflow['workflow_id']}/decision", json=body, timeout=60
                    )
                    st.success(f"Decision recorded: {decision_result['status']}. This UI does not send messages.")
                    st.session_state.last_support_result = decision_result
                    st.session_state.last_workflow_status = None
                except ApiError as exc:
                    st.error(str(exc))
        elif workflow.get("approval_status"):
            st.info(f"This approval is already {workflow['approval_status']}.")

with docs_tab:
    st.subheader("Knowledge base")
    st.write("Upload a synthetic FAQ, policy, or manual. Supported formats: PDF, Markdown, and UTF-8 text.")
    uploaded = st.file_uploader("Choose a support document", type=["pdf", "md", "txt"])
    if uploaded and st.button("Upload and index document", type="primary"):
        with st.spinner("Extracting, embedding, and indexing…"):
            try:
                document = request_json(
                    api_base_url,
                    "POST",
                    "/documents/upload",
                    data={"tenant_id": tenant_id},
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")},
                    timeout=180,
                )
                st.success(f"Indexed {document['filename']} · {document['chunk_count']} chunks · {document['status']}")
                st.session_state.documents = None
            except ApiError as exc:
                st.error(str(exc))
    if st.button("Refresh documents"):
        st.session_state.documents = None
    if st.session_state.documents is None:
        try:
            st.session_state.documents = request_json(
                api_base_url, "GET", "/documents", params={"tenant_id": tenant_id}, timeout=10
            )
        except ApiError:
            st.session_state.documents = []
    if st.session_state.documents:
        st.dataframe(
            [
                {
                    "filename": item["filename"],
                    "status": item["status"],
                    "chunks": item["chunk_count"],
                    "version": item["version"],
                    "active": item["is_active"],
                    "created": item["created_at"],
                }
                for item in st.session_state.documents
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No indexed documents were returned for this tenant yet.")

st.divider()
st.caption("SupportPilot AI · local portfolio demo · synthetic records only · no automatic customer actions")
