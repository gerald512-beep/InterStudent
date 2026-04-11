PERSONA_CONFIG = {
    "niche": "International students in NYC",
    "tone": "helpful, empowering, informative",
    "expertise_level": "peer-to-peer",
    "content_goal": "surface inequities and share practical resources",
    "audience": {
        "primary": "International students aged 18-30 living in NYC",
        "pain_points": [
            "finding affordable housing",
            "understanding visa work restrictions",
            "navigating CUNY/university bureaucracy",
            "cost of living shock",
            "isolation and community building",
        ],
        "platforms": ["LinkedIn", "Instagram"],
    },
    "topics": {
        "core": [
            "international students NYC",
            "student visa",
            "CUNY",
            "NYC housing students",
            "OPT CPT",
        ],
        "adjacent": [
            "NYC cost of living",
            "student jobs NYC",
            "immigration policy NYC",
            "affordable neighborhoods NYC",
        ],
        "excluded": ["entertainment", "sports", "unrelated NYC news"],
        "weights": {
            "international students NYC": 0.35,
            "student visa": 0.25,
            "NYC housing students": 0.20,
            "OPT CPT": 0.10,
            "NYC cost of living": 0.10,
        },
    },
    "retrieval_directives": {
        "recency_bias": 0.7,
        "source_priority": ["nyc_open_data", "articles", "events"],
        "min_relevance_score": 0.60,
        "top_k": 5,
    },
}


def get_strategy_pack() -> dict:
    return PERSONA_CONFIG
