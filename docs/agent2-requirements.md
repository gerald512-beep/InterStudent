# Agent 2: Trend Content Generator — Requirements

**Owner:** Dev 2  
**File:** `agents/agent2_content_generator.py`  
**Input:** `retrieval_pack` JSON from Agent 1  
**Output:** `content_draft` JSON → consumed by Creative Storyteller

---

## Purpose

Takes retrieved NYC data chunks and generates a trend-aware, audience-specific social media post draft using Gemini 2.0 Flash via Google ADK.

---

## Implementation: Google ADK Agent

Use the Google Agent Development Kit to define this as a proper ADK agent.

```python
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm  # or use Gemini directly

content_agent = Agent(
    name="trend_content_generator",
    model="gemini-2.0-flash",
    description="Generates trend-aware social media content for international students in NYC",
    instruction=SYSTEM_PROMPT,
    tools=[generate_content_tool]
)
```

---

## Sub-components

### 1. Trend Detector

**Input:** list of retrieved content chunks from `retrieval_pack`  
**Task:** Identify the single most compelling angle or trend across the chunks  
**Implementation:** Gemini prompt call (not a separate agent — one function call)

```
Prompt template:
"Given the following content chunks about international students in NYC,
identify the single most compelling trend, insight, or actionable fact
that would resonate with international students aged 18-30.
Return: topic_angle (string), urgency (low/medium/high), key_fact (string)"
```

### 2. Content Generator

**Input:** `topic_angle` + `key_fact` + `persona` from retrieval_pack  
**Task:** Write the social media post  
**Implementation:** ADK agent with structured output

#### System Prompt

```
You are an AI influencer creating content for international students in NYC.
Your tone is: helpful, empowering, and informative.
Your audience: international students aged 18-30 in NYC.
Your goal: surface real NYC data to help them navigate inequities.

Always:
- Lead with one surprising or urgent fact from the data
- Include 1 actionable tip
- End with a question to drive engagement
- Keep under 250 words
- Include 3-5 relevant hashtags
```

#### Output Schema

```python
{
    "post_text": str,       # The full post body
    "image_prompt": str,    # Prompt for Imagen 3 (visual description)
    "platform": str,        # "linkedin" or "instagram"
    "hashtags": list[str],
    "topic": str,           # The trend angle used
    "sources": list[str],   # URLs from retrieval_pack
    "urgency": str          # low | medium | high
}
```

### 3. Quota Controller

- Simple counter: max 1 post per pipeline run for MVP
- Prevents runaway generation during demo
- Hardcoded limit, no database needed

```python
MAX_POSTS_PER_RUN = 1
```

---

## Quality Control (Self-Review)

After content is generated, run a second Gemini call to review it:

```
Prompt:
"Review this social media post for an international student audience in NYC.
Score it 1-10 on: accuracy, tone, helpfulness.
If score < 7, return: {approved: false, reason: string}
If score >= 7, return: {approved: true}"
```

If `approved: false`, regenerate once with the rejection reason appended to the prompt.  
If second attempt also fails, pass it through with a warning flag.

---

## Full Function Flow

```python
def run_agent2(retrieval_pack: dict) -> dict:
    # 1. Detect trend from chunks
    trend = detect_trend(retrieval_pack["results"])

    # 2. Generate post draft
    draft = generate_post(
        trend=trend,
        persona=retrieval_pack["persona"],
        sources=retrieval_pack["results"]
    )

    # 3. QC check
    qc_result = quality_check(draft)
    if not qc_result["approved"]:
        draft = regenerate_post(draft, qc_result["reason"])

    return draft  # content_draft JSON
```

---

## Environment Variables Required

```
GOOGLE_API_KEY=
```

---

## Dependencies

```
google-adk
google-generativeai
```

---

## Interface Contract with Agent 1

Agent 2 expects this exact input structure from Agent 1:

```json
{
  "query_topic": "string",
  "persona": {
    "niche": "string",
    "audience": "string",
    "tone": "string",
    "content_goal": "string"
  },
  "results": [
    {
      "id": "string",
      "source_type": "string",
      "title": "string",
      "content_chunk": "string",
      "published_at": "string",
      "relevance_score": 0.0,
      "source_url": "string",
      "tags": ["string"]
    }
  ]
}
```

If Agent 1 is not ready, Dev 2 can use the mock file at `tests/mock_retrieval_pack.json` to develop independently.
