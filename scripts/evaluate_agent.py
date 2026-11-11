"""Evaluate deterministic routing and in-memory graph behavior on labeled cases."""

import argparse
import json
import platform
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
from time import perf_counter

from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.workflow import build_support_graph, initial_state


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "eval" / "agent_cases.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def _tool(name: str, counters: dict[str, int], result: str) -> StructuredTool:
    def invoke(tenant_id: str, external_id: str | None = None, query: str | None = None,
               limit: int = 5) -> str:
        counters[name] += 1
        return result

    return StructuredTool.from_function(func=invoke, name=name, description=f"Evaluation stub for {name}.")


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile * len(ordered) + 0.999999)) - 1))
    return round(ordered[index], 3)


def evaluate(cases: list[dict] | None = None) -> dict:
    cases = cases or load_cases()
    scores = {
        "intent": 0,
        "priority": 0,
        "route": 0,
        "tool_selection": 0,
        "status": 0,
        "human_review": 0,
    }
    latencies_ms: list[float] = []
    failures = []

    for index, case in enumerate(cases):
        counters = {"search_knowledge_base": 0, "lookup_mock_order": 0, "lookup_mock_ticket": 0}
        search_tool = _tool("search_knowledge_base", counters, "[]")
        order_tool = _tool("lookup_mock_order", counters, '{"found":false}')
        ticket_tool = _tool("lookup_mock_ticket", counters, '{"found":false}')
        graph = build_support_graph(
            search_tool,
            lambda: None,
            order_tool,
            ticket_tool,
            checkpointer=InMemorySaver(),
        )
        state = initial_state(
            tenant_id="evaluation",
            message=case["message"],
            order_id=case.get("order_id"),
            ticket_id=case.get("ticket_id"),
            limit=5,
        )
        started = perf_counter()
        result = graph.invoke(state, {"configurable": {"thread_id": f"eval-{index}"}})
        latencies_ms.append((perf_counter() - started) * 1000)

        interrupted = bool(result.get("__interrupt__"))
        actual_status = "approval_pending" if interrupted else result["status"]
        actual_tools = [name for name, count in counters.items() if count]
        actual_tool = actual_tools[0] if len(actual_tools) == 1 else None
        actual = {
            "intent": result["intent"],
            "priority": result["priority"],
            "route": result["route"],
            "tool_selection": actual_tool,
            "status": actual_status,
            "human_review": interrupted,
        }
        expected = {
            "intent": case["expected_intent"],
            "priority": case["expected_priority"],
            "route": case["expected_route"],
            "tool_selection": case["expected_tool"],
            "status": case["expected_status"],
            "human_review": case["expected_human_review"],
        }
        for metric in scores:
            matched = actual[metric] == expected[metric]
            scores[metric] += int(matched)
            if not matched:
                failures.append({"id": case["id"], "metric": metric,
                                 "expected": expected[metric], "actual": actual[metric]})

    total = len(cases)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "data/eval/agent_cases.jsonl",
        "runtime": {
            "python": platform.python_version(),
            "langgraph": version("langgraph"),
        },
        "cases": total,
        "metrics": {f"{name}_accuracy": round(value / total, 4) for name, value in scores.items()},
        "workflow_latency_ms": {
            "p50": _percentile(latencies_ms, 0.50),
            "p95": _percentile(latencies_ms, 0.95),
            "scope": "single-process graph invocation with stub tools, InMemorySaver, no DB, Qdrant, or LLM",
        },
        "passed": not failures,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    report = evaluate()
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
