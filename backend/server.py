import base64
import json
import os
import re
import threading
import uuid
from pathlib import Path
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


_GROUNDING_URL_RE = re.compile(
    r'\[([^\]]+)\]\(https?://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[^\)]+\)'
)
_BARE_GROUNDING_RE = re.compile(
    r'https?://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/\S+'
)


def _clean_post_text(text: str) -> str:
    """Remove Google Search Grounding redirect URLs from post body."""
    text = _GROUNDING_URL_RE.sub(r'\1', text)   # [label](redirect url) → label
    text = _BARE_GROUNDING_RE.sub('', text)      # bare redirect url → removed
    return text.strip()


def _sanitize(obj: Any) -> Any:
    """Recursively convert bytes/numpy arrays to JSON-safe types."""
    if isinstance(obj, bytes):
        return _b64(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
    except ImportError:
        pass
    return obj


_AVATARS_DIR = Path(__file__).parent.parent / "avatars"
_CANONICAL_AVATAR_PATH = _AVATARS_DIR / "canonical.json"


class AvatarGenerateRequest(BaseModel):
    description: str


class AvatarSaveRequest(BaseModel):
    description: str
    image_base64: str
    mime_type: str = "image/png"


class GeneratePostRequest(BaseModel):
    topic: str = Field(..., min_length=3)
    platform: Literal["linkedin", "instagram"] = "linkedin"
    canonical_avatar: dict | None = None  # { description, image_base64, mime_type }


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


class GenerateImageRequest(BaseModel):
    image_prompt: str
    avatar_description: str = ""


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


@app.get("/avatar")
def get_avatar() -> dict[str, Any]:
    if _CANONICAL_AVATAR_PATH.exists():
        try:
            data = json.loads(_CANONICAL_AVATAR_PATH.read_text(encoding="utf-8"))
            return data
        except Exception:
            pass
    return {"description": "", "image_base64": "", "mime_type": "image/png"}


@app.post("/avatar/generate-image")
def avatar_generate_image(req: AvatarGenerateRequest) -> dict[str, Any]:
    try:
        from vertexai.preview.vision_models import ImageGenerationModel
        import vertexai
        _p = os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026")
        _l = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        vertexai.init(project=_p, location=_l)
        image_bytes = None
        for model_id in ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001", "imagen-3.0-generate-001"]:
            try:
                model = ImageGenerationModel.from_pretrained(model_id)
                images = model.generate_images(
                    prompt=req.description,
                    number_of_images=1,
                    aspect_ratio="9:16",
                )
                if images:
                    image_bytes = images[0]._image_bytes
                    break
            except Exception:
                continue
        if not image_bytes:
            raise HTTPException(status_code=500, detail="Imagen returned no image (content filter or quota)")
        mime = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
        return {"image_base64": _b64(image_bytes), "mime_type": mime}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/avatar/save")
def avatar_save(req: AvatarSaveRequest) -> dict[str, Any]:
    try:
        _AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"description": req.description, "image_base64": req.image_base64, "mime_type": req.mime_type}
        _CANONICAL_AVATAR_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate/image")
def generate_image_only(req: GenerateImageRequest) -> dict[str, Any]:
    try:
        from output.creative_storyteller import generate_image
        image_bytes = generate_image(req.image_prompt, avatar_description=req.avatar_description)
        if not image_bytes:
            raise HTTPException(status_code=500, detail="Imagen returned no image")
        mime = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
        return {"image_b64": _b64(image_bytes), "mime_type": mime}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate/post", response_model=GeneratePostResponse)
def generate_post(req: GeneratePostRequest) -> GeneratePostResponse:
    try:
        from agents.agent1_source_retrieval import retrieve
        from agents.agent2_content_generator import run_agent2
        from output.creative_storyteller import generate_output

        retrieval_pack = retrieve(req.topic)
        content_draft = run_agent2(retrieval_pack, forced_platform=req.platform)
        content_draft["platform"] = req.platform

        # Inject canonical avatar into content_draft if provided
        if req.canonical_avatar and req.canonical_avatar.get("description"):
            avatar_desc = req.canonical_avatar["description"]
            video_brief = content_draft.setdefault("video_brief", {})
            video_brief["avatar_description"] = avatar_desc
            # Prepend avatar description to each scene's visual_prompt
            for scene in video_brief.get("storyboard", []):
                vp = scene.get("visual_prompt", "")
                if avatar_desc[:40].lower() not in vp.lower():
                    scene["visual_prompt"] = f"{avatar_desc[:300]}, {vp}"
            # Prepend to post image_prompt for Imagen
            existing_img_prompt = content_draft.get("image_prompt", "")
            content_draft["image_prompt"] = f"{avatar_desc[:300]}. {existing_img_prompt}"
            # Store decoded bytes for Veo reference_images
            try:
                content_draft["avatar_reference_image_bytes"] = base64.b64decode(
                    req.canonical_avatar["image_base64"]
                )
            except Exception:
                pass

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

    # Strip grounding redirect URLs from post text
    for field in ("body", "caption"):
        if final_output.get(field):
            final_output[field] = _clean_post_text(final_output[field])

    # Convert bytes to base64 for JSON transport
    if final_output.get("image_bytes"):
        raw = final_output["image_bytes"]
        final_output["image_b64"] = _b64(raw)
        final_output["image_mime"] = "image/jpeg" if raw[:2] == b"\xff\xd8" else "image/png"
        final_output.pop("image_bytes", None)

    return GeneratePostResponse(
        retrieval_pack=_sanitize(retrieval_pack),
        content_draft=_sanitize(content_draft),
        final_output=_sanitize(final_output),
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
            video_output.pop("audio_bytes", None)  # frontend doesn't need raw MP3

            qc = run_agent4(req.final_output, video_output or {})
            _set_job(job_id, status="done", result=_sanitize({"video_output": video_output, "qc_result": qc}))
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

