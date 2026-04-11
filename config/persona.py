PERSONA_CONFIG = {
    "niche": "Personal finance for international students in NYC",
    "tone": "helpful, empowering, informative",
    "expertise_level": "peer-to-peer",
    "content_goal": "help international students navigate US financial systems and surface practical money resources",
    "audience": {
        "primary": "International students aged 18-30 living in NYC",
        "pain_points": [
            "opening a US bank account without SSN",
            "understanding W-2 with multiple employers or states",
            "filing taxes as F1/J1 nonresident alien",
            "finding loans and scholarships as an international student",
            "building US credit history from zero",
            "sending money home affordably",
        ],
        "platforms": ["LinkedIn", "Instagram"],
    },
    "topics": {
        "core": [
            "international student banking NYC",
            "F1 J1 visa taxes W-2",
            "scholarships financial aid international students",
            "OPT CPT income tax",
            "credit history international student",
        ],
        "adjacent": [
            "ITIN nonresident alien",
            "remittances NYC",
            "NYC cost of living",
            "international student loans Prodigy SoFi Earnest MPOWER",
            "financial aid CUNY NYC universities",
        ],
        "excluded": ["entertainment", "sports", "unrelated NYC news"],
        "weights": {
            "international student banking": 0.30,
            "international student taxes W-2": 0.25,
            "scholarships financial aid": 0.20,
            "OPT CPT income tax": 0.10,
            "NYC cost of living": 0.15,
        },
    },
    "retrieval_directives": {
        "recency_bias": 0.7,
        "source_priority": ["grounded_search", "articles", "nyc_open_data", "events"],
        "min_relevance_score": 0.55,
        "top_k": 5,
    },
}


def get_strategy_pack() -> dict:
    return PERSONA_CONFIG
