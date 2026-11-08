"""Render the numbered AniFlow art panels as one silent, sequential MP4."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from pipeline.recap_script_writer import count_words, target_video_duration_seconds


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def export_numbered_panels(
    panels: list[dict[str, Any]],
    export_dir: str,
    script_text: str,
) -> dict[str, Any]:
    """Copy already-cropped panel images in reading order and write a manifest.

    This is an export/numbering step only. It does not detect, crop, filter,
    transform, or regenerate images.
    """
    if not panels:
        raise ValueError("Нет готовых изображений для экспорта")

    root = Path(export_dir)
    numbered_dir = root / "numbered_panels"
    numbered_dir.mkdir(parents=True, exist_ok=True)
    for item in numbered_dir.iterdir():
        if item.is_file():
            item.unlink()

    entries = []
    for number, panel in enumerate(panels, start=1):
        source = Path(str(panel.get("path") or ""))
        if not source.is_file():
            raise FileNotFoundError(f"Подготовленный кадр не найден: {source}")
        suffix = source.suffix.lower() or ".jpg"
        filename = f"{number:06d}{suffix}"
        destination = numbered_dir / filename
        shutil.copy2(source, destination)
        entries.append({
            "number": number,
            "filename": filename,
            "panel_id": panel.get("panel_id"),
            "source_panel_id": panel.get("source_panel_id", panel.get("panel_id")),
            "chapter": panel.get("source_chapter"),
            "original_path": str(source),
            "export_path": str(destination),
        })

    word_count = count_words(script_text)
    duration = target_video_duration_seconds(word_count)
    script_path = root / "script.txt"
    script_path.write_text((script_text or "").strip() + "\n", encoding="utf-8")

    manifest = {
        "panel_count": len(entries),
        "word_count": word_count,
        "target_duration_seconds": duration,
        "target_duration_hms": _format_duration(duration),
        "seconds_per_word": 0.72,
        "panels": entries,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "numbered_dir": str(numbered_dir),
        "script_path": str(script_path),
        "manifest_path": str(manifest_path),
        "panel_count": len(entries),
        "word_count": word_count,
        "duration_seconds": duration,
        "duration_hms": _format_duration(duration),
        "panels": entries,
    }


def render_silent_recap_video(
    panels: list[dict[str, Any]],
    script_text: str,
    output_path: str,
    *,
    resolution: str = "1080p_landscape",
    fps: int = 30,
    quality: str = "medium",
    animation_style: str = "auto",
    progress_callback=None,
) -> dict[str, Any]:
    """Render every existing panel sequentially at 0.72 sec per script word.

    There is intentionally no audio input, TTS, audio stream, music, or timeline
    alignment. Each panel receives an equal share of the target video duration.
    """
    from moviepy import concatenate_videoclips
    from pipeline import compositor

    if not panels:
        raise ValueError("Нет готовых изображений для видео")
    word_count = count_words(script_text)
    duration = target_video_duration_seconds(word_count)
    if duration <= 0:
        raise ValueError("Сценарий пустой: невозможно рассчитать длительность видео")

    width, height = compositor.RESOLUTION_MAP.get(resolution, (1920, 1080))
    fps = int(fps) if int(fps) in compositor.FPS_OPTIONS else 30
    seconds_per_panel = duration / len(panels)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    clips = []
    final_video = None
    try:
        for index, panel in enumerate(panels):
            if progress_callback:
                progress_callback(index, len(panels), f"Сборка немого видео: кадр {index + 1}/{len(panels)}")
            motion = animation_style or "auto"
            if motion == "auto":
                motion = ("zoom_in", "slide_left", "zoom_out", "slide_right")[index % 4]
            clip = compositor._make_panel_clip(
                panel, width, height, seconds_per_panel, fps, index,
                "blur", None, motion,
            )
            clips.append(clip.with_duration(seconds_per_panel))

        final_video = concatenate_videoclips(clips, method="compose")
        if abs(float(final_video.duration) - duration) > 1.0 / fps:
            final_video = final_video.with_duration(duration)

        bitrate = {"low": "2500k", "medium": "5000k", "high": "8000k"}.get(quality, "5000k")
        if progress_callback:
            progress_callback(len(panels), len(panels), "Экспорт беззвучного MP4…")
        final_video.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio=False,
            bitrate=bitrate,
            preset="medium",
            threads=4,
            logger=None,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-an"],
        )
    finally:
        if final_video is not None:
            final_video.close()
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("Не удалось создать немое видео")
    return {
        "video_path": output_path,
        "word_count": word_count,
        "duration_seconds": duration,
        "duration_hms": _format_duration(duration),
        "panel_count": len(panels),
        "seconds_per_word": 0.72,
    }


def add_youtube_package_to_export(
    export_dir: str,
    *,
    titles: list[dict[str, Any]],
    description: str,
    pinned_comment: str,
    selected_title: dict[str, Any] | None,
    thumbnails: list[dict[str, Any]],
) -> dict[str, str]:
    """Copy generated YouTube assets into the silent-video export folder."""
    root = Path(export_dir)
    root.mkdir(parents=True, exist_ok=True)
    thumbs_dir = root / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for item in thumbnails or []:
        source = Path(str(item.get("path") or ""))
        if not source.is_file():
            continue
        target = thumbs_dir / source.name
        shutil.copy2(source, target)
        copied.append(str(target))

    package = {
        "titles": titles or [],
        "selected_title": selected_title,
        "description": description or "",
        "pinned_comment": pinned_comment or "",
        "thumbnails": [
            {
                key: value for key, value in item.items()
                if key not in {"path"}
            }
            for item in (thumbnails or [])
        ],
    }
    (root / "youtube_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "title_options.txt").write_text(
        "\n".join(
            f"{index}. {item.get('title', '')}"
            for index, item in enumerate(titles or [], start=1)
        ) + "\n",
        encoding="utf-8",
    )
    (root / "description.txt").write_text(
        (description or "").rstrip() + "\n", encoding="utf-8"
    )
    (root / "pinned_comment.txt").write_text(
        (pinned_comment or "").rstrip() + "\n", encoding="utf-8"
    )
    return {
        "package_json": str(root / "youtube_package.json"),
        "titles_txt": str(root / "title_options.txt"),
        "description_txt": str(root / "description.txt"),
        "pinned_comment_txt": str(root / "pinned_comment.txt"),
        "thumbnail_dir": str(thumbs_dir),
        "copied_thumbnails": len(copied),
    }


def build_silent_recap_export(
    panels: list[dict[str, Any]],
    script_text: str,
    export_dir: str,
    *,
    resolution: str = "1080p_landscape",
    fps: int = 30,
    quality: str = "medium",
    animation_style: str = "auto",
    progress_callback=None,
) -> dict[str, Any]:
    """Create script, numbered panels, manifest, and one silent MP4."""
    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    numbered = export_numbered_panels(panels, str(export_path), script_text)
    video_path = str(export_path / "full_recap_silent.mp4")
    video = render_silent_recap_video(
        panels, script_text, video_path,
        resolution=resolution, fps=fps, quality=quality,
        animation_style=animation_style, progress_callback=progress_callback,
    )
    package = {**numbered, **video, "export_dir": str(export_path)}
    summary_path = export_path / "export.json"
    summary_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    package["summary_path"] = str(summary_path)
    return package
