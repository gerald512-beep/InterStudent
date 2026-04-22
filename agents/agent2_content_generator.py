import os
import json
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError

from audience_personalization import (
    effective_audience_line,
    effective_tone,
    persona_prompt_block,
)

load_dotenv()

_client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

GENERATION_MODEL = "gemini-2.5-flash"

# Best Chirp3-HD voice names by gender
CHIRP3_VOICES = {
    "female": "en-US-Chirp3-HD-Aoede",   # warm, natural female
    "male":   "en-US-Chirp3-HD-Orus",    # warm, conversational male
}

SYSTEM_PROMPT = """You are an AI influencer creating finance content for international students in NYC.
Tone: helpful, empowering, urgent where needed.
Audience: international students aged 18-30 in NYC (F1/J1 visa holders).
Goal: surface real data and help them navigate US financial systems.

Rules:
- Lead with one surprising or urgent fact
- Include 1-2 numbered actionable steps
- End with a strong call-to-action with a source link
- Include a closing engagement question
- Include 3-5 relevant hashtags starting with #
- Embed source URLs directly in the post body as clickable references"""


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
                print(f"[agent2] Rate limited, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# 1. Trend Detector
# ---------------------------------------------------------------------------

def detect_trend(results: list[dict], persona: dict | None = None) -> dict:
    combined = "\n\n".join(
        f"[{r['source_type']}] {r['title']}: {r['content_chunk']}"
        for r in results[:5]
    )[:3000]

    persona_hint = persona_prompt_block(persona)
    platform_hint = ""
    if persona and persona.get("platform_style"):
        platform_hint = (
            f"\nPrefer a platform angle aligned with: {persona.get('platform_style')}. "
            "Set suggested_platform to linkedin or instagram accordingly when it fits."
        )

    prompt = f"""You are analyzing finance content about international students in NYC.

{persona_hint}
{platform_hint}

Given these content chunks:
{combined}

Identify the single most compelling financial trend, insight, or actionable fact
that would help international students aged 18-30 navigate US money systems.

Return ONLY a JSON object with exactly these keys:
- topic_angle: string (compelling headline angle)
- urgency: string ("low", "medium", or "high")
- key_fact: string (the single most surprising or useful fact from the data)
- suggested_platform: string ("linkedin" or "instagram")
- primary_source_url: string (the most credible source URL from the data, or empty string)"""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result:
        return {
            "topic_angle": "International students are missing out on key financial benefits in NYC",
            "urgency": "medium",
            "key_fact": results[0]["content_chunk"][:200] if results else "NYC financial data unavailable",
            "suggested_platform": "linkedin",
            "primary_source_url": results[0].get("source_url", "") if results else "",
        }
    return result


# ---------------------------------------------------------------------------
# 2. Content Generator — platform-specific with CTA links
# ---------------------------------------------------------------------------

def generate_post(trend: dict, persona: dict, sources: list[dict], extra_instruction: str = "") -> dict:
    source_titles = [s["title"] for s in sources[:3]]
    source_urls = [s["source_url"] for s in sources if s.get("source_url")]
    primary_url = trend.get("primary_source_url") or (source_urls[0] if source_urls else "")
    platform = trend.get("suggested_platform", "linkedin")
    tone = effective_tone(persona)
    audience_line = effective_audience_line(persona)
    persona_block = persona_prompt_block(persona)

    if platform == "linkedin":
        format_instructions = """FORMAT FOR LINKEDIN:
- Line 1: Bold hook (surprising fact, under 15 words)
- Blank line
- 2-3 sentences of context
- Blank line
- Numbered actionable steps (2-3 steps)
- Blank line
- → Full guide: [embed primary_source_url here as plain text]
- Blank line
- Engagement question ending with a ?
- Blank line
- Hashtags on the last line"""
    else:
        format_instructions = """FORMAT FOR INSTAGRAM:
- Line 1: Emoji + bold punchy hook (max 10 words)
- 2-3 short sentences (emoji-accented)
- 👉 Link in bio for the full guide
- 📌 Save this post — you'll need it!
- Engagement question ending with ?
- Hashtags (5 max, on last line)"""

    cta_hint = ""
    if persona:
        cta_hint = (
            f"Primary CTA style requested: {persona.get('cta_preference', 'Visit resource links')}. "
            f"Risk tolerance: {persona.get('risk_tolerance', 'Balanced')} — keep claims responsible."
        )
        if persona.get("include_language_support") and persona.get("languages"):
            cta_hint += (
                f" Optionally note available languages for resources: {', '.join(persona['languages'])}."
            )

    prompt = f"""{SYSTEM_PROMPT}

{persona_block}

Write a {tone} social media post for {audience_line}.

Topic angle: {trend['topic_angle']}
Key fact: {trend['key_fact']}
Platform: {platform}
Primary source URL to embed: {primary_url}
Sources to reference: {source_titles}
{cta_hint}
{extra_instruction}

{format_instructions}

Return ONLY a JSON object with these keys:
- post_text: string (the complete formatted post body including CTA with embedded link)
- cta_links: list of strings (1-3 URLs embedded in the post for easy follower access)
- image_prompt: string (vivid photorealistic scene for Imagen 4, no text in image, NYC finance theme)
- platform: string ("{platform}")
- hashtags: list of 3-5 strings each starting with #
- topic: string (same as topic_angle)
- sources: {json.dumps(source_urls[:3])}
- urgency: string ("{trend.get('urgency', 'medium')}")"""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result.get("post_text"):
        result = {
            "post_text": f"{trend['key_fact']}\n\nHere's what to do:\n1. Check your tax status with your DSO\n2. Review your W-2 forms carefully\n\n→ Full guide: {primary_url}\n\nWhat financial challenge are you facing right now?\n\n#InternationalStudents #NYC #F1Visa #StudentFinance",
            "cta_links": [primary_url] if primary_url else [],
            "image_prompt": "Diverse international student reviewing financial documents in a modern NYC coffee shop, warm lighting, professional atmosphere",
            "platform": platform,
            "hashtags": ["#InternationalStudents", "#NYC", "#F1Visa", "#StudentFinance"],
            "topic": trend.get("topic_angle", ""),
            "sources": source_urls[:3],
            "urgency": trend.get("urgency", "medium"),
        }
    return result


# ---------------------------------------------------------------------------
# 3. Quality Control
# ---------------------------------------------------------------------------

def quality_check(draft: dict) -> dict:
    platform = draft.get("platform", "linkedin")
    prompt = f"""Review this {platform} social media post for international students in NYC.

Post: {draft.get('post_text', '')}

Score 1-10 on: accuracy, tone, CTA effectiveness, helpfulness.
Return ONLY a JSON object: {{"approved": bool, "score": int, "reason": string}}
Approve (approved: true) if score >= 7.
A strong CTA with an embedded link should push score higher."""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result or "approved" not in result:
        return {"approved": True, "score": 7, "reason": "Auto-approved (QC parse error)"}
    return result


# ---------------------------------------------------------------------------
# 4. Video Brief Generator — 5 scenes, SSML script, Veo-ready prompts
# ---------------------------------------------------------------------------

def generate_video_brief(trend: dict, draft: dict, persona: dict) -> dict:
    post_text = draft.get("post_text", "")
    platform = draft.get("platform", "linkedin")
    key_fact = trend.get("key_fact", "")
    topic = trend.get("topic_angle", "")
    persona_block = persona_prompt_block(persona)
    tone = effective_tone(persona)
    audience_line = effective_audience_line(persona)
    avatar_style = (persona or {}).get("avatar_style", "Friendly peer creator")

    prompt = f"""You are creating a 40-50 second multi-shot AI influencer video for international students in NYC.

{persona_block}

Topic: {topic}
Key fact: {key_fact}
Post summary: {post_text[:300]}
Platform: {platform}
Tone: {tone}
Audience: {audience_line}
Avatar style: {avatar_style} — reflect this in avatar_description and scene emotions.

Create a 5-scene video with a realistic AI avatar. Each scene is a different shot.

SCENE STRUCTURE:
- Scene 1 (8s): Avatar INTRO — wide establishing shot, direct to camera, warm welcome
- Scene 2 (9s): KEY FACT — medium closeup, avatar reacts with surprise/concern
- Scene 3 (9s): ACTIONABLE TIP — medium shot, avatar gestures/explains
- Scene 4 (8s): RESOURCE REVEAL — avatar points to info, NYC setting visible
- Scene 5 (8s): CALL TO ACTION + OUTRO — direct camera, warm close, save/follow CTA

VOICE SSML RULES:
- Use <break time="300ms"/> between thoughts
- Use <emphasis level="strong"> for key facts and numbers
- Use <prosody rate="slow"> for critical advice
- Use <prosody pitch="+2st"> for exciting/encouraging parts
- Keep natural rhythm — avoid robotic pacing
- Total script: 90-110 spoken words

Return ONLY a JSON object with these keys:
- ssml_script: string (FULL script in SSML, wrapped in <speak> tags, all 5 scenes concatenated)
- voice_gender: string ("female" or "male")
- storyboard: list of exactly 5 objects, each with:
    - scene: int (1-5)
    - camera_angle: string (e.g. "wide establishing shot", "medium closeup", "over-the-shoulder")
    - visual_prompt: string (detailed Veo/Imagen prompt: avatar appearance, setting, lighting, action, photorealistic, 9:16, no text)
    - voiceover: string (plain text portion of script for this scene — what the avatar says)
    - duration_seconds: int (7-10)
    - emotion: string (e.g. "warm and welcoming", "urgent and concerned", "encouraging")
- avatar_description: string (consistent appearance across all scenes: age, ethnicity, clothing, hair, personality)
- music_mood: string (e.g. "upbeat lo-fi", "calm inspiring", "energetic")"""

    raw = _generate(prompt)
    result = _parse_json_response(raw)

    if not result.get("ssml_script") or not result.get("storyboard"):
        fallback_script = f"""<speak>
  <prosody rate="medium">Hey, international students in NYC!</prosody>
  <break time="300ms"/>
  <emphasis level="strong">This is something most people don't know.</emphasis>
  <break time="400ms"/>
  {key_fact}
  <break time="400ms"/>
  <prosody rate="slow">Here's exactly what you need to do.</prosody>
  <break time="300ms"/>
  First, check with your Designated School Official.
  <break time="200ms"/>
  Second, keep copies of all your financial documents.
  <break time="400ms"/>
  <emphasis level="strong">Drop a comment below</emphasis> — what financial challenge are you navigating right now?
  <break time="300ms"/>
  <prosody pitch="+2st">Save this video and follow for more NYC student finance tips!</prosody>
</speak>"""
        avatar_desc = "Young woman, South Asian appearance, warm smile, casual blazer over a simple top, natural makeup, friendly and approachable, mid-20s"
        result = {
            "ssml_script": fallback_script,
            "voice_gender": "female",
            "avatar_description": avatar_desc,
            "music_mood": "upbeat lo-fi",
            "storyboard": [
                {
                    "scene": 1, "camera_angle": "wide establishing shot",
                    "visual_prompt": f"Photorealistic young South Asian woman, casual blazer, standing outdoors with NYC skyline in background, golden hour, speaking to camera, 9:16 vertical, no text",
                    "voiceover": "Hey, international students in NYC! This is something most people don't know.",
                    "duration_seconds": 8, "emotion": "warm and welcoming",
                },
                {
                    "scene": 2, "camera_angle": "medium closeup",
                    "visual_prompt": f"Photorealistic young South Asian woman, casual blazer, medium closeup, slightly raised eyebrows, animated expression, modern NYC cafe background, 9:16 vertical, no text",
                    "voiceover": key_fact[:120],
                    "duration_seconds": 9, "emotion": "urgent and informative",
                },
                {
                    "scene": 3, "camera_angle": "medium shot",
                    "visual_prompt": f"Photorealistic young South Asian woman, casual blazer, medium shot, gesturing with one hand while explaining, bright NYC street background, 9:16 vertical, no text",
                    "voiceover": "Here's exactly what you need to do. First, check with your DSO. Second, keep all your financial documents.",
                    "duration_seconds": 9, "emotion": "encouraging and clear",
                },
                {
                    "scene": 4, "camera_angle": "over-the-shoulder",
                    "visual_prompt": f"Photorealistic young South Asian woman, casual blazer, seen from behind looking at NYC skyline, then turning to camera, warm lighting, 9:16 vertical, no text",
                    "voiceover": "The resources are out there — you just need to know where to look.",
                    "duration_seconds": 8, "emotion": "reassuring",
                },
                {
                    "scene": 5, "camera_angle": "direct closeup",
                    "visual_prompt": f"Photorealistic young South Asian woman, casual blazer, direct camera closeup, warm smile, pointing at camera, NYC background blurred, 9:16 vertical, no text",
                    "voiceover": "Drop a comment below with your question. Save this video and follow for more NYC student finance tips!",
                    "duration_seconds": 8, "emotion": "excited and warm CTA",
                },
            ],
        }

    # Inject consistent avatar description into all scene visual prompts
    avatar_desc = result.get("avatar_description", "")
    if avatar_desc:
        for scene in result.get("storyboard", []):
            vp = scene.get("visual_prompt", "")
            if avatar_desc[:40].lower() not in vp.lower():
                scene["visual_prompt"] = f"{avatar_desc}, {vp}"

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent2(retrieval_pack: dict) -> dict:
    results = retrieval_pack.get("results", [])
    persona = retrieval_pack.get("persona", {})

    print("[agent2] Detecting trend...")
    trend = detect_trend(results, persona)
    print(f"  Angle: {trend.get('topic_angle')} | Urgency: {trend.get('urgency')}")

    print("[agent2] Generating platform-specific post with CTA...")
    draft = generate_post(trend, persona, results)

    # Ensure cta_links always has at least the primary source URL
    if not draft.get("cta_links"):
        primary_url = trend.get("primary_source_url", "")
        draft["cta_links"] = [primary_url] if primary_url else []

    print("[agent2] Running QC check...")
    qc = quality_check(draft)
    print(f"  QC score: {qc.get('score')} | Approved: {qc.get('approved')}")

    if not qc.get("approved"):
        print(f"  QC rejected: {qc.get('reason')}. Regenerating...")
        draft = generate_post(trend, persona, results,
                              extra_instruction=f"Previous rejected: {qc.get('reason')}. Fix this.")

    print("[agent2] Generating 5-scene video brief with SSML...")
    video_brief = generate_video_brief(trend, draft, persona)
    draft["video_brief"] = video_brief
    draft["audience_persona"] = persona

    print("[agent2] Done.")
    return draft
