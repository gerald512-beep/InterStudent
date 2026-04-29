"""
Integration test for Agent 1.
Run with: python tests/test_agent1.py

Saves output to tests/mock_retrieval_pack.json for Dev 2 to use.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent1_source_retrieval import retrieve

TEST_QUERY = "housing costs for international students NYC"

if __name__ == "__main__":
    print(f"\n[test] Running Agent 1 with query: '{TEST_QUERY}'\n")

    result = retrieve(TEST_QUERY)

    print(f"\n[test] Results returned: {len(result['results'])}")
    for r in result["results"]:
        print(f"  - [{r['relevance_score']}] {r['title']} ({r['source_type']})")

    assert len(result["results"]) >= 1, "Expected at least 1 result"

    out_path = os.path.join(os.path.dirname(__file__), "mock_retrieval_pack.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[test] mock_retrieval_pack.json saved to: {out_path}")
    print("[test] PASS — Agent 1 is ready. Share mock_retrieval_pack.json with Dev 2.")
