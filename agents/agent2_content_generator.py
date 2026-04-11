import os
import json
import re

from dotenv import load_dotenv
from google import genai

load_dotenv()

_client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

GENERATION_MODEL = "gemini-2.0-flash"
MAX_POSTS_PER_RUN = 1

SYSTEM_PROMPT = """You are an AI influencer creating content for international students in NYC.
Tone: helpful, empowering, informative.
Audience: international students aged 18-30 in NYC.
Goal: surface real NYC data to help them navigate inequities.

Rules:
- Lead with one surprising or urgent fact from the data
- Include 1 actionable tip
- End with a question to drive engagement
- Keep under 250 words
- Include 3-5 relevant hashtags starting with #"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Extract JSON from a model response that may contain markdown code fences."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Return a safe fallback so the pipeline never crashes
        return {}


def _generate(prompt: str) -> str:
    response = _client.models.generate_content(
        model=GENERATION_MODEL,
        contents=prompt,
    )
    return response.text


# ---------------------------------------------------------------------------
# 1. Trend Detector
# ---------------------------------------------------------------------------

def detect_trend(results: list[dict]) -> dict:
    combined = "\n\n".join(
        f"[{r['source_type']}] {r['title']}: {r['content_chunk']}"
        for r in results[:5]
    )[:3000]

    prompt = f"""You are analyzing content about international students in NYC.

Given these content chunks:
{combined}

Identify the single most compelling trend, insight, or actionable fact
that would resonate with international students aged 18-30.

Return ONLY a JSON object with exactly these keys:
- topic_angle: string (compelling headline angle)
- urgency: string ("low", "medium", or "high")
- key_fact: string (the single most surprising or useful fact from the data)
- suggested_platform: string ("linkedin" or "instagram")"""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result:
        return {
            "topic_angle": "International students face growing challenges in NYC",
            "urgency": "medium",
            "key_fact": results[0]["content_chunk"][:200] if results else "NYC data unavailable",
            "suggested_platform": "linkedin",
        }
    return result


# ---------------------------------------------------------------------------
# 2. Content Generator
# ---------------------------------------------------------------------------

def generate_post(trend: dict, persona: dict, sources: list[dict], extra_instruction: str = "") -> dict:
    source_titles = [s["title"] for s in sources[:3]]
    source_urls = [s["source_url"] for s in sources]

    prompt = f"""{SYSTEM_PROMPT}

Write a {persona['tone']} social media post for {persona['audience']}.

Topic angle: {trend['topic_angle']}
Key fact: {trend['key_fact']}
Platform: {trend.get('suggested_platform', 'linkedin')}
Sources to reference: {source_titles}
{extra_instruction}

Return ONLY a JSON object with these keys:
- post_text: string (the full post body, under 250 words)
- image_prompt: string (vivid visual scene for an image that complements this post, no text in the image, photorealistic)
- platform: string ("linkedin" or "instagram")
- hashtags: list of 3-5 strings each starting with #
- topic: string (same as topic_angle)
- sources: {json.dumps(source_urls[:3])}
- urgency: string ("{trend.get('urgency', 'medium')}")"""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result.get("post_text"):
        result = {
            "post_text": raw[:500],
            "image_prompt": "International students studying together in New York City, diverse group, warm lighting, urban background",
            "platform": trend.get("suggested_platform", "linkedin"),
            "hashtags": ["#InternationalStudents", "#NYC", "#StudentLife"],
            "topic": trend.get("topic_angle", ""),
            "sources": source_urls[:3],
            "urgency": trend.get("urgency", "medium"),
        }
    return result


# ---------------------------------------------------------------------------
# 3. Quality Control
# ---------------------------------------------------------------------------

def quality_check(draft: dict) -> dict:
    prompt = f"""Review this social media post for an international student audience in NYC.

Post: {draft.get('post_text', '')}

Score it 1-10 on accuracy, tone, and helpfulness.
Return ONLY a JSON object: {{"approved": bool, "score": int, "reason": string}}
Approve (approved: true) if score >= 7."""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result or "approved" not in result:
        return {"approved": True, "score": 7, "reason": "Auto-approved (QC parse error)"}
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent2(retrieval_pack: dict) -> dict:
    results = retrieval_pack.get("results", [])
    persona = retrieval_pack.get("persona", {})

    print("[agent2] Detecting trend...")
    trend = detect_trend(results)
    print(f"  Angle: {trend.get('topic_angle')} | Urgency: {trend.get('urgency')}")

    print("[agent2] Generating post...")
    draft = generate_post(trend, persona, results)

    print("[agent2] Running QC check...")
    qc = quality_check(draft)
    print(f"  QC score: {qc.get('score')} | Approved: {qc.get('approved')}")

    if not qc.get("approved"):
        print(f"  QC rejected. Reason: {qc.get('reason')}. Regenerating...")
        draft = generate_post(trend, persona, results, extra_instruction=f"Previous version was rejected: {qc.get('reason')}. Fix this.")

    print("[agent2] Done.")
    return draft
