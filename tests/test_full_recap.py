import json
import sys
import types

from pipeline.recap_script_writer import (
    RECAP_STYLE_PROFILE_RU,
    SYSTEM_PROMPT_RU,
    _allocate_word_targets,
    build_panel_context,
    count_words,
    generate_full_recap_script,
    merge_chapter_panels,
    target_video_duration_seconds,
)


def test_word_count_to_silent_video_duration():
    assert target_video_duration_seconds(5000) == 3600.0
    assert target_video_duration_seconds(10000) == 7200.0
    assert target_video_duration_seconds(0) == 0.0
    assert count_words("Один, два! Три — четыре.") == 4


def test_panel_context_preserves_all_existing_panels_without_filtering():
    panels = [
        {"panel_id": 1, "sequence_number": 1, "visual_description": "герой входит в комнату", "text": "Кто здесь?"},
        {"panel_id": 2, "sequence_number": 2, "visual_description": "", "text": ""},
        {"panel_id": 3, "sequence_number": 3, "visual_description": "герой входит в комнату", "text": "Кто здесь?"},
    ]
    scenes = build_panel_context(panels, scene_size=2)
    flattened = [panel for scene in scenes for panel in scene["panels"]]
    assert [panel["panel_id"] for panel in flattened] == [1, 2, 3]
    assert flattened[1]["visual_note"] == ""
    assert flattened[2]["visual_note"] == "герой входит в комнату"
    assert flattened[0]["dialogue"] == "Кто здесь?"


def test_merge_chapter_panels_assigns_unique_ids_and_sequential_numbers():
    merged = merge_chapter_panels([
        (12, [{"panel_id": 1, "path": "chapter12/panel1.png"},
              {"panel_id": 2, "path": "chapter12/panel2.png"}]),
        (13, [{"panel_id": 1, "path": "chapter13/panel1.png"}]),
    ])
    assert [panel["panel_id"] for panel in merged] == [
        "ch00012_1", "ch00012_2", "ch00013_1"
    ]
    assert [panel["sequence_number"] for panel in merged] == [1, 2, 3]
    assert [panel["source_chapter"] for panel in merged] == [12, 12, 13]


def test_long_recap_is_written_in_chronological_batches(monkeypatch):
    calls = []

    class FakeTransport:
        def chat(self, model, prompt, **kwargs):
            calls.append({"model": model, "prompt": prompt, **kwargs})
            return "Герой продолжает путь и сталкивается с новым испытанием. " * 25

    monkeypatch.setitem(
        sys.modules,
        "llm_transport",
        types.SimpleNamespace(as_transport=lambda backend: FakeTransport()),
    )
    panels = [
        {
            "panel_id": index,
            "sequence_number": index,
            "visual_description": f"событие номер {index}",
            "text": f"важная реплика {index}",
        }
        for index in range(1, 72)
    ]
    context = build_panel_context(panels, scene_size=20)
    result = generate_full_recap_script(
        context,
        backend=object(),
        text_model="test-model",
        target_words=1000,
    )

    assert len(calls) == 2
    assert "часть 1 из 2" in calls[0]["prompt"]
    assert "часть 2 из 2" in calls[1]["prompt"]
    assert "Герой продолжает путь" in calls[1]["prompt"]
    assert result["word_count"] == count_words(result["full_text"])
    assert result["target_words"] == 1000
    assert result["target_duration_seconds"] == result["word_count"] * 0.72
    assert result["panel_ids"] == list(range(1, 72))


def test_competitor_blended_profile_is_original_and_paraphrase_focused():
    assert "косвенной" in SYSTEM_PROMPT_RU
    assert "Не копируй" in RECAP_STYLE_PROFILE_RU
    assert "иронией" in RECAP_STYLE_PROFILE_RU



def test_word_targets_are_exact_and_never_negative_for_many_batches():
    weights = [100 + (index % 7) for index in range(200)]
    targets = _allocate_word_targets(weights, 10000)
    assert len(targets) == len(weights)
    assert sum(targets) == 10000
    assert all(target >= 0 for target in targets)


def test_word_target_allocator_handles_single_and_empty_batches():
    assert _allocate_word_targets([10], 5000) == [5000]
    assert _allocate_word_targets([], 5000) == []
