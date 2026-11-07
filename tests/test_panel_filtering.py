import sys
import types

from PIL import Image

from pipeline import full_recap


def _fake_group_into_scenes(panels, scene_size=5):
    return [panels[index:index + scene_size] for index in range(0, len(panels), scene_size)]


def test_panel_context_skips_blank_and_exact_duplicate_but_keeps_story_panels(monkeypatch, tmp_path):
    keep_path = tmp_path / "keep.png"
    duplicate_path = tmp_path / "duplicate.png"
    blank_path = tmp_path / "blank.png"

    Image.new("RGB", (80, 80), (100, 30, 20)).save(keep_path)
    # Same bytes, copied to another path: exact duplicate should be removed.
    duplicate_path.write_bytes(keep_path.read_bytes())
    Image.new("RGB", (80, 80), (255, 255, 255)).save(blank_path)

    scene_module = types.SimpleNamespace(group_into_scenes=_fake_group_into_scenes)
    monkeypatch.setitem(sys.modules, "pipeline.scene_narrator", scene_module)
    monkeypatch.setattr(
        full_recap,
        "_extract_recap_panel_note",
        lambda panel, backend, vision_model, timeout=180: (
            True, "Главный герой стоит перед дверью", ""
        ),
    )

    progress = []
    contexts = full_recap.build_panel_context(
        [
            {"panel_id": 1, "path": str(keep_path)},
            {"panel_id": 2, "path": str(duplicate_path)},
            {"panel_id": 3, "path": str(blank_path)},
        ],
        backend=object(),
        vision_model="test",
        scene_size=5,
        progress_callback=lambda current, total, message: progress.append((current, total)),
    )

    story_scenes = [scene for scene in contexts if scene["scene_id"] != "filter_summary"]
    summary = next(scene for scene in contexts if scene["scene_id"] == "filter_summary")
    panels = [panel for scene in story_scenes for panel in scene["panels"]]

    assert [panel["panel_id"] for panel in panels] == [1]
    assert panels[0]["sequence_number"] == 1
    assert summary["kept_count"] == 1
    assert summary["skipped_count"] == 2
    assert {item["reason"] for item in summary["skipped_panels"]} == {
        "exact duplicate", "uniform blank background"
    }
    assert progress[-1] == (3, 3)


def test_vision_skip_response_is_parsed_and_uncertainty_keeps_panel(monkeypatch, tmp_path):
    image_path = tmp_path / "panel.png"
    Image.new("RGB", (64, 64), (50, 80, 90)).save(image_path)

    scene_module = types.SimpleNamespace(
        _encode_image_small=lambda path, max_side: "fake-image-data",
        MAX_IMG_SIDE_ALL=640,
    )
    monkeypatch.setitem(sys.modules, "pipeline.scene_narrator", scene_module)

    class FakeTransport:
        def __init__(self, answer):
            self.answer = answer

        def chat(self, *args, **kwargs):
            return self.answer

    monkeypatch.setitem(
        sys.modules,
        "llm_transport",
        types.SimpleNamespace(
            as_transport=lambda backend: FakeTransport("SKIP: рекламная страница")
        ),
    )
    keep, note, reason = full_recap._extract_recap_panel_note(
        {"panel_id": 4, "path": str(image_path)}, object(), "test"
    )
    assert keep is False
    assert note == ""
    assert reason == "рекламная страница"

    monkeypatch.setitem(
        sys.modules,
        "llm_transport",
        types.SimpleNamespace(
            as_transport=lambda backend: FakeTransport("KEEP: герой входит в комнату")
        ),
    )
    keep, note, reason = full_recap._extract_recap_panel_note(
        {"panel_id": 5, "path": str(image_path)}, object(), "test"
    )
    assert keep is True
    assert note == "герой входит в комнату"
