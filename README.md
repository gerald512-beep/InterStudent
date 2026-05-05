# International Student AI Influencer

An AI-powered multi-agent pipeline that transforms fragmented civic and financial information into platform-ready social media content for international students in the United States. Built for the NYC Build With AI Hackathon 2026.

**GitHub:** https://github.com/gerald512-beep/InterStudent

## Team

Joaquin Sardon · Kulbir Kaur · Melissa Lee · Shivani Kabra · Gerald Velasquez

Course: Gen AI & Social Media

---

## What it does

A five-agent pipeline produces a complete social media content package from a single topic selection:

1. **Agent 1 — Source Retrieval** — Queries Google Search Grounding, NYC Open Data (job postings, CUNY enrollment, living wage), eight financial RSS feeds, and a curated F-1/J-1 tax knowledge seed. Chunks, embeds, and ranks results by relevance.
2. **Agent 2 — Content Generator** — Detects the trending angle, drafts platform-specific post text, hashtags, CTAs, and a five-scene video storyboard with SSML voice script.
3. **Creative Storyteller** — Generates a social image via Imagen (4.0-ultra → 4.0 → 3.0 fallback chain) and produces a final multimodal post body via Gemini.
4. **Agent 3 — Video Generator** — Generates per-scene clips with Veo 3.1 Fast (parallel, 3 workers), replaces audio with Chirp3-HD TTS, and assembles a 9:16 MP4 with subtitle overlays using MoviePy.
5. **Agent 4 — Quality Control** — Scores output across seven criteria (accuracy, tone, engagement, compliance, platform fit, video script, video visuals). Scores ≥ 7 → Publish; below 7 → Modify with structured feedback.

**Agent 5 — Scenario Resolver** (optional standalone) — Deterministic financial guidance for specific F-1/J-1 tax and visa scenarios, kept out of the probabilistic generation path.

---

## Prerequisites

- Python 3.11+ (3.12+ recommended)
- Node.js 18+ and npm
- Google Cloud project with Vertex AI enabled (Gemini, Imagen, Veo, Text-to-Speech)
- Application Default Credentials: `gcloud auth application-default login`

---

## Setup

### Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env   # fill in values (see table below)
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_BASE=http://localhost:8000
```

---

## Environment variables

| Variable | Purpose | Required |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini and embedding API access | Yes |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI project ID (default: `interstudent-nyc-2026`) | Yes |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region (default: `us-central1`) | Yes |
| `NYC_OPEN_DATA_APP_TOKEN` | Socrata API token — raises rate limits | No |
| `CORS_ALLOW_ORIGINS` | Override default CORS whitelist | No |

Frontend (`frontend/.env`):

| Variable | Purpose | Required |
|---|---|---|
| `VITE_API_BASE` | Backend URL (default: `http://localhost:8000`) | Yes |

---

## How to run

**Backend** (from repo root):

```bash
python -m uvicorn backend.server:app --reload --port 8000
```

**Frontend** (from `frontend/`):

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

Generated videos are saved under `videos/` (gitignored). The publish queue persists to `data/publish_queue.json` (gitignored).

---

## API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| `/topics` | GET | Seven predefined civic topic strings |
| `/avatar` | GET | Load canonical avatar |
| `/avatar/generate-image` | POST | Generate avatar image via Imagen |
| `/avatar/save` | POST | Persist canonical avatar to disk |
| `/generate/post` | POST | Full post pipeline (Agents 1, 2, Creative Storyteller) |
| `/generate/video_async` | POST | Launch background video job (Agents 3, 4) |
| `/jobs/{job_id}` | GET | Poll video job status |

---

## Tech stack

| Area | Technology |
|---|---|
| Frontend | React 19, TypeScript 6.0, Vite 8.0 |
| Backend | FastAPI, Uvicorn, Python 3.11+ |
| Retrieval | Gemini 2.5 Flash (Search Grounding), `gemini-embedding-001`, NYC Open Data (Socrata), RSS feeds |
| Content & image | Gemini 2.5 Flash, Imagen 4 Ultra |
| Video & audio | Veo 3.1 Fast, Chirp3-HD TTS, MoviePy |
| Publishing | JSON queue, stub LinkedIn/Instagram adapters, webhook notifications |

---

## Project layout

```
├── agents/
│   ├── agent1_source_retrieval.py     # Retrieval + embedding + ranking
│   ├── agent2_content_generator.py    # Post drafting + storyboard
│   ├── agent3_video_generator.py      # Veo + TTS + MoviePy assembly
│   ├── agent4_qc.py                   # Quality control scoring
│   ├── agent5_scenario_resolver.py    # Deterministic F-1/J-1 guidance
│   └── scenario_rules.py
├── backend/
│   └── server.py                      # FastAPI REST server
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # Main React component
│   │   └── main.tsx
│   └── package.json
├── output/
│   └── creative_storyteller.py        # Image gen + multimodal polish
├── publishing/
│   ├── service.py                     # Queue management
│   ├── adapters.py                    # Stub LinkedIn/Instagram publishers
│   ├── webhook.py                     # Webhook notification helper
│   └── storage.py
├── config/
│   └── persona.py                     # Audience persona configuration
├── docs/
│   └── project_report_v2.tex          # Full project report (LaTeX)
├── avatars/                           # canonical.json (saved avatar)
├── videos/                            # Exported MP4s (gitignored)
├── data/                              # publish_queue.json (gitignored)
├── app_streamlit_legacy.py            # Legacy Streamlit UI (inactive)
├── main.py                            # CLI: Agent 1 only
├── requirements.txt
└── .env.example
```

---

## Approximate cost per full run

| Component | Cost |
|---|---|
| Gemini 2.5 Flash (Agents 1, 2, 4, CS) | $0.01–$0.05 |
| Imagen 4 Ultra | $0.04 |
| Veo 3.1 Fast (5 scenes, ~40s) | $0.50–$0.75 |
| Chirp3-HD TTS | $0.01–$0.02 |
| NYC Open Data | Free |
| **Total (approx.)** | **$0.60–$0.90** |

---

## Known limitations

- LinkedIn and Instagram publishing adapters are stubs — no live platform publishing yet.
- Single audience persona (`config/persona.py`) — does not yet cover the full diversity of international student backgrounds and visa types.
- In-memory vector store — documents are re-embedded on every run; no persistent vector database.
- Pipeline output varies between runs due to the stochastic nature of Veo and Gemini — consistency at scale is the primary engineering challenge before production deployment.
- No explicit content filters for immigration or housing advice beyond Agent 4's compliance criterion.

---

## Roadmap

- [ ] Human approval gate before publishing
- [ ] Structured user testing with real international students
- [ ] Persistent vector store for cross-session retrieval quality
- [ ] Explicit content filters for sensitive topics (housing, immigration, safety)
- [ ] Live LinkedIn and Instagram publishing adapters
- [ ] Citation display in video storyboard and published captions
- [ ] Platform expansion: TikTok, WhatsApp, newsletters
- [ ] Multi-persona support beyond single `PERSONA_CONFIG`
