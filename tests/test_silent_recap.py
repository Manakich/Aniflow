import json
import sys
import types
from pathlib import Path

from PIL import Image

from pipeline.full_recap_renderer import (
    export_numbered_panels,
    render_silent_recap_video,
)


def test_export_numbered_panels_copies_existing_crops_in_order(tmp_path):
    source_dir = tmp_path / "original_crop2"
    source_dir.mkdir()
    panels = []
    for index in range(1, 4):
        source = source_dir / f"panel_{index:03d}.png"
        Image.new("RGB", (40, 40), (index * 20, 0, 0)).save(source)
        panels.append({
            "panel_id": f"chapter_1_{index}",
            "source_chapter": 1,
            "sequence_number": index,
            "path": str(source),
        })

    result = export_numbered_panels(panels, str(tmp_path / "export"), " ".join(["слово"] * 5000))
    numbered = Path(result["numbered_dir"])
    assert sorted(path.name for path in numbered.iterdir()) == [
        "000001.png", "000002.png", "000003.png"
    ]
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert [item["panel_id"] for item in manifest["panels"]] == [
        "chapter_1_1", "chapter_1_2", "chapter_1_3"
    ]
    assert result["word_count"] == 5000
    assert result["duration_seconds"] == 3600.0
    assert result["duration_hms"] == "01:00:00"
    # Original Crop 2 files are still in place; export only copies them.
    assert all(Path(panel["path"]).is_file() for panel in panels)


def test_silent_renderer_explicitly_disables_audio(monkeypatch, tmp_path):
    from pipeline import compositor
    import pipeline.full_recap_renderer as renderer

    calls = []

    class FakeClip:
        def __init__(self, duration):
            self.duration = duration

        def with_duration(self, duration):
            self.duration = duration
            return self

        def close(self):
            pass

    class FakeFinalVideo(FakeClip):
        def write_videofile(self, path, **kwargs):
            calls.append(kwargs)
            Path(path).write_bytes(b"silent-mp4")
            return None

    monkeypatch.setattr(
        compositor,
        "_make_panel_clip",
        lambda panel, width, height, duration, fps, index, bg_mode, custom_bg, motion: FakeClip(duration),
    )
    monkeypatch.setattr(
        sys.modules.get("moviepy") or __import__("moviepy"),
        "concatenate_videoclips",
        lambda clips, method="compose": FakeFinalVideo(sum(clip.duration for clip in clips)),
    )

    panels = [
        {"panel_id": 1, "path": "unused-1.jpg"},
        {"panel_id": 2, "path": "unused-2.jpg"},
    ]
    output = tmp_path / "video.mp4"
    result = render_silent_recap_video(
        panels,
        " ".join(["слово"] * 10),
        str(output),
        fps=30,
    )

    assert output.read_bytes() == b"silent-mp4"
    assert result["duration_seconds"] == 7.2
    assert calls[0]["audio"] is False
    assert "-an" in calls[0]["ffmpeg_params"]
