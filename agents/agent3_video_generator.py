import os
import io
import time
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "interstudent-nyc-2026")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

vertexai.init(project=_PROJECT, location=_LOCATION)

# Vertex AI genai client for Veo
from google import genai as _genai
from google.genai import types as _gtypes
_vertex_client = _genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)

VIDEO_SIZE = (1080, 1920)   # 9:16 portrait
FPS = 24


# ---------------------------------------------------------------------------
# 1. Chirp3-HD voice synthesis with SSML
# ---------------------------------------------------------------------------

CHIRP3_VOICES = {
    "female": "en-US-Chirp3-HD-Aoede",
    "male":   "en-US-Chirp3-HD-Orus",
}


def synthesize_speech(ssml_script: str, voice_gender: str = "female") -> bytes | None:
    try:
        client = texttospeech.TextToSpeechClient()
        voice_name = CHIRP3_VOICES.get(voice_gender.lower(), CHIRP3_VOICES["female"])

        # Accept both SSML and plain text
        if ssml_script.strip().startswith("<speak"):
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml_script)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=ssml_script)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        print(f"[agent3] Chirp3-HD TTS ({voice_name}): {len(response.audio_content)} bytes")
        return response.audio_content
    except Exception as exc:
        print(f"[agent3] TTS failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# 2. Veo 3.1 — hero clip (scene 1)
# ---------------------------------------------------------------------------

def generate_veo_clip(visual_prompt: str, duration_seconds: int = 8) -> bytes | None:
    try:
        operation = _vertex_client.models.generate_videos(
            model="veo-3.1-fast-generate-001",
            prompt=visual_prompt,
            config=_gtypes.GenerateVideosConfig(
                aspect_ratio="9:16",
                duration_seconds=duration_seconds,
                number_of_videos=1,
            ),
        )

        print(f"[agent3] Veo 3.1 generating hero clip (up to 3 min)...")
        max_polls = 18  # 3 minutes
        for poll in range(max_polls):
            if operation.done:
                break
            time.sleep(10)
            operation = _vertex_client.operations.get(operation)
            print(f"[agent3]   Veo poll {poll + 1}/{max_polls}...")

        if not operation.done:
            print("[agent3] Veo timed out — falling back to Imagen 4")
            return None

        generated = operation.result.generated_videos[0]
        video = generated.video

        # Inline bytes
        video_bytes = getattr(video, "video_bytes", None)
        if video_bytes:
            print(f"[agent3] Veo hero clip: {len(video_bytes)} bytes")
            return video_bytes

        # GCS fallback
        uri = getattr(video, "uri", None)
        if uri and uri.startswith("gs://"):
            try:
                from google.cloud import storage
                parts = uri.replace("gs://", "").split("/", 1)
                gcs_client = storage.Client(project=_PROJECT)
                data = gcs_client.bucket(parts[0]).blob(parts[1]).download_as_bytes()
                print(f"[agent3] Veo clip from GCS: {len(data)} bytes")
                return data
            except Exception as gcs_exc:
                print(f"[agent3] GCS download failed: {gcs_exc}")

        print("[agent3] Veo returned no usable video")
        return None

    except Exception as exc:
        print(f"[agent3] Veo failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# 3. Imagen 4 Ultra — per-scene background
# ---------------------------------------------------------------------------

def generate_scene_image(visual_prompt: str) -> bytes | None:
    for model_id in ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001", "imagen-3.0-generate-001"]:
        try:
            model = ImageGenerationModel.from_pretrained(model_id)
            images = model.generate_images(
                prompt=visual_prompt,
                number_of_images=1,
                aspect_ratio="9:16",
            )
            if images:
                print(f"[agent3] Scene image via {model_id}")
                return images[0]._image_bytes
        except Exception as exc:
            print(f"[agent3] {model_id} failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# 4. Ken Burns zoom effect
# ---------------------------------------------------------------------------

def make_ken_burns_frames(img_array: np.ndarray, duration: float, fps: int = FPS,
                           zoom_start: float = 1.0, zoom_end: float = 1.06) -> list[np.ndarray]:
    h, w = img_array.shape[:2]
    n_frames = max(int(duration * fps), 1)
    pil_img = Image.fromarray(img_array)
    frames = []

    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        scale = zoom_start + (zoom_end - zoom_start) * t
        new_w, new_h = int(w * scale), int(h * scale)
        resized = pil_img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        frames.append(np.array(resized.crop((left, top, left + w, top + h))))

    return frames


# ---------------------------------------------------------------------------
# 5. Subtitle overlay
# ---------------------------------------------------------------------------

def _add_subtitle(img_array: np.ndarray, text: str) -> np.ndarray:
    img = Image.fromarray(img_array).convert("RGBA")
    w, h = img.size

    # Dark gradient bar at bottom
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_o = ImageDraw.Draw(overlay)
    draw_o.rectangle([(0, h - 180), (w, h)], fill=(0, 0, 0, 180))
    img = Image.alpha_composite(img, overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
        font_small = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    # Word-wrap text to fit width
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

    # Draw up to 3 lines, centered
    y = h - 160
    for ln in lines[:3]:
        bbox = draw.textbbox((0, 0), ln, font=font)
        x = (w - (bbox[2] - bbox[0])) // 2
        # Shadow
        draw.text((x + 2, y + 2), ln, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), ln, font=font, fill=(255, 255, 255))
        y += 46

    return np.array(img)


# ---------------------------------------------------------------------------
# 6. Multi-shot video assembly
# ---------------------------------------------------------------------------

def assemble_multishot_video(
    scenes: list[dict],
    audio_bytes: bytes | None,
    hero_clip_bytes: bytes | None,
) -> bytes | None:
    try:
        from moviepy import (
            ImageSequenceClip, AudioFileClip, VideoFileClip,
            concatenate_videoclips,
        )
        from moviepy.video.fx import FadeIn, FadeOut

        with tempfile.TemporaryDirectory() as tmpdir:
            clips = []
            scene_list = list(scenes)  # copy so we can pop

            # --- Scene 0: use Veo hero clip if available ---
            if hero_clip_bytes and scene_list:
                hero_path = os.path.join(tmpdir, "hero.mp4")
                with open(hero_path, "wb") as f:
                    f.write(hero_clip_bytes)
                try:
                    hero_clip = VideoFileClip(hero_path).resized(VIDEO_SIZE)
                    hero_clip = hero_clip.with_effects([FadeIn(0.3)])
                    clips.append(hero_clip)
                    scene_list.pop(0)  # hero clip covers scene 1
                    print("[agent3] Hero clip (Veo) added as scene 1")
                except Exception as e:
                    print(f"[agent3] Hero clip load failed: {e}")
                    hero_clip_bytes = None  # fall through to Imagen for scene 1

            # --- Remaining scenes: Imagen 4 + Ken Burns ---
            for idx, scene in enumerate(scene_list):
                image_bytes = scene.get("image_bytes")
                duration = float(scene.get("duration_seconds", 8))
                voiceover = scene.get("voiceover", "")

                if image_bytes:
                    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(VIDEO_SIZE, Image.LANCZOS)
                else:
                    # Fallback: dark gradient with scene number
                    img = Image.new("RGB", VIDEO_SIZE, color=(15, 25, 55))
                    d = ImageDraw.Draw(img)
                    d.text((50, VIDEO_SIZE[1] // 2), f"Scene {scene.get('scene', idx + 1)}", fill=(200, 200, 200))

                img_array = np.array(img)

                # Subtitle overlay
                if voiceover:
                    img_array = _add_subtitle(img_array, voiceover)

                # Ken Burns — alternate zoom direction per scene for variety
                z_start, z_end = (1.0, 1.06) if idx % 2 == 0 else (1.06, 1.0)
                frames = make_ken_burns_frames(img_array, duration, zoom_start=z_start, zoom_end=z_end)

                clip = ImageSequenceClip(frames, fps=FPS)
                clip = clip.with_effects([FadeIn(0.25), FadeOut(0.25)])
                clips.append(clip)

            if not clips:
                return None

            # --- Concatenate ---
            final_video = concatenate_videoclips(clips, method="compose")

            # --- Audio overlay ---
            if audio_bytes:
                audio_path = os.path.join(tmpdir, "voice.mp3")
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                audio_clip = AudioFileClip(audio_path)
                # Match lengths
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.with_end(final_video.duration)
                final_video = final_video.with_audio(audio_clip)

            output_path = os.path.join(tmpdir, "influencer_video.mp4")
            final_video.write_videofile(
                output_path,
                fps=FPS,
                codec="libx264",
                audio_codec="aac",
                logger=None,
                threads=2,
            )

            with open(output_path, "rb") as f:
                video_bytes = f.read()

        print(f"[agent3] Multi-shot video assembled: {len(video_bytes)} bytes, {len(clips)} clips")
        return video_bytes

    except Exception as exc:
        print(f"[agent3] Video assembly failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent3(content_draft: dict) -> dict:
    video_brief = content_draft.get("video_brief", {})

    if not video_brief:
        print("[agent3] No video_brief — skipping")
        return {"video_bytes": None, "audio_bytes": None, "script": "", "thumbnail_bytes": None, "storyboard": []}

    ssml_script = video_brief.get("ssml_script", "")
    voice_gender = video_brief.get("voice_gender", "female")
    storyboard = video_brief.get("storyboard", [])
    avatar_description = video_brief.get("avatar_description", "")

    # --- 1. Synthesize voice (Chirp3-HD + SSML) ---
    print("[agent3] Synthesizing Chirp3-HD voice with SSML...")
    audio_bytes = synthesize_speech(ssml_script, voice_gender)

    # --- 2. Try Veo hero clip for scene 1 ---
    hero_clip_bytes = None
    if storyboard:
        scene1_prompt = storyboard[0].get("visual_prompt", "")
        if scene1_prompt:
            print("[agent3] Attempting Veo 3.1 hero clip for scene 1...")
            hero_clip_bytes = generate_veo_clip(scene1_prompt, duration_seconds=8)

    # --- 3. Generate Imagen 4 Ultra per remaining scene ---
    scenes_for_assembly = []
    start_idx = 1 if hero_clip_bytes else 0  # skip scene 1 if Veo succeeded

    for i, scene in enumerate(storyboard):
        scene_data = dict(scene)

        if i < start_idx:
            # Scene 1 covered by Veo — still include as skeleton for timing
            scene_data["image_bytes"] = None
        else:
            print(f"[agent3] Generating Imagen 4 Ultra for scene {scene.get('scene', i + 1)}...")
            scene_data["image_bytes"] = generate_scene_image(scene.get("visual_prompt", ""))

        scenes_for_assembly.append(scene_data)

    # --- 4. Assemble multi-shot video ---
    print("[agent3] Assembling multi-shot video...")
    video_bytes = assemble_multishot_video(scenes_for_assembly, audio_bytes, hero_clip_bytes)

    # thumbnail = first scene image
    thumbnail_bytes = next(
        (s["image_bytes"] for s in scenes_for_assembly if s.get("image_bytes")),
        None,
    )

    return {
        "video_bytes": video_bytes,
        "audio_bytes": audio_bytes,
        "script": ssml_script,
        "thumbnail_bytes": thumbnail_bytes,
        "storyboard": storyboard,
        "avatar_description": avatar_description,
        "music_mood": video_brief.get("music_mood", ""),
        "used_veo": hero_clip_bytes is not None,
    }
