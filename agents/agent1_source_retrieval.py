import os
import re
import json
import uuid

import time
import feedparser
import numpy as np
import requests
from dotenv import load_dotenv
from google import genai

from config.persona import PERSONA_CONFIG

load_dotenv()
_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

EMBEDDING_MODEL = "gemini-embedding-001"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NYC_DATASETS = {
    "erm2-nwe9": "311 Housing Complaints",
    "kpav-sd4t": "NYC Job Postings",
    "d44m-4xgv": "CUNY First Year Applications",
}

RSS_FEEDS = [
    "https://feeds.feedburner.com/ImmigrationProf",
    "https://rss.nytimes.com/services/xml/rss/nyt/Education.xml",
]

NYC_OPEN_DATA_BASE = "https://data.cityofnewyork.us/resource"

# ---------------------------------------------------------------------------
# Ingestion Layer
# ---------------------------------------------------------------------------

def fetch_nyc_open_data(dataset_id: str, limit: int = 10) -> list[dict]:
    url = f"{NYC_OPEN_DATA_BASE}/{dataset_id}.json"
    params = {"$limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        records = resp.json()
    except Exception as exc:
        print(f"[agent1] NYC Open Data fetch failed ({dataset_id}): {exc}")
        return []

    docs = []
    for record in records:
        title = _first_string_value(record) or dataset_id
        content_raw = json.dumps(record)[:1000]
        docs.append({
            "id": str(uuid.uuid4()),
            "source_type": "nyc_open_data",
            "title": title,
            "content_raw": content_raw,
            "published_at": "",
            "source_url": f"{NYC_OPEN_DATA_BASE}/{dataset_id}",
            "tags": ["nyc_open_data", NYC_DATASETS.get(dataset_id, dataset_id)],
            "relevance_score": 0.0,
        })
    return docs


def _first_string_value(record: dict) -> str:
    for v in record.values():
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    return ""


def fetch_rss_articles(feed_url: str) -> list[dict]:
    try:
        feed = feedparser.parse(feed_url)
        entries = feed.entries[:20]
    except Exception as exc:
        print(f"[agent1] RSS fetch failed ({feed_url}): {exc}")
        return []

    docs = []
    for entry in entries:
        title = getattr(entry, "title", "")
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        content_raw = f"{title}. {summary}"[:1000]
        published = getattr(entry, "published", "") or ""
        link = getattr(entry, "link", feed_url)
        docs.append({
            "id": str(uuid.uuid4()),
            "source_type": "article",
            "title": title,
            "content_raw": content_raw,
            "published_at": published,
            "source_url": link,
            "tags": ["article"],
            "relevance_score": 0.0,
        })
    return docs


def fetch_all_sources() -> list[dict]:
    docs: list[dict] = []

    print("[agent1] Fetching NYC Open Data...")
    for dataset_id, name in NYC_DATASETS.items():
        batch = fetch_nyc_open_data(dataset_id)
        print(f"  {name}: {len(batch)} records")
        docs.extend(batch)

    print("[agent1] Fetching RSS feeds...")
    for feed_url in RSS_FEEDS:
        batch = fetch_rss_articles(feed_url)
        print(f"  {feed_url}: {len(batch)} articles")
        docs.extend(batch)

    print(f"[agent1] Total documents fetched: {len(docs)}")
    return docs


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize(docs: list[dict]) -> list[dict]:
    seen_titles: set[str] = set()
    cleaned: list[dict] = []

    for doc in docs:
        content = _HTML_TAG_RE.sub("", doc["content_raw"]).strip()
        content = content[:1000]

        if len(content) < 50:
            continue

        title_key = doc["title"].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        doc["content_raw"] = content
        cleaned.append(doc)

    print(f"[agent1] After normalization: {len(cleaned)} documents")
    return cleaned


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

def chunk_document(doc: dict, chunk_size: int = 400, overlap: int = 50) -> list[dict]:
    text = doc["content_raw"]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append({
            "chunk_text": chunk_text,
            "metadata": {
                "id": doc["id"],
                "title": doc["title"],
                "source_type": doc["source_type"],
                "source_url": doc["source_url"],
                "tags": doc["tags"],
                "published_at": doc["published_at"],
            },
        })
        start += chunk_size - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 50


def embed_text(text: str) -> list[float]:
    result = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return result.embeddings[0].values


def embed_chunks(chunks: list[dict]) -> list[dict]:
    total = len(chunks)
    for batch_start in range(0, total, EMBED_BATCH_SIZE):
        batch = chunks[batch_start: batch_start + EMBED_BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]
        result = _client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
        )
        for chunk, embedding in zip(batch, result.embeddings):
            chunk["embedding"] = embedding.values
        done = min(batch_start + EMBED_BATCH_SIZE, total)
        print(f"[agent1] Embedded {done}/{total} chunks")
        if done < total:
            time.sleep(62)  # stay under 100 requests/min quota
    print(f"[agent1] Embedding complete: {total} chunks")
    return chunks


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------

class VectorStore:
    def __init__(self):
        self.chunks: list[dict] = []

    def add(self, chunks: list[dict]) -> None:
        self.chunks.extend(chunks)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.6) -> list[dict]:
        if not self.chunks:
            return []

        query_embedding = np.array(embed_text(query))
        topic_weights = PERSONA_CONFIG["topics"]["weights"]
        scored: list[tuple[float, dict]] = []

        for chunk in self.chunks:
            chunk_vec = np.array(chunk["embedding"])
            norm = np.linalg.norm(query_embedding) * np.linalg.norm(chunk_vec)
            score = float(np.dot(query_embedding, chunk_vec) / (norm + 1e-9))

            for topic, weight in topic_weights.items():
                if topic.lower() in chunk["chunk_text"].lower():
                    score *= (1 + weight)
                    break

            if score >= min_score:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            results.append({
                "id": chunk["metadata"]["id"],
                "source_type": chunk["metadata"]["source_type"],
                "title": chunk["metadata"]["title"],
                "content_chunk": chunk["chunk_text"],
                "published_at": chunk["metadata"]["published_at"],
                "relevance_score": round(score, 4),
                "source_url": chunk["metadata"]["source_url"],
                "tags": chunk["metadata"]["tags"],
            })
        return results


# ---------------------------------------------------------------------------
# Retrieval Interface
# ---------------------------------------------------------------------------

def retrieve(query: str) -> dict:
    directives = PERSONA_CONFIG["retrieval_directives"]
    audience = PERSONA_CONFIG["audience"]

    docs = fetch_all_sources()
    docs = normalize(docs)

    all_chunks: list[dict] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))

    all_chunks = embed_chunks(all_chunks)

    store = VectorStore()
    store.add(all_chunks)

    results = store.search(
        query=query,
        top_k=directives["top_k"],
        min_score=directives["min_relevance_score"],
    )

    if not results:
        print("[agent1] No results above threshold, relaxing min_score to 0.3")
        results = store.search(query=query, top_k=directives["top_k"], min_score=0.3)

    return {
        "query_topic": query,
        "persona": {
            "niche": PERSONA_CONFIG["niche"],
            "audience": audience["primary"],
            "tone": PERSONA_CONFIG["tone"],
            "content_goal": PERSONA_CONFIG["content_goal"],
        },
        "results": results,
    }
