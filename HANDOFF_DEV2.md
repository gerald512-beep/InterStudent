# Handoff to Dev 2 — Agent 1 is Ready

## Status
Agent 1 is working and tested. Your input file is ready at:
```
tests/mock_retrieval_pack.json
```
You do NOT need to run Agent 1 to start. Use this file directly.

---

## How to Load It

```python
import json

with open("tests/mock_retrieval_pack.json", "r") as f:
    retrieval_pack = json.load(f)

# Pass straight into your agent
content_draft = run_agent2(retrieval_pack)
```

---

## What's Inside

### Top-level structure
```json
{
  "query_topic": "housing costs for international students NYC",
  "persona": { ... },
  "results": [ ... ]
}
```

### `persona` — use this to guide tone and framing
```json
{
  "niche": "International students in NYC",
  "audience": "International students aged 18-30 living in NYC",
  "tone": "helpful, empowering, informative",
  "content_goal": "surface inequities and share practical resources"
}
```

### `results` — 5 ranked chunks, these are your raw material

| # | Title | Source | Relevance | Key content |
|---|---|---|---|---|
| 1 | Plunging International Student Enrollment Under Trump... | NYT Article | 0.63 | Trump policy cutting international student enrollment — squeezing colleges |
| 2 | 774233 | NYC Job Postings | 0.62 | Student intern role, $20/hr, Intergovernmental Relations |
| 3 | 769071 | NYC Job Postings | 0.61 | Law school summer intern, $17.90–$26.73/hr |
| 4 | 774202 | NYC Job Postings | 0.60 | Student intern, $17.50/hr, Economic Development |
| 5 | 773300 | NYC Job Postings | 0.60 | College Aid role, $17.50/hr |

---

## Important: Read `content_chunk`, not `title`

NYC Open Data records have raw numeric IDs as titles (e.g. `"774233"`).
**The actual useful content is in `content_chunk`.**

```python
for r in retrieval_pack["results"]:
    print(r["content_chunk"])  # ← use this
    # NOT r["title"] for nyc_open_data records
```

---

## Best Trend Angle (recommended)

The strongest angle for Agent 2 is **result #1** (the NYT article):

> *"International student enrollment is plunging under Trump policy — and NYC students are caught in the middle."*

Pair it with the NYC job data (results 2–5) to add a local civic angle:
> *"Even as enrollment drops, NYC is still posting student-level jobs at $17–$26/hr — but can international students legally take them? Here's what OPT/CPT rules say."*

This hits: urgency (Trump policy), NYC data (job postings), audience pain point (work restrictions), and a clear actionable tip.

---

## Your Output Contract

Your `run_agent2(retrieval_pack)` must return this exact shape for the Creative Storyteller:

```json
{
  "post_text": "string (under 250 words)",
  "image_prompt": "string (description for Imagen 3, no text in image)",
  "platform": "linkedin",
  "hashtags": ["#InternationalStudents", "#NYC", "..."],
  "topic": "string (the angle used)",
  "sources": ["https://...", "https://..."],
  "urgency": "high"
}
```

---

## Environment

Make sure your `.env` has:
```
GOOGLE_API_KEY=AIzaSyA8Oe4K_oVhbcWdxtqaGOjwjhRcMxDkcWE
GOOGLE_CLOUD_PROJECT=interstudent-nyc-2026
GOOGLE_CLOUD_LOCATION=us-central1
```

---

## Questions?
Ping Dev 1 or check `docs/agent2-requirements.md` for the full spec.
