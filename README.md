# NYC International Student AI Influencer

AI-powered multi-agent pipeline that surfaces civic inequities and resources for international students in NYC — built for the NYC Build With AI Hackathon.

## Team

| Name | Role |
|------|------|
| Kulbir Kaur | Dev 1 & Biz Strategy |
| Gerald Velasquez | Dev 2 |

## What it does

1. Retrieves NYC Open Data, RSS, and grounded web sources relevant to international students.
2. Detects trends and generates platform-specific LinkedIn/Instagram posts with CTAs.
3. Produces images (Imagen) and optional multi-scene video (Veo, TTS, assembly).
4. **Audience Personalization** — persona, segment, tone, CTA style, and related fields feed Agent 2, the Creative Storyteller, and the video brief.
5. **Auto-publishing (local)** — JSON-backed draft/queue, stub LinkedIn/Instagram adapters, optional webhook notifications (no full Instagram consumer automation).

## Prerequisites

- **Python 3.11+** (3.12+ recommended; 3.14 works with current pins where wheels exist).
- **Google Cloud** project with Vertex AI enabled for Gemini, Imagen, Veo, and Text-to-Speech, plus Application Default Credentials or service account as required by your environment.
- **API keys / tokens** as listed under Environment variables.

## Install dependencies

From the repository root:

```bash
python -m venv .venv
```

Activate the virtual environment:

- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
- **macOS / Linux:** `source .venv/bin/activate`

Then install packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Environment variables

Copy the example file and fill in real values:

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` | Google AI (Gemini) API key for embeddings and clients that use the API key path (see `agents/agent1_source_retrieval.py`). |
| `NYC_OPEN_DATA_APP_TOKEN` | NYC Open Data (Socrata) API app token for higher rate limits. |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI. |
| `GOOGLE_CLOUD_LOCATION` | Region (e.g. `us-central1`). |

Ensure Application Default Credentials are available if you use Vertex AI (`gcloud auth application-default login` for local dev, or workload identity in production).

## How to run

**Agent 1-only pipeline (CLI):**

```bash
python main.py
```

**Full Streamlit UI** (Agents 1–4, storyboard editor, personalization, publishing):

```bash
streamlit run app.py
```

Generated videos are written under `videos/` when present. The publish queue persists to `data/publish_queue.json` (created on first save). Override the queue directory with:

```bash
set INTERSTUDENT_QUEUE_DIR=C:\path\to\queue\dir
```

(Use `export` on Unix.)

## Optional: webhook on publish

In the Streamlit sidebar, set **Webhook URL** and enable **Notify webhook on manual / due publish**. The app POSTs JSON: `{"event": "publish_attempt", "payload": {...}}` to your endpoint.

## Tech stack

| Area | Technology |
|------|------------|
| UI | Streamlit, pandas (queue table) |
| Retrieval & embeddings | Gemini, NYC Open Data, RSS, Google Search Grounding |
| Content & video | Gemini 2.5 Flash, Imagen 4, Veo, Chirp3-HD (TTS), MoviePy |
| Publishing | Local JSON queue, stub adapters, `requests` for webhooks |
| Language | Python 3.11+ |

## Project layout

```
├── agents/
│   ├── agent1_source_retrieval.py
│   ├── agent2_content_generator.py
│   ├── agent3_video_generator.py
│   └── agent4_qc.py
├── publishing/           # Local queue, stub publishers, webhook helper
├── output/
│   └── creative_storyteller.py
├── config/
│   └── persona.py
├── audience_personalization.py
├── app.py                  # Streamlit app
├── main.py                 # CLI: Agent 1 retrieval only
├── requirements.txt
├── .env.example
├── data/                   # publish_queue.json (gitignored when present)
├── docs/                   # Additional design/requirements notes
└── videos/                 # Exported videos (gitignored)
```

## Development notes

- Run `pip install -r requirements.txt` after pulling changes.
- `data/publish_queue.json` is listed in `.gitignore`; each environment creates its own queue file.

## Hackathon checklist

- [ ] Git repository is public
- [ ] README lists all team members
- [ ] Deployed to Google Cloud Run (optional)
- [ ] Uses Google GenAI / Vertex AI
- [ ] Demo video or live demo ready
- [ ] NYC Open Data referenced and used

More architecture and task notes live under `docs/`.
