# NYC International Student AI Influencer

> AI-powered content agent that surfaces civic inequities and resources for international students in NYC — built for the NYC Build With AI Hackathon.

## Team

| Name | Role |
|---|---|
| [TEAM MEMBER 1] | Dev 1 — Agent 1 (Source Retrieval) |
| [TEAM MEMBER 2] | Dev 2 — Agent 2 + Creative Output |

## What It Does

An autonomous multi-agent pipeline that:
1. Retrieves real NYC Open Data + articles relevant to international students
2. Identifies trending topics and angles (housing, visas, jobs, cost of living)
3. Generates a multimodal LinkedIn/Instagram post (text + image) using Gemini's interleaved output

## Why It's Civic

International students in NYC face systemic inequities: predatory housing, limited work rights, higher tuition costs, visa complexity. This tool surfaces real NYC data to give them a voice and help them navigate the city — turning public datasets into actionable, shareable content.

## Tech Stack

| Component | Technology |
|---|---|
| Agent orchestration | Google Agent Development Kit (ADK) |
| Content generation | Gemini 2.0 Flash |
| Image generation | Imagen 3 |
| Embeddings | text-embedding-004 |
| Data source | NYC Open Data (Socrata API) |
| Hosting | Google Cloud Run |
| Language | Python 3.11+ |

## Architecture

```
Module 0 (Persona Config)
        │
        ▼
Agent 1: Source Retrieval  ──▶  Agent 2: Trend Content Generator  ──▶  Creative Storyteller Output
(NYC Open Data + Articles)       (Gemini 2.0 Flash via ADK)             (Text + Image via Gemini)
```

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Fill in: GOOGLE_API_KEY, NYC_OPEN_DATA_APP_TOKEN

# Run the pipeline
python main.py

# Launch demo UI
streamlit run app.py
```

## Project Structure

```
/
├── agents/
│   ├── agent1_source_retrieval.py
│   └── agent2_content_generator.py
├── output/
│   └── creative_storyteller.py
├── config/
│   └── persona.py
├── app.py                  # Streamlit demo UI
├── main.py                 # Pipeline entry point
├── requirements.txt
├── .env.example
└── docs/
    ├── architecture.md
    ├── agent1-requirements.md
    ├── agent2-requirements.md
    ├── output-requirements.md
    ├── dev1-tasks.md
    └── dev2-tasks.md
```

## Hackathon Submission Checklist

- [ ] Git repository is public
- [ ] README lists all team members
- [ ] Deployed to Google Cloud Run
- [ ] Uses Google GenAI SDK / ADK
- [ ] Uses Gemini interleaved/mixed output (Creative Storyteller)
- [ ] Demo video or live demo ready
- [ ] Architecture diagram visible in presentation
- [ ] NYC Open Data referenced and used
