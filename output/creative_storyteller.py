import os
import io

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

vertexai.init(project=_PROJECT, location=_LOCATION)

_client = genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)


# ---------------------------------------------------------------------------
# Image generation via Imagen 3
# ---------------------------------------------------------------------------

def generate_image(image_prompt: str) -> bytes | None:
    for model_id in ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001", "imagen-3.0-generate-001"]:
        try:
            model = ImageGenerationModel.from_pretrained(model_id)
            images = model.generate_images(
                prompt=image_prompt,
                number_of_images=1,
                aspect_ratio="9:16",
            )
            if not images:
                print(f"[storyteller] {model_id} returned no images (content filter). Trying fallback...")
                continue
            print(f"[storyteller] Image generated via {model_id}")
            return images[0]._image_bytes
        except Exception as exc:
            print(f"[storyteller] {model_id} failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Gemini interleaved output (text + image) — Creative Storyteller requirement
# ---------------------------------------------------------------------------

def generate_interleaved_output(content_draft: dict, image_bytes: bytes | None) -> str:
    platform = content_draft.get("platform", "linkedin")
    post_text = content_draft.get("post_text", "")
    hashtags = " ".join(content_draft.get("hashtags", []))

    prompt_text = f"""You are finalizing a {platform} post for international students in NYC.
Combine the text and the image context into a polished, ready-to-publish post.

Post text: {post_text}
Hashtags: {hashtags}

Return only the final post text, formatted for {platform}."""

    if image_bytes:
        mime_type = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
        contents = types.Content(
            role="user",
            parts=[
                types.Part(text=prompt_text),
                types.Part(
                    inline_data=types.Blob(mime_type=mime_type, data=image_bytes)
                ),
            ],
        )
    else:
        contents = prompt_text

    try:
        response = _client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )
        print("[storyteller] Interleaved output generated")
        return response.text
    except Exception as exc:
        print(f"[storyteller] Interleaved generation failed: {exc}")
        return f"{post_text}\n\n{hashtags}"


# ---------------------------------------------------------------------------
# Post formatter
# ---------------------------------------------------------------------------

def format_post(content_draft: dict, final_text: str, image_bytes: bytes | None) -> dict:
    platform = content_draft.get("platform", "linkedin")
    hashtags = " ".join(content_draft.get("hashtags", []))

    if platform == "linkedin":
        return {
            "header": content_draft.get("topic", "").upper(),
            "body": final_text,
            "hashtags": hashtags,
            "image_bytes": image_bytes,
            "sources": content_draft.get("sources", []),
            "platform": platform,
            "urgency": content_draft.get("urgency", "medium"),
        }
    else:
        return {
            "caption": f"{final_text}\n\n{hashtags}",
            "image_bytes": image_bytes,
            "sources": content_draft.get("sources", []),
            "platform": platform,
            "urgency": content_draft.get("urgency", "medium"),
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_output(content_draft: dict) -> dict:
    print("[storyteller] Generating image...")
    image_bytes = generate_image(content_draft.get("image_prompt", ""))

    print("[storyteller] Generating interleaved output...")
    final_text = generate_interleaved_output(content_draft, image_bytes)

    return format_post(content_draft, final_text, image_bytes)
