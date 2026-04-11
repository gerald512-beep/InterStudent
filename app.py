import json
import io
import re
import streamlit as st
from PIL import Image

from agents.agent1_source_retrieval import retrieve
from agents.agent2_content_generator import run_agent2
from agents.agent3_video_generator import run_agent3
from agents.agent4_qc import run_agent4
from output.creative_storyteller import generate_output

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NYC International Student AI Influencer",
    page_icon="🗽",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

for key, default in {
    "phase": "idle",          # idle | post_done | video_done
    "retrieval_pack": None,
    "content_draft": None,
    "final_output": None,
    "video_output": None,
    "qc_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Pipeline")
    st.markdown("""
**Agent 1 — Source Retrieval**
- Google Search Grounding (live)
- Finance RSS (IRS, CFPB, loans)
- NYC Open Data (supplementary)
- Tax scenario knowledge seed

↓

**Agent 2 — Content Generator**
- Platform-specific CTA with links
- Gemini trend detection
- 5-scene SSML video brief

↓

**Creative Storyteller**
- Imagen 4 image generation
- Gemini interleaved output

↓

**Storyboard Editor**
- Review & edit scenes before video

↓

**Agent 3 — Video Generator**
- Veo 3.1 hero clip
- Imagen 4 Ultra per scene
- Chirp3-HD SSML voice
- Multi-shot + Ken Burns assembly

↓

**Agent 4 — Quality Control**
- 7-criteria Gemini evaluation
- Publish / Modify decision
    """)
    st.divider()
    st.caption("Powered by Veo 3.1 · Imagen 4 · Chirp3-HD · Gemini 2.5 Flash")
    st.caption("NYC Build With AI Hackathon 2026")
    st.divider()

    # --- Step status icons ---
    st.markdown("**Status**")
    _step_keys   = ["agent1", "agent2", "storyteller", "agent3", "agent4"]
    _step_labels = {
        "agent1":      "Agent 1 — Source Retrieval",
        "agent2":      "Agent 2 — Content Generator",
        "storyteller": "Creative Storyteller",
        "agent3":      "Agent 3 — Video Generator",
        "agent4":      "Agent 4 — Quality Control",
    }
    _step_icons  = {"idle": "⬜", "running": "🔄", "done": "✅", "error": "❌"}
    _slots = {k: st.empty() for k in _step_keys}
    for k in _step_keys:
        _slots[k].markdown(f"{_step_icons['idle']} {_step_labels[k]}")


def _set_step(key: str, state: str):
    _slots[key].markdown(f"{_step_icons[state]} {_step_labels[key]}")


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("NYC International Student AI Influencer")
st.subheader("Personal finance guidance — built on live NYC data + Google AI")

TOPICS = [
    "Opening a US bank account as an F1 student in NYC",
    "Filing taxes with a W-2 as an F1/J1 visa student",
    "Scholarships and financial aid for international students NYC",
    "Building US credit history as an international student",
    "Student loans for international students (Prodigy, SoFi, MPOWER)",
    "OPT/CPT income and tax obligations",
    "Sending money home affordably from NYC",
]

topic    = st.selectbox("Topic:", TOPICS)
platform = st.radio("Platform:", ["linkedin", "instagram"], horizontal=True)

col_btn1, col_btn2 = st.columns([1, 1])
with col_btn1:
    phase1_btn = st.button(
        "Generate Post + Storyboard",
        type="primary",
        use_container_width=True,
        disabled=(st.session_state.phase == "running"),
    )
with col_btn2:
    reset_btn = st.button("Reset", use_container_width=True)

if reset_btn:
    for key in ["phase", "retrieval_pack", "content_draft", "final_output", "video_output", "qc_result"]:
        st.session_state[key] = "idle" if key == "phase" else None
    for k in _step_keys:
        _slots[k].markdown(f"{_step_icons['idle']} {_step_labels[k]}")
    st.rerun()

# ---------------------------------------------------------------------------
# PHASE 1 — Post + Storyboard generation
# ---------------------------------------------------------------------------

if phase1_btn:
    st.session_state.phase = "running"
    st.divider()
    with st.status("Generating post and storyboard...", expanded=True) as status:

        _set_step("agent1", "running")
        st.write("Agent 1 — Fetching live finance data via Google Search Grounding...")
        try:
            st.session_state.retrieval_pack = retrieve(topic)
            st.write(f"Retrieved {len(st.session_state.retrieval_pack['results'])} sources")
            _set_step("agent1", "done")
        except Exception as e:
            _set_step("agent1", "error")
            st.error(f"Agent 1 failed: {e}")
            st.stop()

        _set_step("agent2", "running")
        st.write("Agent 2 — Detecting trend, generating post + 5-scene storyboard...")
        try:
            draft = run_agent2(st.session_state.retrieval_pack)
            draft["platform"] = platform
            st.session_state.content_draft = draft
            st.write(f"Trend: {draft.get('topic', '')}")
            _set_step("agent2", "done")
        except Exception as e:
            _set_step("agent2", "error")
            st.error(f"Agent 2 failed: {e}")
            st.stop()

        _set_step("storyteller", "running")
        st.write("Creative Storyteller — Generating post image...")
        try:
            st.session_state.final_output = generate_output(st.session_state.content_draft)
            _set_step("storyteller", "done")
        except Exception as e:
            _set_step("storyteller", "error")
            st.error(f"Creative Storyteller failed: {e}")
            st.stop()

        st.session_state.phase = "post_done"
        status.update(label="Post ready — review your storyboard below!", state="complete")

# ---------------------------------------------------------------------------
# Show post output (after phase 1)
# ---------------------------------------------------------------------------

if st.session_state.phase in ("post_done", "video_done") and st.session_state.final_output:
    final_output   = st.session_state.final_output
    content_draft  = st.session_state.content_draft

    st.divider()
    urgency_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
        final_output.get("urgency", "medium"), "🟡"
    )
    st.markdown(f"### {urgency_color} {content_draft.get('topic', topic)}")

    col1, col2 = st.columns([1, 1])
    with col1:
        image_bytes = final_output.get("image_bytes")
        if image_bytes:
            st.image(Image.open(io.BytesIO(image_bytes)), caption="Imagen 4 · Generated image", use_container_width=True)
        else:
            st.info("Image unavailable — check Vertex AI credentials.")
    with col2:
        body = final_output.get("body") or final_output.get("caption", "")
        st.markdown(body)
        st.markdown(f"**{final_output.get('hashtags', '')}**")
        cta_links = content_draft.get("cta_links", [])
        if cta_links:
            st.markdown("**Links featured in this post:**")
            for link in cta_links:
                st.markdown(f"- {link}")

    with st.expander("Data sources used"):
        for url in final_output.get("sources", []):
            st.markdown(f"- {url}")

# ---------------------------------------------------------------------------
# STORYBOARD EDITOR (after phase 1, before phase 2)
# ---------------------------------------------------------------------------

if st.session_state.phase in ("post_done", "video_done") and st.session_state.content_draft:
    video_brief = st.session_state.content_draft.get("video_brief", {})
    storyboard  = video_brief.get("storyboard", [])

    if storyboard:
        st.divider()
        st.markdown("### Storyboard Editor")
        st.caption("Review and edit each scene before generating the video. Changes here are sent directly to Agent 3.")

        avatar_desc = video_brief.get("avatar_description", "")
        voice_gender = video_brief.get("voice_gender", "female")
        music_mood   = video_brief.get("music_mood", "")

        meta_col1, meta_col2, meta_col3 = st.columns(3)
        with meta_col1:
            st.markdown(f"**Avatar:** {avatar_desc[:80]}{'...' if len(avatar_desc) > 80 else ''}")
        with meta_col2:
            st.markdown(f"**Voice:** Chirp3-HD · {voice_gender}")
        with meta_col3:
            st.markdown(f"**Music mood:** {music_mood}")

        st.markdown("---")

        edited_scenes = []
        for i, scene in enumerate(storyboard):
            scene_num = scene.get("scene", i + 1)
            with st.expander(
                f"Scene {scene_num} — {scene.get('camera_angle', '')} · {scene.get('emotion', '')}",
                expanded=(i == 0),
            ):
                sc1, sc2 = st.columns([1, 1])
                with sc1:
                    new_visual = st.text_area(
                        "Visual prompt (Veo / Imagen 4)",
                        value=scene.get("visual_prompt", ""),
                        height=120,
                        key=f"visual_{i}",
                    )
                with sc2:
                    new_voiceover = st.text_area(
                        "Voiceover (spoken text)",
                        value=scene.get("voiceover", ""),
                        height=120,
                        key=f"voice_{i}",
                    )
                new_duration = st.slider(
                    "Duration (seconds) — Veo clips cap at 8s",
                    min_value=5, max_value=12,
                    value=int(scene.get("duration_seconds", 8)),
                    key=f"dur_{i}",
                )

                edited_scenes.append({
                    **scene,
                    "visual_prompt": new_visual,
                    "voiceover": new_voiceover,
                    "duration_seconds": new_duration,
                })

        # SSML script preview
        with st.expander("Full SSML script (editable)"):
            ssml_key = "ssml_edit"
            if ssml_key not in st.session_state:
                st.session_state[ssml_key] = video_brief.get("ssml_script", "")
            edited_ssml = st.text_area(
                "SSML script",
                value=st.session_state[ssml_key],
                height=200,
                key="ssml_textarea",
            )

        # Generate video button
        if st.session_state.phase == "post_done":
            st.divider()
            gen_video_btn = st.button(
                "Generate AI Influencer Video",
                type="primary",
                use_container_width=True,
            )
        else:
            gen_video_btn = False

        # -----------------------------------------------------------------------
        # PHASE 2 — Video generation
        # -----------------------------------------------------------------------

        if gen_video_btn:
            # Push edits back into content_draft
            st.session_state.content_draft["video_brief"]["storyboard"] = edited_scenes
            st.session_state.content_draft["video_brief"]["ssml_script"] = edited_ssml

            st.divider()
            with st.status("Generating AI influencer video...", expanded=True) as vstatus:
                _set_step("agent3", "running")
                st.write("Agent 3 — Veo 3.1 hero clip + Imagen 4 Ultra scenes + Chirp3-HD voice...")
                try:
                    st.session_state.video_output = run_agent3(st.session_state.content_draft)
                    used_veo = st.session_state.video_output.get("used_veo", False)
                    msg = "Video assembled" + (" (Veo 3.1 hero clip included)" if used_veo else " (Imagen 4 Ultra multi-shot)")
                    st.write(msg)
                    _set_step("agent3", "done")
                except Exception as e:
                    _set_step("agent3", "error")
                    st.warning(f"Agent 3 failed: {e}")
                    st.session_state.video_output = {}

                _set_step("agent4", "running")
                st.write("Agent 4 — Quality control evaluation...")
                try:
                    st.session_state.qc_result = run_agent4(
                        st.session_state.final_output,
                        st.session_state.video_output or {},
                    )
                    _set_step("agent4", "done")
                except Exception as e:
                    _set_step("agent4", "error")
                    st.warning(f"Agent 4 QC failed: {e}")

                st.session_state.phase = "video_done"
                vstatus.update(label="Video ready!", state="complete")

# ---------------------------------------------------------------------------
# Video output (after phase 2)
# ---------------------------------------------------------------------------

if st.session_state.phase == "video_done" and st.session_state.video_output:
    video_output = st.session_state.video_output

    st.divider()
    st.markdown("### AI Influencer Video")

    used_veo = video_output.get("used_veo", False)
    if used_veo:
        st.caption("Hero clip generated with Veo 3.1 · Scenes with Imagen 4 Ultra · Voice by Chirp3-HD")
    else:
        st.caption("Scenes generated with Imagen 4 Ultra · Ken Burns effect · Voice by Chirp3-HD")

    vcol1, vcol2 = st.columns([1, 1])
    with vcol1:
        if video_output.get("video_bytes"):
            st.video(video_output["video_bytes"])
            st.download_button(
                label="Download video (.mp4)",
                data=video_output["video_bytes"],
                file_name="influencer_video.mp4",
                mime="video/mp4",
                use_container_width=True,
            )
        elif video_output.get("thumbnail_bytes"):
            tb = video_output["thumbnail_bytes"]
            # Only treat as image if it looks like PNG or JPEG (not MP4 video bytes)
            is_image = tb[:2] == b"\xff\xd8" or tb[:4] == b"\x89PNG"
            if is_image:
                st.image(
                    Image.open(io.BytesIO(tb)),
                    caption="Background (Imagen 4 Ultra)",
                    use_container_width=True,
                )
                st.info("Video encoding failed — showing scene image")
            else:
                st.info("Video unavailable")
        else:
            st.info("Video unavailable")

    with vcol2:
        st.markdown("**Script (SSML)**")
        ssml = video_output.get("script", "")
        # Show clean version without XML tags
        clean_script = re.sub(r"<[^>]+>", "", ssml).strip()
        st.markdown(f"_{clean_script}_")

        vb = st.session_state.content_draft.get("video_brief", {})
        st.markdown(f"**Avatar:** {vb.get('avatar_description', '')[:120]}")
        st.markdown(f"**Voice:** Chirp3-HD · {vb.get('voice_gender', 'female')}")

    # QC panel
    if st.session_state.qc_result:
        qc = st.session_state.qc_result
        st.divider()
        st.markdown("### Quality Control")

        decision = qc.get("decision", "Publish")
        score = qc.get("overall_score", 0)
        color = "green" if decision == "Publish" else "orange"
        st.markdown(
            f"<h4 style='color:{color}'>Decision: {decision} &nbsp; ({score}/10)</h4>",
            unsafe_allow_html=True,
        )

        qc1, qc2 = st.columns(2)
        with qc1:
            st.markdown("**Post feedback**")
            st.write(qc.get("post_feedback", ""))
        with qc2:
            st.markdown("**Video feedback**")
            st.write(qc.get("video_feedback", ""))

        criteria = qc.get("criteria_scores", {})
        if criteria:
            with st.expander("Criteria scores"):
                cols = st.columns(3)
                for idx, (k, v) in enumerate(criteria.items()):
                    cols[idx % 3].metric(k.replace("_", " ").title(), f"{v}/10")

        notes = qc.get("improvement_notes", [])
        if notes:
            with st.expander("Improvements needed"):
                for note in notes:
                    st.markdown(f"- {note}")

    # Raw JSON for judges
    with st.expander("Raw pipeline output (for judges)"):
        rp = st.session_state.retrieval_pack or {}
        cd = st.session_state.content_draft or {}
        judge_data = {
            "retrieval_summary": {
                "query": rp.get("query_topic", ""),
                "results_count": len(rp.get("results", [])),
                "top_result": rp.get("results", [{}])[0] if rp.get("results") else {},
            },
            "post": {k: v for k, v in cd.items() if k not in ("video_brief",)},
            "video_brief": cd.get("video_brief", {}),
            "qc": st.session_state.qc_result or {},
        }
        st.json(judge_data)
