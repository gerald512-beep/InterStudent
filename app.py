import json
import io
import re
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from PIL import Image

from audience_personalization import merge_retrieval_persona
from publishing.service import (
    delete_item,
    enqueue,
    list_queue,
    process_due,
    publish_manual,
    save_draft,
)

VIDEO_SAVE_DIR = os.path.join(os.path.dirname(__file__), "videos")

from agents.agent1_source_retrieval import retrieve
from agents.agent2_content_generator import run_agent2
from agents.agent3_video_generator import run_agent3
from agents.agent4_qc import run_agent4
from agents.agent5_scenario_resolver import run_agent5
from output.creative_storyteller import generate_output

# ---------------------------------------------------------------------------
# Audience UI options
# ---------------------------------------------------------------------------

AUDIENCE_SEGMENTS = [
    "New F1 students",
    "Current F1 students",
    "OPT students",
    "J1 students",
    "International parents",
    "General international student audience",
]
SCHOOL_TYPES = ["Undergraduate", "Graduate", "Any"]
CONTENT_GOALS = ["Awareness", "Education", "Engagement", "Conversion"]
TONE_OPTIONS = ["Helpful", "Empowering", "Urgent", "Friendly", "Professional"]
PLATFORM_STYLES = [
    "Thought-leadership",
    "Creator-style",
    "Informational carousel tone",
    "Short-form viral",
]
CTA_OPTIONS = [
    "Visit resource links",
    "Comment for checklist",
    "DM for guide",
    "Save and share",
]
RISK_OPTIONS = ["Conservative", "Balanced", "Bold"]
AVATAR_STYLES = [
    "Professional student advisor",
    "Friendly peer creator",
    "Campus influencer",
]
LANG_OPTIONS = ["English", "Hindi", "Mandarin", "Spanish"]

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
    "last_video_path": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Audience widget defaults (Streamlit keys ap_*)
if "ap_city_focus" not in st.session_state:
    st.session_state.ap_city_focus = "NYC"
if "ap_content_goal" not in st.session_state:
    st.session_state.ap_content_goal = ["Education"]
if "ap_languages" not in st.session_state:
    st.session_state.ap_languages = ["English"]

# Agent 5 — scenario assistant (session-scoped; max 5 history entries)
if "agent5_history" not in st.session_state:
    st.session_state.agent5_history = []
if "agent5_last_result" not in st.session_state:
    st.session_state.agent5_last_result = None
if "agent5_query" not in st.session_state:
    st.session_state.agent5_query = ""

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
    st.markdown("**Auto-Publishing**")
    st.caption("Local JSON queue · stub adapters · optional webhook on publish")
    st.text_input("Webhook URL (optional)", key="pub_webhook_url", placeholder="https://example.com/hooks/publish")
    st.checkbox("Notify webhook on manual / due publish", key="pub_notify_webhook")

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


def _webhook_url_if_enabled() -> str | None:
    if not st.session_state.get("pub_notify_webhook"):
        return None
    u = (st.session_state.get("pub_webhook_url") or "").strip()
    return u or None


def _render_vertex_credentials_help(err: BaseException) -> None:
    msg = str(err).lower()
    if "default credentials" not in msg and "application default" not in msg:
        return
    st.info(
        "**Vertex AI needs Application Default Credentials (ADC) on this machine.**\n\n"
        "1. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).\n"
        "2. Run: `gcloud auth application-default login`\n"
        "3. Set `GOOGLE_CLOUD_PROJECT` in your `.env` to your GCP project ID (Vertex AI enabled).\n"
        "4. Restart Streamlit.\n\n"
        "Alternatively, set `GOOGLE_APPLICATION_CREDENTIALS` to a service account JSON key path. "
        "[ADC setup guide](https://cloud.google.com/docs/authentication/external/set-up-adc)"
    )


def _collect_audience_persona() -> dict:
    inc = bool(st.session_state.get("ap_include_language_support", False))
    langs = list(st.session_state.get("ap_languages") or [])
    if not inc:
        langs = []
    return {
        "persona_name": (st.session_state.get("ap_persona_name") or "").strip(),
        "audience_segment": st.session_state.get("ap_audience_segment")
        or "General international student audience",
        "city_focus": (st.session_state.get("ap_city_focus") or "NYC").strip() or "NYC",
        "school_type": st.session_state.get("ap_school_type") or "Any",
        "content_goal": list(st.session_state.get("ap_content_goal") or []),
        "tone_preference": st.session_state.get("ap_tone_preference") or "Helpful",
        "platform_style": st.session_state.get("ap_platform_style")
        or "Thought-leadership",
        "cta_preference": st.session_state.get("ap_cta_preference")
        or "Visit resource links",
        "risk_tolerance": st.session_state.get("ap_risk_tolerance") or "Balanced",
        "avatar_style": st.session_state.get("ap_avatar_style")
        or "Friendly peer creator",
        "include_language_support": inc,
        "languages": langs,
    }


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("NYC International Student AI Influencer")
st.subheader("Personal finance guidance — built on live NYC data + Google AI")

with st.expander("Audience Personalization", expanded=False):
    st.caption("Tune copy, CTA, storyboard, and tone for your target audience.")
    st.text_input("Persona name", key="ap_persona_name", placeholder="e.g. Finance-savvy grad mentor")
    st.selectbox("Audience segment", AUDIENCE_SEGMENTS, key="ap_audience_segment")
    st.text_input("City focus", key="ap_city_focus")
    st.selectbox("School type", SCHOOL_TYPES, key="ap_school_type")
    st.multiselect("Content goal", CONTENT_GOALS, key="ap_content_goal")
    st.selectbox("Tone preference", TONE_OPTIONS, key="ap_tone_preference")
    st.selectbox("Platform style", PLATFORM_STYLES, key="ap_platform_style")
    st.selectbox("CTA preference", CTA_OPTIONS, key="ap_cta_preference")
    st.selectbox("Risk tolerance", RISK_OPTIONS, key="ap_risk_tolerance")
    st.selectbox("Avatar style", AVATAR_STYLES, key="ap_avatar_style")
    st.checkbox("Include language support", key="ap_include_language_support")
    st.multiselect("Languages", LANG_OPTIONS, key="ap_languages")

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
    for key in [
        "phase",
        "retrieval_pack",
        "content_draft",
        "final_output",
        "video_output",
        "qc_result",
        "last_video_path",
        "agent5_history",
        "agent5_last_result",
        "agent5_query",
    ]:
        if key == "phase":
            st.session_state[key] = "idle"
        elif key == "agent5_history":
            st.session_state[key] = []
        elif key == "agent5_query":
            st.session_state[key] = ""
        else:
            st.session_state[key] = None
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
            user_persona = _collect_audience_persona()
            st.session_state.retrieval_pack["persona"] = merge_retrieval_persona(
                st.session_state.retrieval_pack.get("persona"),
                user_persona,
            )
            st.write(f"Retrieved {len(st.session_state.retrieval_pack['results'])} sources")
            _set_step("agent1", "done")
        except Exception as e:
            _set_step("agent1", "error")
            st.error(f"Agent 1 failed: {e}")
            _render_vertex_credentials_help(e)
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

    st.divider()
    with st.expander("Auto-Publishing — drafts, queue, stubs", expanded=False):
        st.markdown(
            "Save posts to a **local JSON queue** (`data/publish_queue.json`), schedule them, "
            "or trigger **stub** LinkedIn / Instagram publishers. Optional **webhook** notify from the sidebar."
        )
        ap = content_draft.get("audience_persona") or {}
        st.caption(
            f"Active persona: **{ap.get('audience_segment', '—')}** · "
            f"{ap.get('tone_preference', '')} · {ap.get('city_focus', '')}"
        )

        snap = {
            "body": final_output.get("body") or "",
            "caption": final_output.get("caption") or "",
            "hashtags": final_output.get("hashtags", ""),
            "sources": final_output.get("sources", []),
            "platform": content_draft.get("platform", platform),
            "topic": content_draft.get("topic", topic),
        }

        ex1, ex2 = st.columns(2)
        with ex1:
            st.download_button(
                label="Export post (.json)",
                data=json.dumps(
                    {"post": snap, "audience_persona": ap},
                    indent=2,
                    ensure_ascii=False,
                ),
                file_name="interstudent_post_export.json",
                mime="application/json",
                use_container_width=True,
                key="pub_dl_json",
            )
        with ex2:
            plain = (snap.get("body") or snap.get("caption") or "") + "\n\n" + str(
                snap.get("hashtags") or ""
            )
            st.download_button(
                label="Export post (.txt)",
                data=plain.encode("utf-8"),
                file_name="interstudent_post_export.txt",
                mime="text/plain",
                use_container_width=True,
                key="pub_dl_txt",
            )

        if st.button("Save current post as draft", use_container_width=True, key="pub_save_draft"):
            try:
                vid = st.session_state.get("last_video_path")
                new_id = save_draft(
                    topic=snap["topic"],
                    platform_primary=snap["platform"],
                    post_snapshot=snap,
                    audience_persona=ap,
                    video_path=vid,
                )
                st.success(f"Draft saved — id `{new_id}`")
            except Exception as ex:
                st.error(f"Could not save draft: {ex}")

        queue = list_queue()
        draft_rows = [q for q in queue if q.get("status") == "draft"]
        draft_ids = [q["id"] for q in draft_rows]

        c1, c2 = st.columns(2)
        with c1:
            pick = st.selectbox(
                "Draft to schedule",
                options=["—"] + draft_ids,
                key="pub_pick_draft",
            )
        with c2:
            plat_sel = st.multiselect(
                "Target platforms",
                ["linkedin", "instagram"],
                default=[platform],
                key="pub_target_platforms",
            )

        sd = st.date_input("Schedule date", key="pub_sched_date")
        st_time = st.time_input("Schedule time (UTC)", key="pub_sched_time")
        sched_iso = None
        if sd and st_time:
            sched_dt = datetime.combine(sd, st_time, tzinfo=timezone.utc)
            sched_iso = sched_dt.isoformat()

        if st.button("Enqueue draft (queued)", use_container_width=True, key="pub_enqueue"):
            if pick == "—" or not plat_sel:
                st.warning("Select a draft and at least one platform.")
            else:
                ok = enqueue(
                    pick,
                    scheduled_at_iso=sched_iso,
                    platforms=plat_sel,
                )
                st.success("Queued." if ok else "Enqueue failed — id not found.")

        if st.button("Process due jobs now", use_container_width=True, key="pub_process_due"):
            done = process_due(webhook_url=_webhook_url_if_enabled())
            st.info(f"Processed {len(done)} item(s).")

        st.markdown("**Manual publish (stub adapters)**")
        q_ids = [q["id"] for q in queue]
        mp = st.selectbox("Queue item", options=["—"] + q_ids, key="pub_manual_id")
        if st.button("Publish now (stub)", use_container_width=True, key="pub_manual_go"):
            if mp != "—":
                out = publish_manual(mp, webhook_url=_webhook_url_if_enabled())
                if out:
                    st.json(
                        {
                            "status": out.get("status"),
                            "last_publish_results": out.get("last_publish_results"),
                        }
                    )
                else:
                    st.error("Item not found.")

        if queue:
            rows = []
            for it in queue:
                rows.append(
                    {
                        "id": it.get("id", ""),
                        "status": it.get("status"),
                        "scheduled_at": it.get("scheduled_at"),
                        "topic": (it.get("topic") or "")[:80],
                        "platforms": ",".join(it.get("platforms") or []),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        del_id = st.selectbox("Delete queue item", options=["—"] + q_ids, key="pub_del_pick")
        if st.button("Delete selected", key="pub_del_go"):
            if del_id != "—":
                delete_item(del_id)
                st.success("Deleted.")
                st.rerun()

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
            progress_bar = st.progress(0)
            progress_text = st.empty()

            def update_progress(pct: int, message: str) -> None:
                pct_clamped = max(0, min(100, int(pct)))
                progress_bar.progress(pct_clamped / 100.0)
                progress_text.markdown(f"**{pct_clamped}% — {message}**")

            with st.status("Generating AI influencer video...", expanded=True) as vstatus:
                _set_step("agent3", "running")
                st.caption("⏱️ Estimated time: ~2–3 minutes")
                update_progress(5, "Initializing video pipeline... ⏳")
                st.write("Agent 3 — Veo 3.1 hero clip + Imagen 4 Ultra scenes + Chirp3-HD voice...")
                update_progress(10, "Preparing scenes and voiceover... ⏳")
                try:
                    st.session_state.video_output = run_agent3(
                        st.session_state.content_draft,
                        progress_callback=update_progress,
                    )
                    update_progress(100, "Video ready! ⏳")
                    used_veo = st.session_state.video_output.get("used_veo", False)
                    msg = "Video assembled" + (" (Veo 3.1 hero clip included)" if used_veo else " (Imagen 4 Ultra multi-shot)")
                    st.write(msg)
                    # Auto-save video to disk
                    vb = st.session_state.video_output.get("video_bytes")
                    if vb:
                        os.makedirs(VIDEO_SAVE_DIR, exist_ok=True)
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_path = os.path.join(VIDEO_SAVE_DIR, f"influencer_{ts}.mp4")
                        with open(save_path, "wb") as _f:
                            _f.write(vb)
                        st.session_state.last_video_path = save_path
                        st.write(f"Saved to: `{save_path}`")
                    _set_step("agent3", "done")
                except Exception as e:
                    _set_step("agent3", "error")
                    st.warning(f"Agent 3 failed: {e}")
                    st.session_state.video_output = {}

                _set_step("agent4", "running")
                update_progress(98, "🔍 Running quality checks... ⏳")
                st.write("Agent 4 — Quality control evaluation...")
                try:
                    st.session_state.qc_result = run_agent4(
                        st.session_state.final_output,
                        st.session_state.video_output or {},
                    )
                    _set_step("agent4", "done")
                    update_progress(100, "✅ Quality review complete! ⏳")
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

# ---------------------------------------------------------------------------
# Agent 5 — Scenario Resolver (post-generation; not a general chatbot)
# ---------------------------------------------------------------------------

if st.session_state.final_output and st.session_state.phase in ("post_done", "video_done"):
    st.divider()
    st.markdown("### Scenario Resolver")
    st.caption(
        "Describe your situation to get tailored **informational** guidance. "
        "One-shot answers with clarifiers — not an open-ended chat."
    )
    if "tax" in (topic or "").lower():
        st.caption(
            "_For tax-related topics, include tax year and which forms you received (W-2, 1099, 1042-S, etc.) if you can._"
        )

    chip1, chip2, chip3, chip4 = st.columns(4)
    with chip1:
        if st.button("F1 + W-2", key="a5_chip_f1w2"):
            st.session_state.agent5_query = (
                "I'm an F1 student with a W-2 from campus work. What should I think about for taxes and withholding?"
            )
    with chip2:
        if st.button("OPT + no SSN", key="a5_chip_opt"):
            st.session_state.agent5_query = (
                "I'm on OPT, worked several months, and I don't have an SSN yet. What might I need for payroll or taxes?"
            )
    with chip3:
        if st.button("Scholarship question", key="a5_chip_sch"):
            st.session_state.agent5_query = (
                "I have scholarship and fellowship income. How do I think about what might be taxable?"
            )
    with chip4:
        if st.button("Work off campus?", key="a5_chip_work"):
            st.session_state.agent5_query = (
                "Can I work off campus while on F1? What questions should I ask my DSO?"
            )

    st.text_area(
        "Describe your situation",
        key="agent5_query",
        height=120,
        placeholder=(
            "I'm on OPT, worked 6 months in NYC, got a W-2, and I don't have an SSN yet."
        ),
    )

    b1, b2 = st.columns([1, 1])
    with b1:
        run_a5 = st.button("Get personalized guidance", type="primary", use_container_width=True, key="a5_submit")
    with b2:
        if st.button("Clear Agent 5 history", use_container_width=True, key="a5_reset"):
            st.session_state.agent5_history = []
            st.session_state.agent5_last_result = None
            st.session_state.agent5_query = ""
            st.rerun()

    if run_a5:
        uq = (st.session_state.get("agent5_query") or "").strip()
        if not uq:
            st.warning("Enter a short description of your situation first.")
        else:
            with st.spinner("Resolving scenario…"):
                result = run_agent5(
                    user_query=uq,
                    retrieval_pack=st.session_state.get("retrieval_pack"),
                    content_draft=st.session_state.get("content_draft"),
                    user_profile=(st.session_state.get("content_draft") or {}).get("audience_persona"),
                )
            st.session_state.agent5_last_result = result
            st.session_state.agent5_history.append({"query": uq, "result": result})
            st.session_state.agent5_history = st.session_state.agent5_history[-5:]

    res = st.session_state.agent5_last_result
    if res:
        g = res.get("guidance") or {}
        st.markdown("#### Summary")
        st.markdown(g.get("summary") or "—")

        st.markdown("#### What likely applies to you")
        for line in g.get("what_likely_applies") or []:
            st.markdown(f"- {line}")

        st.markdown("#### Next steps")
        for i, line in enumerate(g.get("recommended_next_steps") or [], start=1):
            st.markdown(f"{i}. {line}")

        st.markdown("#### Watchouts")
        for line in g.get("watchouts") or []:
            st.warning(line)

        st.markdown("#### Questions to confirm")
        for line in g.get("questions_to_confirm") or []:
            st.markdown(f"- {line}")

        srcs = g.get("sources") or []
        if srcs:
            st.markdown("#### Sources")
            for s in srcs:
                t, u = s.get("title", "Source"), s.get("url", "")
                if u:
                    st.markdown(f"- [{t}]({u})")
                else:
                    st.markdown(f"- {t}")

        conf = res.get("confidence", "medium")
        st.caption(f"Confidence: **{conf}**")
        st.info(res.get("disclaimer") or "")

        copy_blob = "\n\n".join(
            [
                g.get("summary") or "",
                "What likely applies:\n"
                + "\n".join(f"- {x}" for x in (g.get("what_likely_applies") or [])),
                "Next steps:\n"
                + "\n".join(f"- {x}" for x in (g.get("recommended_next_steps") or [])),
                "Watchouts:\n" + "\n".join(f"- {x}" for x in (g.get("watchouts") or [])),
                res.get("disclaimer") or "",
            ]
        )
        st.download_button(
            label="Download guidance as .txt",
            data=copy_blob.encode("utf-8"),
            file_name="scenario_guidance.txt",
            mime="text/plain",
            key="a5_dl_txt",
        )

        with st.expander("Scenario extraction details"):
            st.json(res.get("normalized_scenario") or {})

        if st.session_state.agent5_history:
            with st.expander("Recent scenario requests (this session)", expanded=False):
                for h in reversed(st.session_state.agent5_history):
                    st.markdown(f"**Q:** {h.get('query', '')[:200]}")
