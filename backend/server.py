import base64
import os
import threading
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables from repo-local `.env` when running locally.
# This keeps the React+FastAPI dev flow working without manual `setx`/shell exports.
try:
    from dotenv import load_dotenv  # type: ignore

    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(_repo_root, ".env"), override=False)
except Exception:
    # If python-dotenv isn't installed or the file doesn't exist, we fall back to OS env vars.
    pass


TOPICS: list[str] = [
    "Opening a US bank account as an F1 student in NYC",
    "Filing taxes with a W-2 as an F1/J1 visa student",
    "Scholarships and financial aid for international students NYC",
    "Building US credit history as an international student",
    "Student loans for international students (Prodigy, SoFi, MPOWER)",
    "OPT/CPT income and tax obligations",
    "Sending money home affordably from NYC",
]


def _b64(data: bytes | None) -> str | None:
    if not data:
        return None
    return base64.b64encode(data).decode("ascii")


class GeneratePostRequest(BaseModel):
    topic: str = Field(..., min_length=3)
    platform: Literal["linkedin", "instagram"] = "linkedin"


class GeneratePostResponse(BaseModel):
    retrieval_pack: dict[str, Any]
    content_draft: dict[str, Any]
    final_output: dict[str, Any]


class GenerateVideoRequest(BaseModel):
    content_draft: dict[str, Any]
    final_output: dict[str, Any]


class GenerateVideoResponse(BaseModel):
    video_output: dict[str, Any]
    qc_result: dict[str, Any] | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    error: str | None = None
    result: dict[str, Any] | None = None


_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _set_job(job_id: str, **patch: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id, {})
        job.update(patch)
        _jobs[job_id] = job


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        return _jobs.get(job_id)


app = FastAPI(title="InterStudent API", version="0.1.0")

# Vite may start on varying ports (5173, 5174, 5175, ...). Also, `localhost` and `127.0.0.1`
# are different browser origins, so we allow both in dev by default.
#
# You can override this completely via CORS_ALLOW_ORIGINS="http://localhost:5173,https://..."
_DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"
_cors_env = os.environ.get("CORS_ALLOW_ORIGINS")
_allow_origins = [o.strip() for o in (_cors_env or _DEFAULT_CORS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$" if not _cors_env else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/topics")
def list_topics() -> dict[str, Any]:
    return {"topics": TOPICS}


@app.post("/generate/post", response_model=GeneratePostResponse)
def generate_post(req: GeneratePostRequest) -> GeneratePostResponse:
    try:
        from agents.agent1_source_retrieval import retrieve
        from agents.agent2_content_generator import run_agent2
        from output.creative_storyteller import generate_output

        retrieval_pack = retrieve(req.topic)
        content_draft = run_agent2(retrieval_pack, forced_platform=req.platform)
        content_draft["platform"] = req.platform

        # Provide a fast baseline response first. Full image generation (Imagen)
        # can take a long time or hang in some local environments.
        hashtags = " ".join(content_draft.get("hashtags", []))
        final_output: dict[str, Any] = {
            "body": content_draft.get("post_text", ""),
            "hashtags": hashtags,
            "sources": content_draft.get("sources", []),
            "platform": req.platform,
            "urgency": content_draft.get("urgency", "medium"),
        }

        # Try to run the full creative storyteller with a time budget.
        timeout_s = float(os.environ.get("POST_RENDER_TIMEOUT_SECONDS", "35"))
        result_box: dict[str, Any] = {"ok": False, "value": None, "error": None}

        def _work():
            try:
                result_box["value"] = generate_output(content_draft)
                result_box["ok"] = True
            except Exception as exc:  # pragma: no cover
                result_box["error"] = str(exc)

        t = threading.Thread(target=_work, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        if result_box["ok"] and isinstance(result_box["value"], dict):
            final_output = result_box["value"]
    except KeyError as exc:
        # Most common: missing GOOGLE_API_KEY / GCP env vars
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Convert bytes to base64 for JSON transport
    if final_output.get("image_bytes"):
        final_output["image_b64"] = _b64(final_output.get("image_bytes"))
        final_output.pop("image_bytes", None)

    return GeneratePostResponse(
        retrieval_pack=retrieval_pack,
        content_draft=content_draft,
        final_output=final_output,
    )


@app.post("/generate/video_async")
def generate_video_async(req: GenerateVideoRequest) -> dict[str, str]:
    """
    Video generation can take minutes. This endpoint starts work in a thread and returns job_id.
    Poll /jobs/{job_id} to retrieve the result.
    """
    job_id = str(uuid.uuid4())
    _set_job(job_id, status="queued", error=None, result=None)

    def _work():
        try:
            _set_job(job_id, status="running")

            from agents.agent3_video_generator import run_agent3
            from agents.agent4_qc import run_agent4

            video_output = run_agent3(req.content_draft)
            if video_output.get("video_bytes"):
                video_output["video_b64"] = _b64(video_output.get("video_bytes"))
                video_output.pop("video_bytes", None)
            if video_output.get("thumbnail_bytes"):
                video_output["thumbnail_b64"] = _b64(video_output.get("thumbnail_bytes"))
                video_output.pop("thumbnail_bytes", None)

            qc = run_agent4(req.final_output, video_output or {})
            _set_job(job_id, status="done", result={"video_output": video_output, "qc_result": qc})
        except Exception as exc:
            _set_job(job_id, status="error", error=str(exc))

    threading.Thread(target=_work, daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = _get_job(job_id)
    if not job:
        return JobStatusResponse(job_id=job_id, status="error", error="job_not_found", result=None)
    return JobStatusResponse(
        job_id=job_id,
        status=job.get("status", "error"),
        error=job.get("error"),
        result=job.get("result"),
    )

