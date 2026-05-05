import os
import io
import time
import tempfile
from collections.abc import Callable
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

_PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

vertexai.init(project=_PROJECT, location=_LOCATION)

from google import genai as _genai
from google.genai import types as _gtypes
_vertex_client = _genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)

VIDEO_SIZE = (1080, 1920)   # 9:16 portrait
FPS        = 24

CHIRP3_VOICES = {
    "female": "en-US-Chirp3-HD-Aoede",
    "male":   "en-US-Chirp3-HD-Orus",
}


# ---------------------------------------------------------------------------
# 1. Chirp3-HD voice synthesis with SSML
# ---------------------------------------------------------------------------

def synthesize_speech(ssml_script: str, voice_gender: str = "female") -> bytes | None:
    try:
        client    = texttospeech.TextToSpeechClient()
        voice_name = CHIRP3_VOICES.get(voice_gender.lower(), CHIRP3_VOICES["female"])

        synthesis_input = (
            texttospeech.SynthesisInput(ssml=ssml_script)
            if ssml_script.strip().startswith("<speak")
            else texttospeech.SynthesisInput(text=ssml_script)
        )
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        print(f"[agent3] Chirp3-HD ({voice_name}): {len(response.audio_content)} bytes")
        return response.audio_content
    except Exception as exc:
        print(f"[agent3] TTS failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# 2. Veo 3.1 — generate one clip per scene (dialogue in prompt → lip sync)
# ---------------------------------------------------------------------------

def _poll_veo_operation(operation, label: str = "") -> bytes | None:
    """Poll a Veo operation until done. Returns video bytes or None."""
    max_polls = 18  # 3 minutes
    for poll in range(max_polls):
        if operation.done:
            break
        time.sleep(10)
        operation = _vertex_client.operations.get(operation)
        print(f"[agent3]   {label} poll {poll + 1}/{max_polls}...")

    if not operation.done:
        print(f"[agent3] {label} timed out")
        return None

    generated = operation.result.generated_videos[0]
    video      = generated.video

    # Inline bytes
    video_bytes = getattr(video, "video_bytes", None)
    if video_bytes:
        print(f"[agent3] {label}: {len(video_bytes)} bytes (inline)")
        return video_bytes

    # GCS fallback
    uri = getattr(video, "uri", None)
    if uri and uri.startswith("gs://"):
        try:
            from google.cloud import storage
            parts = uri.replace("gs://", "").split("/", 1)
            data  = storage.Client(project=_PROJECT).bucket(parts[0]).blob(parts[1]).download_as_bytes()
            print(f"[agent3] {label}: {len(data)} bytes (GCS)")
            return data
        except Exception as gcs_exc:
            print(f"[agent3] GCS download failed: {gcs_exc}")

    print(f"[agent3] {label}: no usable video returned")
    return None


def generate_veo_scene_clip(
    visual_prompt: str,
    voiceover: str,
    duration_seconds: int = 8,
    reference_image_bytes: bytes | None = None,
) -> bytes | None:
    """
    Generate a Veo 3.1 clip where the avatar speaks the given voiceover.
    Including the dialogue in the prompt causes Veo to naturally move the
    avatar's lips and body language to match those words.
    """
    def _make_config(with_ref: bool) -> _gtypes.GenerateVideosConfig:
        ref = None
        if with_ref and reference_image_bytes:
            try:
                from google.genai.types import VideoGenerationReferenceImage, Image as _GImage
                mime = "image/jpeg" if reference_image_bytes[:2] == b"\xff\xd8" else "image/png"
                ref = [VideoGenerationReferenceImage(
                    image=_GImage(image_bytes=reference_image_bytes, mime_type=mime),
                    reference_type="ASSET",
                )]
            except Exception as ref_exc:
                print(f"[agent3] reference_image build failed: {ref_exc}")
                ref = None
        return _gtypes.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=min(duration_seconds, 8),
            number_of_videos=1,
            reference_images=ref,
        )

    try:
        full_prompt = (
            f"{visual_prompt}. "
            f"The person speaks directly to camera and says: \"{voiceover}\""
        )

        try:
            operation = _vertex_client.models.generate_videos(
                model="veo-3.1-fast-generate-001",
                prompt=full_prompt,
                config=_make_config(with_ref=True),
            )
        except Exception as ref_api_exc:
            # reference_images may not be supported on this model/tier — retry without
            print(f"[agent3] Veo with reference_images failed ({ref_api_exc}), retrying without...")
            operation = _vertex_client.models.generate_videos(
                model="veo-3.1-fast-generate-001",
                prompt=full_prompt,
                config=_make_config(with_ref=False),
            )

        return _poll_veo_operation(operation, label=f"Veo scene ({voiceover[:30]}...)")

    except Exception as exc:
        print(f"[agent3] Veo scene clip failed: {exc}")
        return None


def generate_all_veo_clips(
    storyboard: list[dict],
    progress_callback: Callable[[int, str], None] | None = None,
    reference_image_bytes: bytes | None = None,
) -> list[bytes | None]:
    """
    Generate Veo clips for all scenes in parallel (up to 3 at a time).
    Each clip has the scene's voiceover embedded in the prompt for lip sync.
    """
    results = [None] * len(storyboard)
    n = len(storyboard)

    def _gen(idx: int, scene: dict):
        return idx, generate_veo_scene_clip(
            visual_prompt         = scene.get("visual_prompt", ""),
            voiceover             = scene.get("voiceover", ""),
            duration_seconds      = int(scene.get("duration_seconds", 8)),
            reference_image_bytes = reference_image_bytes,
        )

    print(f"[agent3] Launching {n} Veo scene clips in parallel (max 3 workers)...")
    completed = 0
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_gen, i, scene): i for i, scene in enumerate(storyboard)}
        for future in as_completed(futures):
            try:
                idx, clip_bytes = future.result()
                results[idx] = clip_bytes
                status = f"{len(clip_bytes)} bytes" if clip_bytes else "FAILED"
                print(f"[agent3] Scene {idx + 1} Veo result: {status}")
                completed += 1
                if progress_callback and n > 0:
                    pct = 20 + int(completed / n * 40)
                    progress_callback(
                        pct,
                        f"🎬 Rendering scene {completed}/{n}... ⏳",
                    )
            except Exception as exc:
                print(f"[agent3] Scene future error: {exc}")

    success = sum(1 for r in results if r)
    print(f"[agent3] Veo parallel generation: {success}/{len(storyboard)} clips succeeded")
    return results


# ---------------------------------------------------------------------------
# 3. Imagen 4 Ultra — fallback for scenes where Veo fails
# ---------------------------------------------------------------------------

def generate_scene_image(visual_prompt: str) -> bytes | None:
    for model_id in ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001", "imagen-3.0-generate-001"]:
        try:
            model  = ImageGenerationModel.from_pretrained(model_id)
            images = model.generate_images(prompt=visual_prompt, number_of_images=1, aspect_ratio="9:16")
            if images:
                print(f"[agent3] Scene image via {model_id}")
                return images[0]._image_bytes
        except Exception as exc:
            print(f"[agent3] {model_id} failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# 4. Ken Burns effect (used only when Veo fails for a scene)
# ---------------------------------------------------------------------------

def make_ken_burns_frames(img_array: np.ndarray, duration: float, fps: int = FPS,
                           zoom_start: float = 1.0, zoom_end: float = 1.06) -> list[np.ndarray]:
    h, w      = img_array.shape[:2]
    n_frames  = max(int(duration * fps), 1)
    pil_img   = Image.fromarray(img_array)
    frames    = []

    for i in range(n_frames):
        t     = i / max(n_frames - 1, 1)
        scale = zoom_start + (zoom_end - zoom_start) * t
        new_w, new_h = int(w * scale), int(h * scale)
        resized  = pil_img.resize((new_w, new_h), Image.LANCZOS)
        left, top = (new_w - w) // 2, (new_h - h) // 2
        frames.append(np.array(resized.crop((left, top, left + w, top + h))))

    return frames


# ---------------------------------------------------------------------------
# 5. Subtitle overlay
# ---------------------------------------------------------------------------

def _add_subtitle(img_array: np.ndarray, text: str) -> np.ndarray:
    img  = Image.fromarray(img_array).convert("RGBA")
    w, h = img.size

    overlay      = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_o       = ImageDraw.Draw(overlay)
    draw_o.rectangle([(0, h - 180), (w, h)], fill=(0, 0, 0, 180))
    img          = Image.alpha_composite(img, overlay).convert("RGB")
    draw         = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()

    words = text.split()
    lines, line = [], ""
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > w - 60:
            if line:
                lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)

    y = h - 160
    for ln in lines[:3]:
        bbox = draw.textbbox((0, 0), ln, font=font)
        x    = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 2), ln, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y),         ln, font=font, fill=(255, 255, 255))
        y += 46

    return np.array(img)


# ---------------------------------------------------------------------------
# 6. Multi-shot video assembly
# ---------------------------------------------------------------------------

def assemble_multishot_video(
    scenes: list[dict],
    scene_clip_bytes: list[bytes | None],
    audio_bytes: bytes | None,
) -> bytes | None:
    try:
        from moviepy import (
            VideoClip, VideoFileClip, ImageSequenceClip,
            AudioFileClip, concatenate_videoclips,
        )
        from moviepy.video.fx import FadeIn, FadeOut

        tmpdir = tempfile.mkdtemp()
        try:
            clips = []
            veo_file_clips = []  # track for explicit close before tmpdir cleanup

            for idx, (scene, clip_bytes) in enumerate(zip(scenes, scene_clip_bytes)):
                voiceover = scene.get("voiceover", "")
                duration  = float(scene.get("duration_seconds", 8))

                if clip_bytes:
                    # --- Veo clip: add subtitle overlay frame-by-frame ---
                    scene_path = os.path.join(tmpdir, f"scene_{idx}.mp4")
                    with open(scene_path, "wb") as f:
                        f.write(clip_bytes)

                    veo_clip = VideoFileClip(scene_path)
                    veo_file_clips.append(veo_clip)  # track for cleanup

                    # Resize to target dimensions if needed
                    if tuple(veo_clip.size) != VIDEO_SIZE:
                        veo_clip = veo_clip.resized(VIDEO_SIZE)

                    if voiceover:
                        # Stamp subtitle onto every frame
                        def make_subtitled_frame(t, _clip=veo_clip, _vo=voiceover):
                            frame = _clip.get_frame(t)
                            fh, fw = frame.shape[:2]
                            if (fw, fh) != VIDEO_SIZE:
                                frame = np.array(Image.fromarray(frame).resize(VIDEO_SIZE, Image.LANCZOS))
                            return _add_subtitle(frame, _vo)

                        subtitled = VideoClip(make_subtitled_frame, duration=veo_clip.duration)
                        # Keep Veo's original audio (it may contain the avatar's speech)
                        if veo_clip.audio:
                            subtitled = subtitled.with_audio(veo_clip.audio)
                        clips.append(subtitled)
                    else:
                        clips.append(veo_clip)

                    print(f"[agent3] Scene {idx + 1}: Veo clip ({veo_clip.duration:.1f}s)")

                else:
                    # --- Fallback: Imagen 4 + Ken Burns ---
                    image_bytes = scene.get("image_bytes")
                    if image_bytes:
                        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(VIDEO_SIZE, Image.LANCZOS)
                    else:
                        img = Image.new("RGB", VIDEO_SIZE, color=(15, 25, 55))
                        ImageDraw.Draw(img).text(
                            (50, VIDEO_SIZE[1] // 2),
                            f"Scene {scene.get('scene', idx + 1)}",
                            fill=(200, 200, 200),
                        )

                    img_array = np.array(img)
                    if voiceover:
                        img_array = _add_subtitle(img_array, voiceover)

                    z_start, z_end = (1.0, 1.06) if idx % 2 == 0 else (1.06, 1.0)
                    frames = make_ken_burns_frames(img_array, duration, zoom_start=z_start, zoom_end=z_end)
                    clip   = ImageSequenceClip(frames, fps=FPS)
                    clip   = clip.with_effects([FadeIn(0.25), FadeOut(0.25)])
                    clips.append(clip)
                    print(f"[agent3] Scene {idx + 1}: Imagen 4 fallback ({duration:.0f}s)")

            if not clips:
                return None

            final_video = concatenate_videoclips(clips, method="compose")

            # Replace audio with Chirp3-HD (higher quality, SSML inflections)
            if audio_bytes:
                audio_path = os.path.join(tmpdir, "voice.mp3")
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                audio_clip = AudioFileClip(audio_path)
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.with_end(final_video.duration)
                final_video = final_video.with_audio(audio_clip)

            output_path = os.path.join(tmpdir, "influencer_video.mp4")
            final_video.write_videofile(
                output_path, fps=FPS, codec="libx264",
                audio_codec="aac", logger=None, threads=2,
            )

            with open(output_path, "rb") as f:
                video_bytes = f.read()

            # Explicitly close all moviepy clips to release Windows file locks
            try:
                final_video.close()
            except Exception:
                pass
            for vc in veo_file_clips:
                try:
                    vc.close()
                except Exception:
                    pass

        finally:
            import shutil
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

        print(f"[agent3] Final video: {len(video_bytes)} bytes, {len(clips)} scenes")
        return video_bytes

    except Exception as exc:
        print(f"[agent3] Video assembly failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent3(
    content_draft: dict,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict:
    video_brief = content_draft.get("video_brief", {})

    if not video_brief:
        print("[agent3] No video_brief — skipping")
        return {"video_bytes": None, "audio_bytes": None, "script": "", "thumbnail_bytes": None, "storyboard": []}

    ssml_script      = video_brief.get("ssml_script", "")
    voice_gender     = video_brief.get("voice_gender", "female")
    storyboard       = video_brief.get("storyboard", [])
    avatar_description = video_brief.get("avatar_description", "")
    n_scenes         = max(len(storyboard), 1)

    # Extract canonical avatar reference image bytes if provided
    avatar_ref_bytes = content_draft.get("avatar_reference_image_bytes")

    # 1. Veo clips first (parallel) — progress ~20–60% via callback inside generate_all_veo_clips
    if progress_callback:
        progress_callback(20, "🎬 Generating video scenes... ⏳")
    print("[agent3] Generating per-scene Veo clips (parallel)...")
    scene_clip_bytes = generate_all_veo_clips(
        storyboard,
        progress_callback=progress_callback,
        reference_image_bytes=avatar_ref_bytes,
    )

    # 2. Chirp3-HD voice (full script, SSML) — after scenes so progress matches UX narrative
    if progress_callback:
        progress_callback(70, "🎙️ Generating voiceover... ⏳")
    print("[agent3] Synthesizing Chirp3-HD voice...")
    audio_bytes = synthesize_speech(ssml_script, voice_gender)

    # 3. For scenes where Veo failed, generate Imagen 4 Ultra fallback
    scenes_with_fallbacks = []
    for i, (scene, clip_bytes) in enumerate(zip(storyboard, scene_clip_bytes)):
        scene_data = dict(scene)
        scene_data["image_bytes"] = None
        if not clip_bytes:
            print(f"[agent3] Scene {i + 1} Veo failed — generating Imagen 4 Ultra fallback...")
            if progress_callback:
                pct = 72 + min(7, int((i + 1) / n_scenes * 7))
                progress_callback(pct, f"🖼️ Fallback image for scene {i + 1}/{n_scenes}... ⏳")
            scene_data["image_bytes"] = generate_scene_image(scene.get("visual_prompt", ""))
        scenes_with_fallbacks.append(scene_data)

    # 4. Assemble final multi-shot video
    if progress_callback:
        progress_callback(85, "🎬 Assembling final video... ⏳")
    print("[agent3] Assembling final multi-shot video...")
    video_bytes = assemble_multishot_video(scenes_with_fallbacks, scene_clip_bytes, audio_bytes)

    if progress_callback:
        progress_callback(95, "Finalizing output... ⏳")

    thumbnail_bytes = next(
        (b for b in scene_clip_bytes if b),  # use first successful Veo clip as thumbnail
        next((s["image_bytes"] for s in scenes_with_fallbacks if s.get("image_bytes")), None),
    )

    return {
        "video_bytes":       video_bytes,
        "audio_bytes":       audio_bytes,
        "script":            ssml_script,
        "thumbnail_bytes":   thumbnail_bytes,
        "storyboard":        storyboard,
        "avatar_description": avatar_description,
        "music_mood":        video_brief.get("music_mood", ""),
        "used_veo":          any(b for b in scene_clip_bytes),
        "veo_scenes":        sum(1 for b in scene_clip_bytes if b),
        "total_scenes":      len(storyboard),
        "audience_persona":  content_draft.get("audience_persona"),
    }
