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
from google.genai import types

from config.persona import PERSONA_CONFIG

load_dotenv()

# Vertex AI client — for Google Search Grounding + optional embeddings fallback
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
_vertex_client = genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)

# Embeddings: prefer GOOGLE_API_KEY (AI Studio) when set; otherwise use Vertex (same model)
_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
_embed_client = (
    genai.Client(api_key=_api_key) if _api_key else _vertex_client
)

EMBEDDING_MODEL = "gemini-embedding-001"
GROUNDING_MODEL = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NYC_DATASETS = {
    "kpav-sd4t": "NYC Job Postings",
    "d44m-4xgv": "CUNY First Year Applications",
    "ic3t-wcy2": "NYC Living Wage",
}

RSS_FEEDS = [
    # Tax / IRS
    "https://www.irs.gov/rss/newsroom.rss",
    # Consumer finance
    "https://www.consumerfinance.gov/about-us/blog/feed/",
    # Student financial aid policy
    "https://www.nasfaa.org/rss/news",
    # NYT Business (covers student finance, economy)
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    # Loan providers — graceful fallback if feed unavailable
    "https://www.prodigyfinance.com/blog/feed/",
    "https://www.sofi.com/blog/feed/",
    "https://www.earnest.com/blog/feed/",
    "https://www.mpowerfinancing.com/blog/feed/",
]

NYC_OPEN_DATA_BASE = "https://data.cityofnewyork.us/resource"

# ---------------------------------------------------------------------------
# Static tax scenario knowledge seed
# Injected on every run — covers common W-2 and F1/J1 tax scenarios
# ---------------------------------------------------------------------------

TAX_SCENARIOS = [
    {
        "title": "F1 student W-2 from two different employers",
        "content": "F1 student with W-2 from 2 different employers: file Form 1040-NR, report both W-2s on lines 1a and 1b. As an F1 student in first 5 years, you are a nonresident alien exempt from FICA (Social Security and Medicare) taxes while enrolled full-time. Both employers should not have withheld FICA — if they did, file Form 843 to claim a refund.",
    },
    {
        "title": "F1 student W-2 from two different states",
        "content": "F1 student with W-2 from 2 different states: file one federal Form 1040-NR plus a separate state income tax return for each state where you earned income. For example, if you worked in New York and New Jersey, file NY IT-203 (nonresident) and NJ 1040NR. New York requires filing if you earned income in NY even as a nonresident.",
    },
    {
        "title": "J1 scholar stipend plus W-2 income",
        "content": "J1 scholar receiving stipend plus W-2 wages: the W-2 wages are always taxable. The stipend may be partially or fully exempt under a US tax treaty depending on your home country — check IRS Publication 901 for your country's treaty. File Form 1040-NR and attach Form 8833 if claiming treaty benefits.",
    },
    {
        "title": "OPT income and FICA taxes",
        "content": "OPT (Optional Practical Training) income: F1 students on OPT remain nonresident aliens exempt from FICA taxes for the first 5 calendar years in the US. Once you become a resident alien for tax purposes (typically after 5 years), OPT income becomes subject to FICA. File Form 1040-NR if still a nonresident, Form 1040 if resident alien.",
    },
    {
        "title": "ITIN application for international students without SSN",
        "content": "International students without a Social Security Number (SSN) need an Individual Taxpayer Identification Number (ITIN) to file US taxes. Apply using Form W-7 with your tax return. Required documents: passport, F1/J1 visa, I-20 or DS-2019. Processing takes 7-11 weeks. You can apply through an IRS-authorized Certifying Acceptance Agent at many CUNY and NYU campuses.",
    },
    {
        "title": "Opening a US bank account as an international student",
        "content": "International students can open US bank accounts without an SSN at many banks using passport and I-20. Chase, Bank of America, and Citibank accept ITIN or foreign tax ID. Online options: Wise, Revolut, and Mercury accept international students. Credit unions like CUNY's preferred partners often have lower fees. Avoid monthly fees by maintaining minimum balance or using student accounts.",
    },
    {
        "title": "Building US credit history as an international student",
        "content": "International students can build US credit history using: secured credit cards (Discover it Secured, Capital One Secured), becoming an authorized user on a friend's account, or using credit-builder programs like Self. Some banks (Deserve EDU, Nova Credit) use international credit history. Avoid payday loans. A good credit score opens doors to apartments, loans, and better interest rates after graduation.",
    },
]


# ---------------------------------------------------------------------------
# 1. Google Search Grounding (primary source)
# ---------------------------------------------------------------------------

GROUNDING_QUERIES = [
    "banking account options for F1 visa international student NYC 2025 no SSN",
    "scholarships grants for international students NYC universities 2025",
    "W-2 taxes F1 J1 visa nonresident alien form 1040-NR multiple employers states",
    "Prodigy Finance SoFi Earnest MPOWER international student loans review 2025",
    "OPT CPT income tax obligations international students USA",
]


def fetch_grounded_search(query: str) -> list[dict]:
    try:
        response = _vertex_client.models.generate_content(
            model=GROUNDING_MODEL,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )

        docs = []
        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return []

        grounding = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(grounding, "grounding_chunks", []) if grounding else []

        # Each grounding chunk becomes a source doc
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            title = getattr(web, "title", query[:80]) or query[:80]
            uri = getattr(web, "uri", "") or ""
            # Use the synthesized response text as content for this source
            content = response.text[:800] if response.text else query
            docs.append({
                "id": str(uuid.uuid4()),
                "source_type": "grounded_search",
                "title": title,
                "content_raw": content,
                "published_at": "",
                "source_url": uri,
                "tags": ["grounded_search", "live"],
                "relevance_score": 0.0,
            })

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique = []
        for doc in docs:
            if doc["source_url"] not in seen_urls:
                seen_urls.add(doc["source_url"])
                unique.append(doc)

        return unique[:5]

    except Exception as exc:
        print(f"[agent1] Grounded search failed ({query[:50]}...): {exc}")
        return []


# ---------------------------------------------------------------------------
# 2. NYC Open Data (supplementary)
# ---------------------------------------------------------------------------

def fetch_nyc_open_data(dataset_id: str, limit: int = 5) -> list[dict]:
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


# ---------------------------------------------------------------------------
# 3. RSS feeds (finance-specific)
# ---------------------------------------------------------------------------

def fetch_rss_articles(feed_url: str) -> list[dict]:
    try:
        feed = feedparser.parse(feed_url)
        entries = feed.entries[:15]
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


# ---------------------------------------------------------------------------
# 4. Tax scenario knowledge seed
# ---------------------------------------------------------------------------

def build_tax_scenario_docs() -> list[dict]:
    docs = []
    for scenario in TAX_SCENARIOS:
        docs.append({
            "id": str(uuid.uuid4()),
            "source_type": "knowledge_seed",
            "title": scenario["title"],
            "content_raw": scenario["content"],
            "published_at": "",
            "source_url": "https://www.irs.gov/individuals/international-taxpayers",
            "tags": ["knowledge_seed", "taxes", "F1", "W-2"],
            "relevance_score": 0.0,
        })
    return docs


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def fetch_all_sources() -> list[dict]:
    docs: list[dict] = []

    print("[agent1] Running Google Search Grounding queries...")
    for query in GROUNDING_QUERIES:
        batch = fetch_grounded_search(query)
        print(f"  '{query[:50]}...': {len(batch)} results")
        docs.extend(batch)

    print("[agent1] Fetching finance RSS feeds...")
    for feed_url in RSS_FEEDS:
        batch = fetch_rss_articles(feed_url)
        print(f"  {feed_url.split('/')[2]}: {len(batch)} articles")
        docs.extend(batch)

    print("[agent1] Fetching NYC Open Data (supplementary)...")
    for dataset_id, name in NYC_DATASETS.items():
        batch = fetch_nyc_open_data(dataset_id)
        print(f"  {name}: {len(batch)} records")
        docs.extend(batch)

    print("[agent1] Injecting tax scenario knowledge seed...")
    seed_docs = build_tax_scenario_docs()
    docs.extend(seed_docs)
    print(f"  {len(seed_docs)} tax scenario docs added")

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
    result = _embed_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    return result.embeddings[0].values


def embed_chunks(chunks: list[dict]) -> list[dict]:
    total = len(chunks)
    for batch_start in range(0, total, EMBED_BATCH_SIZE):
        batch = chunks[batch_start: batch_start + EMBED_BATCH_SIZE]
        texts = [c["chunk_text"] for c in batch]
        result = _embed_client.models.embed_content(
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

    def search(self, query: str, top_k: int = 5, min_score: float = 0.55) -> list[dict]:
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

            # Boost grounded search and knowledge seed results
            if chunk["metadata"]["source_type"] in ("grounded_search", "knowledge_seed"):
                score *= 1.15

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
