# Dev 1 Tasks — Agent 1: Source Retrieval

**Time budget:** 4 hours  
**Your files:** `config/persona.py`, `agents/agent1_source_retrieval.py`

---

## Hour-by-Hour Plan

| Time | Task |
|---|---|
| 0:00 – 0:30 | Setup: repo, env, dependencies |
| 0:30 – 1:00 | Module 0: persona config + project structure |
| 1:00 – 2:00 | Ingestion: NYC Open Data + RSS connectors |
| 2:00 – 2:45 | Normalizer + Chunker + Embedder |
| 2:45 – 3:30 | Vector store + Retrieval Interface |
| 3:30 – 4:00 | Integration test + hand off JSON to Dev 2 |

---

## Task 1 — Setup (0:00–0:30)

### Steps
1. Create the project folder structure:
```
mkdir -p agents config output tests docs
touch main.py app.py .env requirements.txt .env.example
```

2. Create `requirements.txt`:
```
google-generativeai
google-adk
feedparser
trafilatura
requests
numpy
python-dotenv
streamlit
vertexai
Pillow
```

3. Create `.env.example`:
```
GOOGLE_API_KEY=your_key_here
NYC_OPEN_DATA_APP_TOKEN=your_token_here
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1
```

4. Install: `pip install -r requirements.txt`

5. Get a free NYC Open Data App Token at: `https://data.cityofnewyork.us/profile/app_tokens`

### Vibe Coding Prompt
```
Create a Python project structure for a multi-agent AI pipeline.
Create these files with placeholder content:
- config/persona.py
- agents/agent1_source_retrieval.py
- agents/agent2_content_generator.py
- output/creative_storyteller.py
- main.py
- app.py
- tests/mock_retrieval_pack.json
Add __init__.py files to each folder.
```

---

## Task 2 — Module 0: Persona Config (0:30–1:00)

### Steps
1. Create `config/persona.py` with the full `PERSONA_CONFIG` dict from `agent1-requirements.md`
2. Add a helper function `get_strategy_pack()` that returns the config

### Vibe Coding Prompt
```
Create config/persona.py for an AI influencer targeting international students in NYC.
Include:
- Persona dict with: niche, tone, expertise_level, content_goal
- Audience dict with: primary description, list of pain_points, platforms
- Topics dict with: core list, adjacent list, excluded list, weights dict (must sum to 1.0)
- Retrieval directives: recency_bias (0.7), source_priority list, min_relevance_score (0.6), top_k (5)
Add a get_strategy_pack() function that returns the full config dict.
```

---

## Task 3 — NYC Open Data Connector (1:00–1:45)

### Target Datasets

| Dataset ID | Description |
|---|---|
| `kfnq-pz6f` | CUNY Enrollment |
| `hg8x-zxpr` | NYC Job Postings |
| `fhrw-4uyv` | 311 Housing Complaints |

### Vibe Coding Prompt
```
Create a Python function fetch_nyc_open_data(dataset_id: str, limit: int = 50) -> list[dict]
that:
- Calls the NYC Open Data Socrata API at https://data.cityofnewyork.us/resource/{dataset_id}.json
- Passes the app token from env var NYC_OPEN_DATA_APP_TOKEN as header X-App-Token
- Returns a list of records as dicts
- Handles HTTP errors gracefully (return empty list on failure, print error)

Then create fetch_all_sources() that calls fetch_nyc_open_data for these dataset IDs:
- kfnq-pz6f (CUNY Enrollment)
- hg8x-zxpr (NYC Job Postings)  
- fhrw-4uyv (311 Housing Complaints)

And maps each record to this schema:
{
  "id": uuid string,
  "source_type": "nyc_open_data",
  "title": first non-empty string field in the record,
  "content_raw": JSON stringified record (truncated to 1000 chars),
  "published_at": empty string,
  "source_url": f"https://data.cityofnewyork.us/resource/{dataset_id}",
  "tags": ["nyc_open_data"],
  "relevance_score": 0.0
}
```

### Also add RSS feed connector:

```
Add a function fetch_rss_articles(feed_url: str) -> list[dict] using feedparser
that returns the latest 20 articles mapped to the same document schema above.
source_type should be "article".
Use feedparser to get title and summary as content_raw.
```

---

## Task 4 — Normalizer + Chunker + Embedder (2:00–2:45)

### Vibe Coding Prompt
```
Create three Python functions:

1. normalize(docs: list[dict]) -> list[dict]
   - Remove records where content_raw is under 50 characters
   - Strip HTML tags from content_raw using a simple regex
   - Deduplicate by title (keep first occurrence)
   - Return cleaned list

2. chunk_document(doc: dict, chunk_size: int = 400, overlap: int = 50) -> list[dict]
   - Split doc["content_raw"] into chunks of chunk_size characters with overlap
   - Return list of dicts: {"chunk_text": str, "metadata": {id, title, source_type, source_url, tags, published_at}}

3. embed_chunks(chunks: list[dict]) -> list[dict]
   - For each chunk, call Google Gemini text-embedding-004 model to embed chunk["chunk_text"]
   - Use: google.generativeai.embed_content(model="models/text-embedding-004", content=text)
   - Add "embedding": list[float] to each chunk dict
   - Return the list with embeddings added
   - Print progress every 10 chunks

Use GOOGLE_API_KEY from environment via python-dotenv.
```

---

## Task 5 — Vector Store + Retrieval Interface (2:45–3:30)

### Vibe Coding Prompt
```
Create a Python class VectorStore with:

__init__(self): initializes empty self.chunks list

add(self, chunks: list[dict]): appends chunks to self.chunks

search(self, query: str, top_k: int = 5, min_score: float = 0.6) -> list[dict]:
  - Embed the query using google.generativeai text-embedding-004
  - Compute cosine similarity between query embedding and each chunk's embedding
    using numpy: np.dot(a,b) / (np.linalg.norm(a) * np.linalg.norm(b))
  - Filter results below min_score
  - Sort by score descending
  - Return top_k results as list of dicts with added "relevance_score" field

Then create the main retrieval function:

def retrieve(query: str) -> dict:
  - Load PERSONA_CONFIG from config/persona.py
  - Fetch all sources using fetch_all_sources()
  - Normalize, chunk, and embed them
  - Add to VectorStore
  - Search using query and persona retrieval_directives
  - Return retrieval_pack dict matching this schema:
    {
      "query_topic": query,
      "persona": {niche, audience (primary), tone, content_goal},
      "results": [
        {id, source_type, title, content_chunk, published_at, relevance_score, source_url, tags}
        for each top result
      ]
    }
```

---

## Task 6 — Integration Test (3:30–4:00)

### Steps

1. Run a quick test:
```python
# In main.py or a test script
from agents.agent1_source_retrieval import retrieve
result = retrieve("housing costs for international students NYC")
print(result)
```

2. Save a sample output to `tests/mock_retrieval_pack.json` — Dev 2 needs this file to work independently

3. Share the file with Dev 2

### Vibe Coding Prompt for integration test
```
Create a file tests/test_agent1.py that:
- Calls retrieve("housing costs for international students NYC")
- Prints the number of results returned
- Prints the title and relevance_score of each result
- Saves the full output as JSON to tests/mock_retrieval_pack.json
- Asserts that at least 1 result is returned
Run it with: python tests/test_agent1.py
```

---

## Done Criteria

- [ ] `config/persona.py` exists and returns a valid strategy pack
- [ ] `fetch_all_sources()` returns at least 10 documents
- [ ] `retrieve("housing for international students NYC")` returns at least 1 result
- [ ] `tests/mock_retrieval_pack.json` exists and is valid JSON
- [ ] Dev 2 has confirmed they can load the mock file
