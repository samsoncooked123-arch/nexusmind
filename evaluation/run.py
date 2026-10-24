"""Small API smoke evaluation. Review answers and opened passages manually as well."""
import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    cases = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.api, timeout=120) as client:
        for case in cases:
            if case["type"] in {"scanned_pdf", "duplicate_upload", "contradictory_documents", "ambiguous_name"}:
                print(f"MANUAL {case['type']}: {case['expected']}")
                continue
            try:
                response = client.post("/ask", json={"question": case["question"]})
                response.raise_for_status()
                answer = response.json()
            except httpx.HTTPError as exc:
                print(f"ERROR {case['type']}: {case['question']} — {exc}")
                continue
            source_ids = [source["chunk_id"] for source in answer["sources"]]
            edge_ids = [edge["id"] for edge in answer["graph_path"]["edges"]]
            if case["type"] == "missing_answer":
                expectation_met = answer["insufficient_evidence"]
            elif case["type"] == "topics":
                expectation_met = bool(answer.get("topics"))
            else:
                expectation_met = case["expected"].lower() in answer["answer"].lower()
            print(f"{'PASS' if expectation_met else 'REVIEW'} {case['type']}: {case['question']}")
            print(f"  route={answer['route']} sources={source_ids} edges={edge_ids}")
            print(f"  answer={answer['answer']}")


if __name__ == "__main__":
    main()
