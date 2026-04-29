# System Architecture — NYC International Student AI Influencer

> NYC Build With AI Hackathon 2026 · Powered by Google Cloud / Vertex AI

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                                 │
│              Topic selector · Platform toggle (LinkedIn/Instagram)  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT 1 — Source Retrieval                                         │
│                                                                     │
│  ┌──────────────────────────┐   ┌──────────────────────────────┐   │
│  │ 🔍 Google Search         │   │ 📰 Finance RSS Feeds          │   │
│  │    Grounding             │   │    IRS · CFPB · NASFAA        │   │
│  │    Gemini 2.5 Flash      │   │    NYT · SoFi · Prodigy       │   │
│  │    Live web results      │   │    Earnest · MPOWER           │   │
│  └──────────────┬───────────┘   └──────────────┬───────────────┘   │
│                 │                               │                   │
│  ┌──────────────┴───────────┐   ┌──────────────┴───────────────┐   │
│  │ 🏙️ NYC Open Data API     │   │ 📚 Tax Knowledge Seed         │   │
│  │    Jobs · CUNY           │   │    7 static F1/J1 scenarios   │   │
│  │    Living Wage           │   │    W-2 · ITIN · OPT · FICA    │   │
│  └──────────────┬───────────┘   └──────────────┬───────────────┘   │
│                 │                               │                   │
│                 └───────────────┬───────────────┘                   │
│                                 ▼                                   │
│                 ┌───────────────────────────────┐                   │
│                 │ 🧮 gemini-embedding-001         │                   │
│                 │    Chunk · Embed · Index        │                   │
│                 │    In-memory vector store       │                   │
│                 │    Cosine similarity search     │                   │
│                 └───────────────┬───────────────┘                   │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │ top-k relevant chunks
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT 2 — Content Generator                                        │
│                                                                     │
│  ┌───────────────────────────┐   ┌───────────────────────────────┐  │
│  │ 📈 Trend Detector         │   │ ✍️  Post Generator             │  │
│  │    Gemini 2.5 Flash       │──▶│    Gemini 2.5 Flash            │  │
│  │    Topic · Urgency        │   │    LinkedIn / Instagram        │  │
│  │    Key fact · Source URL  │   │    CTA links · Hashtags        │  │
│  └───────────────────────────┘   └───────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ 🎬 Video Brief Generator — Gemini 2.5 Flash                  │    │
│  │    5-scene storyboard · SSML script · Avatar description     │    │
│  │    Camera angles · Voiceover per scene · Duration · Emotion  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CREATIVE STORYTELLER                                               │
│                                                                     │
│  ┌───────────────────────────┐   ┌───────────────────────────────┐  │
│  │ 🖼️  Imagen 4 Ultra         │   │ ✨ Gemini 2.5 Flash            │  │
│  │    Post image · 9:16      │──▶│    Interleaved text + image    │  │
│  │    Fallback: Imagen 4     │   │    Final post body             │  │
│  │    Fallback: Imagen 3     │   │                                │  │
│  └───────────────────────────┘   └───────────────────────────────┘  │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ post image + body
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STORYBOARD EDITOR (Streamlit)                                      │
│  Review & edit each scene before video generation                   │
│  Visual prompt · Voiceover · Duration · Full SSML script            │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ approved storyboard
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT 3 — Video Generator                                          │
│                                                                     │
│  ┌───────────────────────────┐                                      │
│  │ 🎙️  Chirp3-HD TTS          │                                      │
│  │    Google Cloud TTS       │                                      │
│  │    SSML · Female / Male   │                                      │
│  │    en-US-Chirp3-HD-Aoede  │                                      │
│  └───────────────┬───────────┘                                      │
│                  │                                                  │
│  ┌───────────────▼───────────────────────────────────────────────┐  │
│  │ 🎥 Veo 3.1 Fast — 5 scenes in parallel (max 3 workers)        │  │
│  │    veo-3.1-fast-generate-001 · 9:16 · 8s per clip             │  │
│  │    Voiceover embedded in prompt → avatar lip sync             │  │
│  └───────────────┬───────────────────────────────────────────────┘  │
│                  │ failed scenes                                    │
│  ┌───────────────▼───────────┐                                      │
│  │ 🖼️  Imagen 4 Ultra         │                                      │
│  │    Fallback scene images  │                                      │
│  │    Ken Burns zoom effect  │                                      │
│  └───────────────┬───────────┘                                      │
│                  │                                                  │
│  ┌───────────────▼───────────┐                                      │
│  │ 🎞️  Video Assembly         │                                      │
│  │    moviepy                │                                      │
│  │    Subtitle overlay       │                                      │
│  │    Chirp3-HD audio track  │                                      │
│  │    Concatenate all scenes │                                      │
│  └───────────────────────────┘                                      │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT 4 — Quality Control                                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ ✅ Gemini 2.5 Flash — 7-criteria evaluation                   │    │
│  │    Accuracy · Tone · Engagement · Compliance                  │    │
│  │    Platform fit · Video script · Video visuals                │    │
│  │    Decision: Publish (score ≥ 7) or Modify                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OUTPUT                                                             │
│  📹 .mp4 video  ·  📝 Social post  ·  📊 QC report + scores        │
│  💾 Auto-saved to videos/influencer_YYYYMMDD_HHMMSS.mp4            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Google Cloud Components

| Component | Model / Service | Role in Pipeline |
|---|---|---|
| **Gemini 2.5 Flash** | `gemini-2.5-flash` | Trend detection, post generation, video brief, interleaved output, QC evaluation |
| **Google Search Grounding** | Gemini tool — `GoogleSearch()` | Real-time finance web results for live, cited content |
| **gemini-embedding-001** | `gemini-embedding-001` | Text embedding for semantic vector search |
| **Imagen 4 Ultra** | `imagen-4.0-ultra-generate-001` | Post image and Veo fallback scene images (9:16) |
| **Veo 3.1 Fast** | `veo-3.1-fast-generate-001` | Per-scene avatar video clips with lip sync |
| **Chirp3-HD TTS** | `en-US-Chirp3-HD-Aoede/Orus` | High-quality SSML voice synthesis |
| **Vertex AI** | `us-central1` | Platform hosting all generative AI models |

---

## Data Sources

| Source | Type | Content |
|---|---|---|
| Google Search Grounding | Live | Banking, taxes, scholarships, loans, OPT/CPT — always fresh |
| IRS Newswire RSS | RSS | Tax rules, nonresident aliens, ITIN, W-2 |
| CFPB Blog RSS | RSS | Consumer finance, student loan rights |
| NASFAA News RSS | RSS | Financial aid policy |
| NYT Business RSS | RSS | Student finance, economy |
| Prodigy / SoFi / Earnest / MPOWER | RSS | International student loan products |
| NYC Open Data | API | Job postings, CUNY, living wage |
| Tax Knowledge Seed | Static | 7 curated F1/J1 tax scenarios (W-2, ITIN, OPT, FICA) |

---

## Key Design Decisions

**Google Search Grounding as primary source**
Static RSS feeds go stale. Grounding queries Gemini with live Google Search, returning cited sources that are always current. This is the highest-signal input for Agent 2.

**Per-scene Veo generation with lip sync**
Rather than generating one long Veo clip and looping it, Agent 3 generates a separate Veo clip per storyboard scene with the voiceover text embedded in the prompt. This causes Veo to naturally animate the avatar's lips and body language to match each scene's dialogue.

**Parallel Veo generation**
Five scenes are generated concurrently (max 3 workers) using `ThreadPoolExecutor`, reducing total video generation time from ~10 minutes to ~3 minutes.

**Chirp3-HD replaces Veo audio**
Veo generates its own audio but Chirp3-HD supports SSML tags (`<emphasis>`, `<prosody>`, `<break>`) for precise tone and pacing control. The Chirp3-HD track replaces Veo's audio in final assembly.

**Fallback chain**
Every generative step has a fallback:
- Veo fails → Imagen 4 Ultra image + Ken Burns zoom effect
- Imagen 4 Ultra fails → Imagen 4 → Imagen 3
- QC parse fails → default Publish with score 7

**In-memory vector store**
No persistent infrastructure needed for the hackathon demo. All chunks are embedded and searched in-memory per run using cosine similarity with topic weight boosting.
