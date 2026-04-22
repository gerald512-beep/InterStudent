"""
Pipeline entry point.
Runs Agent 1. Agent 2 + output layer are implemented by Dev 2.
"""
import json
from agents.agent1_source_retrieval import retrieve

DEFAULT_QUERY = "housing costs for international students NYC"


def run_pipeline(query: str = DEFAULT_QUERY) -> dict:
    print(f"\n=== Agent 1: Source Retrieval ===")
    retrieval_pack = retrieve(query)
    print(f"Retrieved {len(retrieval_pack['results'])} results for: '{query}'")

    # --- Dev 2 hooks in here ---
    # from agents.agent2_content_generator import run_agent2
    # from output.creative_storyteller import generate_output
    # content_draft = run_agent2(retrieval_pack)
    # final_output = generate_output(content_draft)

    return retrieval_pack


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2, ensure_ascii=False))
