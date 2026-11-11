import json
from pathlib import Path

from app.agent.classification import classify_message
from scripts.evaluate_agent import evaluate as evaluate_agent
from scripts import evaluate_retrieval


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_agent_evaluation_dataset_has_unique_ids_and_expected_labels():
    cases = read_jsonl(ROOT / "data" / "eval" / "agent_cases.jsonl")
    ids = [case["id"] for case in cases]
    assert len(ids) >= 10
    assert len(ids) == len(set(ids))
    for case in cases:
        result = classify_message(case["message"])
        assert result.intent == case["expected_intent"], case["id"]
        assert result.priority == case["expected_priority"], case["id"]
        assert result.route == case["expected_route"], case["id"]


def test_retrieval_evaluation_dataset_has_at_least_one_relevant_target():
    cases = read_jsonl(ROOT / "data" / "eval" / "retrieval_cases.jsonl")
    assert len(cases) >= 3
    for case in cases:
        assert case["query"].strip()
        assert case["expected_relevant"]
        assert all(item.get("filename") for item in case["expected_relevant"])


def test_offline_agent_evaluator_reports_perfect_curated_routing():
    report = evaluate_agent()
    assert report["cases"] == 19
    assert report["passed"] is True
    assert all(score == 1.0 for score in report["metrics"].values())


def test_retrieval_evaluator_reports_relevance_and_latency_without_network(monkeypatch):
    class FakeResponse:
        is_error = False

        def __init__(self, section):
            self.section = section

        def json(self):
            return {"hits": [
                {"filename": "return_policy.md", "section": self.section, "score": 0.9},
                {"filename": "other.md", "section": None, "score": 0.3},
            ]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            query = kwargs["json"]["query"].casefold()
            if "damaged" in query:
                section = "Damaged items"
            elif "refund" in query:
                section = "Refund timing"
            else:
                section = "Returns and refunds"
            return FakeResponse(section)

    monkeypatch.setattr(evaluate_retrieval.httpx, "Client", FakeClient)
    report = evaluate_retrieval.evaluate("http://example.invalid", "demo", 2, 2)
    assert report["metrics"]["recall_at_2"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["search_latency_ms"]["sample_count"] == 6
