# Agent 1: Source Retrieval — Requirements

**Owner:** Dev 1  
**File:** `agents/agent1_source_retrieval.py`  
**Output:** `retrieval_pack` JSON → consumed by Agent 2

---

## Module 0: Persona & Audience Config (lives inside Agent 1)

### Purpose
Defines who the influencer is and who they serve. Drives all retrieval decisions.

### Implementation
Static config file at `config/persona.py`. No database needed.

```python
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
            "isolation and community building"
        ],
        "platforms": ["LinkedIn", "Instagram"]
    },
    "topics": {
        "core": ["international students NYC", "student visa", "CUNY", "NYC housing students", "OPT CPT"],
        "adjacent": ["NYC cost of living", "student jobs NYC", "immigration policy NYC", "affordable neighborhoods NYC"],
        "excluded": ["entertainment", "sports", "unrelated NYC news"],
        "weights": {
            "international students NYC": 0.35,
            "student visa": 0.25,
            "NYC housing students": 0.20,
            "OPT CPT": 0.10,
            "NYC cost of living": 0.10
        }
    },
    "retrieval_directives": {
        "recency_bias": 0.7,
        "source_priority": ["nyc_open_data", "articles", "events"],
        "min_relevance_score": 0.60,
        "top_k": 5
    }
}
```

---

## Ingestion Layer

### Sources to Implement (priority order)

#### 1. NYC Open Data (Socrata API)
- Base URL: `https://data.cityofnewyork.us/resource/`
- Auth: App token via `NYC_OPEN_DATA_APP_TOKEN` env var
- Datasets to pull:

| Dataset ID | Name | Relevance |
|---|---|---|
| `kfnq-pz6f` | CUNY Enrollment by College | Student population data |
| `hg8x-zxpr` | NYC Job Postings | Employment for graduates |
| `fhrw-4uyv` | 311 Housing Complaints | Bad landlord data by area |

- Pull top 50 records per dataset, sorted by most recent
- Map each record to the unified document schema

#### 2. RSS Article Feeds
- `https://feeds.feedburner.com/ImmigrationProf` — immigration law updates
- `https://rss.app/feeds/` — configurable fallback
- Use `feedparser` library
- Pull latest 20 articles per feed

#### 3. Web Scrape (fallback only)
- Use `trafilatura` for clean text extraction from URLs
- Only trigger if RSS returns < 5 results

---

## Unified Document Schema

```python
{
    "id": str,            # uuid4
    "source_type": str,   # "nyc_open_data" | "article" | "event"
    "title": str,
    "content_raw": str,
    "published_at": str,  # ISO8601 or empty string
    "source_url": str,
    "tags": list[str],    # derived from topic taxonomy
    "relevance_score": float  # assigned at retrieval time
}
```

---

## Normalizer

- Strip HTML tags
- Remove records with `content_raw` under 50 characters
- Deduplicate by title similarity (simple string hash)
- Truncate content to 1000 characters per document (keep it fast)

---

## Chunker & Embedder

- Split each document into chunks of ~400 characters with 50-character overlap
- Embed each chunk using Gemini `text-embedding-004`
- Store as: `{"chunk_text": str, "embedding": list[float], "metadata": dict}`
- Run at startup, store in memory as a list

```python
import google.generativeai as genai

def embed(text: str) -> list[float]:
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text
    )
    return result["embedding"]
```

---

## In-Memory Vector Store

- Store all chunk embeddings in a Python list
- At query time, embed the query and compute cosine similarity against all chunks
- Return top-k by score

```python
import numpy as np

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

No external vector DB needed for MVP.

---

## Retrieval Interface

### Function Signature

```python
def retrieve(query: str, top_k: int = 5) -> dict:
    """
    Returns retrieval_pack consumed by Agent 2.
    """
```

### Steps
1. Embed the query using `text-embedding-004`
2. Score all stored chunks via cosine similarity
3. Filter by `min_relevance_score` from persona config
4. Apply topic weight boost (multiply score by topic weight if tag matches)
5. Return top-k results + persona config

### Output

Returns the `retrieval_pack` JSON defined in `architecture.md`.

---

## Environment Variables Required

```
GOOGLE_API_KEY=
NYC_OPEN_DATA_APP_TOKEN=
```

---

## Dependencies

```
google-generativeai
google-adk
feedparser
trafilatura
requests
numpy
python-dotenv
```

---

## What This Module Does NOT Do

- No content generation
- No trend analysis
- No posting or formatting
- No persistent database (in-memory only for MVP)
