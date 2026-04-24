# Streamlit → React migration (current state)

This repo now has:

- `backend/`: **FastAPI** wrapper around the existing Python agents
- `frontend/`: **React (Vite + TS)** UI that mirrors the Streamlit flow

## Run locally

### 1) Backend

Set env vars (same as before). At minimum:

- `GOOGLE_API_KEY`
- (optional) `GOOGLE_CLOUD_PROJECT`
- (optional) `GOOGLE_CLOUD_LOCATION`
- (optional) `NYC_OPEN_DATA_APP_TOKEN` (Agent 1 currently hits open endpoints; token can help reliability)

Then:

```bash
python -m uvicorn backend.server:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
copy .env.example .env
npm run dev
```

The UI will call the backend at `VITE_API_BASE` (defaults to `http://localhost:8000`).

## API contract (used by React)

- `GET /topics` → `{ topics: string[] }`
- `POST /generate/post` → `{ retrieval_pack, content_draft, final_output }`
  - `final_output.image_b64` contains the generated image (base64)
- `POST /generate/video_async` → `{ job_id }`
- `GET /jobs/{job_id}` → `{ status, result }`
  - `result.video_output.video_b64` is the MP4 (base64)
  - `result.qc_result` is the QC JSON

