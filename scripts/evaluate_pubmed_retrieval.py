from __future__ import annotations

import json
from pathlib import Path

from tools.pubmed_search import search_pubmed


def precision_at_k(results: list[dict], expected_terms: list[str], k: int = 5) -> float:
    top = results[:k]
    if not top:
        return 0.0
    hits = 0
    expected = [t.lower() for t in expected_terms]
    for item in top:
        text = f"{item.get('title','')} {item.get('abstract','')}".lower()
        if any(term in text for term in expected):
            hits += 1
    return hits / len(top)


def citation_usefulness_score(results: list[dict], k: int = 5) -> float:
    top = results[:k]
    if not top:
        return 0.0
    return sum(float(x.get("score", 0.0)) for x in top) / len(top)


def main() -> int:
    path = Path("data/pubmed_benchmark.jsonl")
    if not path.exists():
        print("Benchmark file not found")
        return 1

    p5_scores = []
    cus_scores = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        queries = [{
            "topic": case["topic"],
            "population": case["population"],
            "context": case["context"],
            "expected_link": case.get("question", ""),
        }]
        results = search_pubmed(queries)
        p5 = precision_at_k(results, case.get("expected_terms", []), k=5)
        cus = citation_usefulness_score(results, k=5)
        p5_scores.append(p5)
        cus_scores.append(cus)
        print(f"{case['id']}: precision@5={p5:.2f} usefulness={cus:.3f} n={len(results)}")

    print("---")
    print(f"Mean precision@5: {sum(p5_scores)/max(1,len(p5_scores)):.3f}")
    print(f"Mean citation usefulness: {sum(cus_scores)/max(1,len(cus_scores)):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
