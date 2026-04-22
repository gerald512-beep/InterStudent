# Dev 2 Tasks — Agent 2 + Creative Storyteller Output

**Time budget:** 4 hours  
**Your files:** `agents/agent2_content_generator.py`, `output/creative_storyteller.py`, `app.py`

---

## Hour-by-Hour Plan

| Time | Task |
|---|---|
| 0:00 – 0:30 | Setup: env, mock data, Gemini API test |
| 0:30 – 1:15 | Agent 2: Trend Detector |
| 1:15 – 2:00 | Agent 2: Content Generator (ADK agent) |
| 2:00 – 2:30 | Agent 2: QC self-review loop |
| 2:30 – 3:15 | Creative Storyteller: image + interleaved output |
| 3:15 – 3:45 | Streamlit demo UI |
| 3:45 – 4:00 | Full pipeline test + Cloud Run deploy |

---

## Important: Start with Mock Data

**Do not wait for Dev 1.** Start with the mock retrieval pack.

Create `tests/mock_retrieval_pack.json` immediately:

### Vibe Coding Prompt
```
Create tests/mock_retrieval_pack.json with this structure:
{
  "query_topic": "housing costs for international students NYC",
  "persona": {
    "niche": "International students in NYC",
    "audience": "International students aged 18-30 in NYC",
    "tone": "helpful, empowering, informative",
    "content_goal": "surface inequities and share practical resources"
  },
  "results": [
    {
      "id": "mock-001",
      "source_type": "nyc_open_data",
      "title": "NYC 311 Housing Complaint - Bronx",
      "content_chunk": "Multiple housing complaints filed in Bronx zip code 10458, common issues include heat and hot water violations affecting student-occupied buildings near Fordham University.",
      "published_at": "2025-11-01",
      "relevance_score": 0.87,
      "source_url": "https://data.cityofnewyork.us/resource/fhrw-4uyv",
      "tags": ["housing", "nyc_open_data", "international students NYC"]
    },
    {
      "id": "mock-002",
      "source_type": "article",
      "title": "International Students Face Higher Rent Burden in NYC",
      "content_chunk": "A 2024 report shows international students in NYC spend 68% of their stipend on rent, compared to 45% for domestic students, driven by inability to secure co-signers for leases.",
      "published_at": "2024-09-15",
      "relevance_score": 0.91,
      "source_url": "https://example.com/intl-students-rent",
      "tags": ["housing", "article", "international students NYC"]
    },
    {
      "id": "mock-003",
      "source_type": "nyc_open_data",
      "title": "CUNY Enrollment - International Students 2024",
      "content_chunk": "CUNY enrolled 12,400 international students in Fall 2024, a 15% increase from 2022. Largest cohorts from India, China, and Nigeria. Most concentrated at Baruch, City College, and Queens College.",
      "published_at": "2024-10-01",
      "relevance_score": 0.83,
      "source_url": "https://data.cityofnewyork.us/resource/kfnq-pz6f",
      "tags": ["CUNY", "nyc_open_data", "international students NYC"]
    }
  ]
}
```

---

## Task 1 — Setup + API Test (0:00–0:30)

### Steps
1. Copy the project structure from Dev 1 (or start fresh with the same structure)
2. Install dependencies: `pip install -r requirements.txt`
3. Set up `.env` with your `GOOGLE_API_KEY`
4. Test the Gemini API is working:

### Vibe Coding Prompt
```
Create a file tests/test_gemini.py that:
- Loads GOOGLE_API_KEY from .env using python-dotenv
- Calls google.generativeai with model "gemini-2.0-flash"
- Sends the prompt: "Say hello to international students in NYC in 1 sentence"
- Prints the response
- If it works, print "Gemini API OK"
```

---

## Task 2 — Trend Detector (0:30–1:15)

### Vibe Coding Prompt
```
Create a Python function detect_trend(results: list[dict]) -> dict
in agents/agent2_content_generator.py that:

- Takes the "results" list from retrieval_pack
- Combines all content_chunk fields into a single string (max 3000 chars total)
- Calls google.generativeai gemini-2.0-flash with this prompt:

  "You are analyzing content about international students in NYC.
   Given these content chunks: {combined_text}
   
   Identify the single most compelling trend, insight, or actionable fact
   that would resonate with international students aged 18-30.
   
   Return a JSON object with exactly these keys:
   - topic_angle: string (the main angle, e.g. 'Hidden housing costs hitting international students')
   - urgency: string ('low', 'medium', or 'high')
   - key_fact: string (the single most surprising or useful fact from the data)
   - suggested_platform: string ('linkedin' or 'instagram')"

- Parse the response as JSON
- Return the dict
- On parse error, return a safe default dict with urgency: "medium"
```

---

## Task 3 — Content Generator ADK Agent (1:15–2:00)

### Vibe Coding Prompt
```
Create an ADK agent in agents/agent2_content_generator.py using google-adk.

First, define a SYSTEM_PROMPT string:
"You are an AI influencer creating content for international students in NYC.
Tone: helpful, empowering, informative.
Audience: international students aged 18-30 in NYC.
Goal: surface real NYC data to help them navigate inequities.
Rules:
- Lead with one surprising or urgent fact from the data
- Include 1 actionable tip
- End with a question to drive engagement
- Keep under 250 words
- Include 3-5 relevant hashtags starting with #"

Then create a function generate_post(trend: dict, persona: dict, sources: list[dict]) -> dict
that calls gemini-2.0-flash with the system prompt and this user message:

"Write a {persona['tone']} social media post for {persona['audience']}.

Topic angle: {trend['topic_angle']}
Key fact: {trend['key_fact']}
Platform: {trend['suggested_platform']}
Sources to reference: {[s['title'] for s in sources[:3]]}

Return a JSON object with:
- post_text: string (the full post)
- image_prompt: string (vivid description for an image that complements this post, no text in image)
- platform: string
- hashtags: list of strings
- topic: string (same as topic_angle)
- sources: list of source_url strings from the sources provided"

Parse and return the JSON response.
```

---

## Task 4 — QC Self-Review (2:00–2:30)

### Vibe Coding Prompt
```
Create a function quality_check(draft: dict) -> dict in agent2_content_generator.py that:

- Calls gemini-2.0-flash with this prompt:
  "Review this social media post for international students in NYC.
   Post: {draft['post_text']}
   
   Score it 1-10 on accuracy, tone, and helpfulness.
   Return JSON: {approved: bool, score: int, reason: string}
   Approve if score >= 7."

- Returns {approved: bool, score: int, reason: str}

Then create the main run_agent2(retrieval_pack: dict) -> dict function that:
1. Calls detect_trend(retrieval_pack["results"])
2. Calls generate_post(trend, retrieval_pack["persona"], retrieval_pack["results"])
3. Calls quality_check(draft)
4. If not approved: calls generate_post again with reason appended to the prompt (one retry only)
5. Returns the final draft dict
```

---

## Task 5 — Creative Storyteller: Image + Output (2:30–3:15)

### Vibe Coding Prompt
```
Create output/creative_storyteller.py with a function generate_output(content_draft: dict) -> dict
that:

1. Generates an image using Vertex AI Imagen 3:
   - Import: from vertexai.preview.vision_models import ImageGenerationModel
   - Init vertexai with project and location from env vars GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION
   - Load model: ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
   - Generate 1 image with content_draft["image_prompt"], aspect_ratio "1:1"
   - Get image bytes from images[0]._image_bytes

2. Combine text and image using Gemini 2.0 Flash multimodal (interleaved):
   - Call genai.GenerativeModel("gemini-2.0-flash").generate_content() with:
     - A text prompt: "Finalize this social media post: {content_draft['post_text']}"  
     - The image bytes as: {"mime_type": "image/png", "data": image_bytes}
   - Get the final text from response.text

3. Return dict:
   {
     "final_text": string,
     "image_bytes": bytes,
     "platform": content_draft["platform"],
     "hashtags": content_draft["hashtags"],
     "sources": content_draft["sources"],
     "topic": content_draft["topic"]
   }

Handle vertexai errors gracefully: if image generation fails, return a placeholder
image_bytes of None and log the error. The pipeline should not crash.
```

---

## Task 6 — Streamlit Demo UI (3:15–3:45)

### Vibe Coding Prompt
```
Create app.py using Streamlit for a hackathon demo of an AI influencer for international students in NYC.

Layout:
- Title: "NYC International Student AI Influencer"
- Subtitle: "Powered by Google ADK + Gemini 2.0 Flash"
- Sidebar: show the architecture flow as text steps

Main area:
- Dropdown (st.selectbox) to pick a topic from this list:
  ["Housing costs for students in NYC", "Visa work restrictions (OPT/CPT)", 
   "CUNY enrollment trends", "Best neighborhoods for international students",
   "NYC job market for graduates"]
- A "Generate Post" button
- When clicked, show st.spinner for each pipeline stage:
  - "Retrieving NYC Open Data..."
  - "Detecting trending angle..."
  - "Generating content..."
  - "Creating image..."
- After completion, show:
  - Two columns: left = generated image (st.image), right = post text (st.markdown)
  - Hashtags below the post text
  - An expander "Data Sources Used" showing the list of source URLs

Import and call:
- agents/agent1_source_retrieval.retrieve(topic) 
- agents/agent2_content_generator.run_agent2(retrieval_pack)
- output/creative_storyteller.generate_output(content_draft)

Use st.session_state to cache results so re-renders don't re-run the pipeline.
```

---

## Task 7 — Cloud Run Deploy (3:45–4:00)

### Vibe Coding Prompt
```
Create a Dockerfile for this Python Streamlit app:
- Base image: python:3.11-slim
- Copy requirements.txt and install dependencies
- Copy all project files
- Expose port 8080
- CMD: streamlit run app.py --server.port=8080 --server.address=0.0.0.0

Then write the exact gcloud commands to deploy to Cloud Run:
1. Build the container: gcloud builds submit --tag gcr.io/{PROJECT_ID}/nyc-student-influencer
2. Deploy: gcloud run deploy nyc-student-influencer --image gcr.io/{PROJECT_ID}/nyc-student-influencer --platform managed --region us-central1 --allow-unauthenticated
   with env vars: GOOGLE_API_KEY, NYC_OPEN_DATA_APP_TOKEN, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
```

---

## Done Criteria

- [ ] `tests/mock_retrieval_pack.json` exists
- [ ] Gemini API test passes
- [ ] `run_agent2(mock_retrieval_pack)` returns a valid `content_draft`
- [ ] `generate_output(content_draft)` returns text + image (or graceful fallback)
- [ ] Streamlit UI runs locally: `streamlit run app.py`
- [ ] Full pipeline works end-to-end with real Agent 1 output
- [ ] Deployed to Cloud Run with a public URL
