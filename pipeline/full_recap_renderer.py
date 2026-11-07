"""Render one continuous video timeline under one complete narration track."""
from __future__ import annotations

import os
from typing import Any


def render_full_recap_video(
    panels: list[dict[str, Any]],
    visual_timeline: dict[str, Any],
    audio_path: str,
    output_path: str,
    *,
    resolution: str = "1080p",
    fps: int = 30,
    quality: str = "medium",
    bg_mode: str = "blur",
    custom_bg_path: str | None = None,
    animation_style: str = "auto",
    watermark_path: str | None = None,
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
    progress_callback=None,
) -> str:
    """Use the narration file as the master clock; never trim or time-stretch it."""
    from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips, concatenate_videoclips
    from pipeline import compositor

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Файл озвучки не найден: {audio_path}")
    if not panels:
        raise ValueError("Нет изображений для монтажа")

    width, height = compositor.RESOLUTION_MAP.get(resolution, (1920, 1080))
    fps = fps if fps in compositor.FPS_OPTIONS else 30
    panel_lookup = {str(panel.get("panel_id")): panel for panel in panels}

    narration = AudioFileClip(audio_path)
    audio_duration = float(narration.duration)
    if audio_duration <= 0:
        narration.close()
        raise ValueError("Длительность озвучки равна нулю")

    entries = sorted(
        visual_timeline.get("entries", []),
        key=lambda entry: float(entry.get("start", 0.0)),
    )
    if not entries:
        narration.close()
        raise ValueError("Визуальный таймлайн пуст")

    # Normalize visual intervals to the audio clock. Gaps hold the preceding
    # image; if the last shot ends early, it remains until the audio ends.
    normalized = []
    cursor = 0.0
    for item in entries:
        panel = panel_lookup.get(str(item.get("panel_id")))
        if panel is None:
            continue
        start = max(0.0, min(audio_duration, float(item.get("start", cursor))))
        end = max(0.0, min(audio_duration, float(item.get("end", cursor))))
        if end <= cursor:
            continue
        if not normalized:
            start = 0.0
        else:
            start = max(cursor, start)
            if start > cursor:
                previous = normalized[-1]
                normalized[-1] = (previous[0], previous[1], start, previous[3])
        if end <= start:
            continue
        normalized.append((panel, start, end, item.get("motion")))
        cursor = end

    if not normalized:
        narration.close()
        raise ValueError("Таймлайн не ссылается на существующие изображения")
    if normalized[-1][2] < audio_duration:
        panel, start, _end, motion = normalized[-1]
        normalized[-1] = (panel, start, audio_duration, motion)

    clips = []
    final = None
    video = None
    bgm = None
    try:
        for index, (panel, start, end, motion) in enumerate(normalized):
            duration = end - start
            if duration <= 0:
                continue
            if progress_callback:
                progress_callback(index + 1, len(normalized), f"Монтаж: кадр {index + 1}/{len(normalized)}")

            motion_map = {
                "slow_zoom_in": "zoom_in",
                "slow_zoom_out": "zoom_out",
                "slow_pan_left": "slide_left",
                "slow_pan_right": "slide_right",
            }
            selected = motion_map.get(motion, animation_style)
            if animation_style == "none":
                selected = "none"

            panel_clip = compositor._make_panel_clip(
                panel, width, height, duration, fps, index,
                bg_mode, custom_bg_path, selected,
            )
            layers = [panel_clip]
            try:
                layers.append(compositor._create_vignette(width, height, duration))
            except Exception:
                pass
            if watermark_path and os.path.isfile(watermark_path):
                try:
                    layers.append(compositor._create_watermark(
                        watermark_path, width, height, duration
                    ))
                except Exception:
                    pass
            if len(layers) > 1:
                panel_clip = compositor.CompositeVideoClip(layers)
            clips.append(panel_clip.with_duration(duration))

        if not clips:
            raise RuntimeError("Не удалось отрендерить ни одного изображения")

        video = concatenate_videoclips(clips, method="compose")
        # A final frame-rounding adjustment applies to video only. Narration is
        # attached as-is and remains the exact master duration.
        if video.duration > audio_duration:
            video = video.subclipped(0, audio_duration)
        elif video.duration < audio_duration:
            video = video.with_duration(audio_duration)

        final = video.with_audio(narration).with_duration(audio_duration)

        # Background music is optional and mixed underneath the single narration.
        # It may loop, but the narration file itself is never modified or trimmed.
        if bgm_path and os.path.isfile(bgm_path):
            try:
                bgm = AudioFileClip(bgm_path)
                if bgm.duration > 0:
                    if bgm.duration < audio_duration:
                        loops = int(audio_duration / bgm.duration) + 1
                        bgm = concatenate_audioclips([bgm] * loops)
                    bgm = bgm.subclipped(0, audio_duration).with_volume_scaled(
                        max(0.0, min(1.0, float(bgm_volume)))
                    )
                    final = final.with_audio(CompositeAudioClip([narration, bgm]))
            except Exception as exc:
                print(f"[FullRecapRenderer] Background music skipped: {exc}")

        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        bitrate = {"low": "2000k", "medium": "5000k", "high": "8000k"}.get(
            quality, "5000k"
        )
        temp_audio = os.path.join(
            out_dir, os.path.basename(output_path) + "_TEMP_audio.mp4"
        )
        if progress_callback:
            progress_callback(len(clips), len(clips), "Экспорт MP4…")
        final.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            bitrate=bitrate,
            preset="medium",
            threads=4,
            logger=None,
            temp_audiofile=temp_audio,
            ffmpeg_params=["-pix_fmt", "yuv420p"],
        )
    finally:
        if final is not None:
            final.close()
        if video is not None:
            video.close()
        narration.close()
        if bgm is not None:
            try:
                bgm.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("Видеорендерер не создал итоговый файл")
    return output_path
