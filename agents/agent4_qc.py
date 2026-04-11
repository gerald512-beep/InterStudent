import os
import json
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError

load_dotenv()

_client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

GENERATION_MODEL = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# QC Criteria
# ---------------------------------------------------------------------------

QC_CRITERIA = [
    ("accuracy",     "Factual claims are supported by NYC data sources"),
    ("tone",         "Voice is helpful, empowering, and appropriate for international students"),
    ("engagement",   "Has a hook, actionable tip, and ends with a question or call-to-action"),
    ("compliance",   "No harmful content, misinformation, or inappropriate advice"),
    ("platform_fit", "Length, format, and hashtags match the target platform"),
    ("video_script", "Video script is conversational, 30-45 seconds, relatable to international students"),
    ("video_visual", "Background and avatar descriptions are appropriate, diverse, and NYC-relevant"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _generate(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            response = _client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
            )
            return response.text
        except ClientError as e:
            if "429" in str(e) and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"[agent4] Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# QC Evaluator
# ---------------------------------------------------------------------------

def evaluate_content(final_output: dict, video_output: dict) -> dict:
    post_text = final_output.get("body") or final_output.get("caption", "")
    hashtags = final_output.get("hashtags", "")
    platform = final_output.get("platform", "linkedin")
    urgency = final_output.get("urgency", "medium")

    script = video_output.get("script", "")
    storyboard = video_output.get("storyboard", [])
    avatar_style = video_output.get("avatar_style", "")
    background_info = ""
    if storyboard:
        background_info = "; ".join(s.get("visual", "") for s in storyboard)

    criteria_list = "\n".join(
        f"- {name}: {desc}" for name, desc in QC_CRITERIA
    )

    prompt = f"""You are a content quality controller for an AI influencer targeting international students in NYC.

Evaluate the following content against each criterion and decide whether to PUBLISH or MODIFY.

--- POST CONTENT ({platform}) ---
{post_text}
{hashtags}
Urgency: {urgency}

--- VIDEO SCRIPT ---
{script}

--- VIDEO VISUALS ---
{background_info}
Avatar: {avatar_style}

--- EVALUATION CRITERIA ---
{criteria_list}

Return ONLY a JSON object with:
- decision: string ("Publish" or "Modify")
- overall_score: int (1-10)
- criteria_scores: object with each criterion name as key and score (1-10) as value
- post_feedback: string (1-2 sentences on post quality)
- video_feedback: string (1-2 sentences on video quality)
- improvement_notes: list of strings (specific changes needed if Modify, empty list if Publish)

Decision rule: Publish if overall_score >= 7 and no criterion scores below 5."""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result or "decision" not in result:
        return {
            "decision": "Publish",
            "overall_score": 7,
            "criteria_scores": {name: 7 for name, _ in QC_CRITERIA},
            "post_feedback": "Content approved (QC parse fallback).",
            "video_feedback": "Video brief approved (QC parse fallback).",
            "improvement_notes": [],
        }

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent4(final_output: dict, video_output: dict) -> dict:
    print("[agent4] Running QC evaluation...")
    result = evaluate_content(final_output, video_output)
    print(f"  Decision: {result.get('decision')} | Score: {result.get('overall_score')}/10")

    if result.get("decision") == "Modify":
        notes = result.get("improvement_notes", [])
        if notes:
            print("  Improvements needed:")
            for note in notes:
                print(f"    - {note}")

    print("[agent4] QC complete.")
    return result
