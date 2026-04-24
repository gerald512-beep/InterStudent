# InterStudent Backend (FastAPI)

## Run

```bash
python -m uvicorn backend.server:app --reload --port 8000
```

## Endpoints

- `GET /health`
- `GET /topics`
- `POST /generate/post` → returns `retrieval_pack`, `content_draft`, and `final_output` (with `image_b64`)
- `POST /generate/video_async` → returns `{ job_id }` (poll job status)
- `GET /jobs/{job_id}` → returns `{ status, result }` where result includes `video_output.video_b64` and `qc_result`

