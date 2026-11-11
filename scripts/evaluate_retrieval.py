"""Measure retrieval relevance and local search latency through the FastAPI API."""

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "eval" / "retrieval_cases.jsonl"


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(quantile * len(ordered)) - 1)], 2)


def evaluate(base_url: str, tenant_id: str, limit: int, repeats: int) -> dict:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    latencies_ms: list[float] = []
    details = []

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=60, trust_env=False) as client:
        for case in cases:
            relevant = {
                (item["filename"].casefold(), (item.get("section") or "").casefold())
                for item in case["expected_relevant"]
            }
            first_hits = None
            first_rank = None
            retrieved_relevant: set[tuple[str, str]] = set()
            for repeat in range(repeats):
                started = perf_counter()
                response = client.post(
                    "/knowledge/search",
                    json={"tenant_id": tenant_id, "query": case["query"], "limit": limit},
                )
                latency = (perf_counter() - started) * 1000
                latencies_ms.append(latency)
                if response.is_error:
                    try:
                        detail = response.json().get("detail", response.text)
                    except ValueError:
                        detail = response.text
                    raise RuntimeError(f"Search API returned HTTP {response.status_code}: {detail}")
                if repeat == 0:
                    first_hits = response.json().get("hits", [])
                    for rank, hit in enumerate(first_hits, start=1):
                        key = (hit["filename"].casefold(), (hit.get("section") or "").casefold())
                        if key in relevant:
                            retrieved_relevant.add(key)
                            if first_rank is None:
                                first_rank = rank

            recall = len(retrieved_relevant) / len(relevant) if relevant else 0.0
            reciprocal_rank = 1 / first_rank if first_rank is not None else 0.0
            recalls.append(recall)
            reciprocal_ranks.append(reciprocal_rank)
            details.append({
                "id": case["id"],
                "recall_at_k": round(recall, 4),
                "reciprocal_rank": round(reciprocal_rank, 4),
                "top_hits": [
                    {"filename": hit["filename"], "section": hit.get("section"), "score": hit["score"]}
                    for hit in (first_hits or [])
                ],
            })

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_base_url": base_url.rstrip("/"),
        "dataset": "data/eval/retrieval_cases.jsonl",
        "dataset_cases": len(cases),
        "tenant_id": tenant_id,
        "k": limit,
        "repeats_per_query": repeats,
        "metrics": {
            f"recall_at_{limit}": round(sum(recalls) / len(recalls), 4),
            "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4),
        },
        "search_latency_ms": {
            "sample_count": len(latencies_ms),
            "p50": percentile(latencies_ms, 0.50),
            "p95": percentile(latencies_ms, 0.95),
            "mean": round(sum(latencies_ms) / len(latencies_ms), 2),
            "scope": "POST /knowledge/search; excludes answer generation and UI rendering",
        },
        "cases": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant-id", default="demo")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if not 1 <= args.k <= 10:
        parser.error("--k must be between 1 and 10")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    report = evaluate(args.base_url, args.tenant_id, args.k, args.repeats)
    serialized = json.dumps(report, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
