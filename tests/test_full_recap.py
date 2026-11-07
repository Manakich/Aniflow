import json
import os
import sys
import types

from pipeline.audio_alignment import (
    align_script_tokens,
    build_visual_timeline,
    parse_srt_word_timestamps,
)
from pipeline.full_recap_audio import generate_full_narration_audio


def test_full_tts_sends_one_complete_text_request(tmp_path):
    calls = []
    output = tmp_path / "full.mp3"

    def fake_synthesize(**kwargs):
        calls.append(kwargs)
        output.write_bytes(b"audio")
        return {"audio_path": str(output), "duration": 8.0}

    result = generate_full_narration_audio(
        "Это полный текст. В нём два предложения.",
        str(output),
        engine="elevenlabs",
        voice="russian-voice",
        synthesize_fn=fake_synthesize,
    )

    assert len(calls) == 1
    assert calls[0]["text"] == "Это полный текст. В нём два предложения."
    assert result["generation_mode"] == "single_full_text_request"
    assert result["audio_path"] == str(output)


def test_full_tts_rejects_empty_script_without_request(tmp_path):
    calls = []
    try:
        generate_full_narration_audio(
            "  ", str(tmp_path / "empty.mp3"),
            synthesize_fn=lambda **kwargs: calls.append(kwargs),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected empty script to fail")
    assert calls == []


def test_srt_word_timestamps_are_parsed():
    srt = """1
00:00:01,000 --> 00:00:03,000
Привет герой

2
00:00:03,000 --> 00:00:04,000
вошел
"""
    words = parse_srt_word_timestamps(srt)
    assert [item["word"] for item in words] == ["привет", "герой", "вошел"]
    assert words[0]["start"] == 1.0
    assert words[1]["end"] == 3.0


def test_visual_timeline_can_use_multiple_panels_for_one_phrase():
    text = "Герой вошел в замок и увидел дракона."
    words = [
        {"word": "Герой", "start": 0.0, "end": 1.2},
        {"word": "вошел", "start": 1.2, "end": 2.5},
        {"word": "в", "start": 2.5, "end": 2.8},
        {"word": "замок", "start": 2.8, "end": 4.2},
        {"word": "и", "start": 4.2, "end": 4.5},
        {"word": "увидел", "start": 4.5, "end": 6.3},
        {"word": "дракона", "start": 6.3, "end": 8.0},
    ]
    timeline = build_visual_timeline(
        text,
        [{"text": text, "panel_ids": [1, 2, 3]}],
        words,
        audio_duration=9.0,
        fallback_panel_ids=[1, 2, 3],
    )
    entries = timeline["entries"]
    assert [item["panel_id"] for item in entries] == [1, 2, 3]
    assert entries[0]["start"] == 0.0
    assert entries[-1]["end"] == 9.0
    assert all(entries[i]["end"] <= entries[i + 1]["end"] for i in range(len(entries) - 1))


def test_same_panel_can_cover_more_than_one_sentence():
    text = "Он вошел в замок. Затем герой нашел дракона."
    words = [
        {"word": "Он", "start": 0.0, "end": 0.3},
        {"word": "вошел", "start": 0.3, "end": 0.8},
        {"word": "в", "start": 0.8, "end": 0.9},
        {"word": "замок", "start": 0.9, "end": 1.5},
        {"word": "Затем", "start": 2.0, "end": 2.4},
        {"word": "герой", "start": 2.4, "end": 2.8},
        {"word": "нашел", "start": 2.8, "end": 3.3},
        {"word": "дракона", "start": 3.3, "end": 4.0},
    ]
    timeline = build_visual_timeline(
        text,
        [{"text": "Он вошел в замок", "panel_ids": [10]},
         {"text": "Затем герой нашел дракона", "panel_ids": [10]}],
        words,
        audio_duration=5.0,
        fallback_panel_ids=[10],
    )
    assert len(timeline["entries"]) == 1
    assert timeline["entries"][0]["panel_id"] == 10
    assert timeline["entries"][0]["start"] == 0.0
    assert timeline["entries"][0]["end"] == 5.0


def test_alignment_interpolates_unmatched_script_words():
    aligned = align_script_tokens(
        "Главный герой внезапно исчез",
        [{"word": "герой", "start": 1.0, "end": 1.5}],
        audio_duration=4.0,
    )
    assert len(aligned) == 4
    assert aligned[0]["start"] == 0.0
    assert aligned[-1]["end"] <= 4.0
    assert all(item["end"] >= item["start"] for item in aligned)


def test_timeline_holds_previous_panel_during_pause():
    text = "Герой вошел в замок. После паузы он увидел дракона."
    words = [
        {"word": "Герой", "start": 0.0, "end": 0.5},
        {"word": "вошел", "start": 0.5, "end": 1.0},
        {"word": "в", "start": 1.0, "end": 1.1},
        {"word": "замок", "start": 1.1, "end": 1.8},
        {"word": "После", "start": 4.0, "end": 4.5},
        {"word": "паузы", "start": 4.5, "end": 5.0},
        {"word": "он", "start": 5.0, "end": 5.2},
        {"word": "увидел", "start": 5.2, "end": 5.8},
        {"word": "дракона", "start": 5.8, "end": 6.5},
    ]
    timeline = build_visual_timeline(
        text,
        [{"text": "Герой вошел в замок", "panel_ids": [1]},
         {"text": "После паузы он увидел дракона", "panel_ids": [2]}],
        words,
        audio_duration=8.0,
        fallback_panel_ids=[1, 2],
    )
    first, second = timeline["entries"]
    assert first["start"] == 0.0
    assert first["end"] == second["start"]
    assert first["end"] >= 4.0
    assert second["end"] == 8.0


def test_full_script_is_generated_in_one_llm_call_and_panel_ids_are_valid(monkeypatch):
    from pipeline.full_recap import generate_full_recap_script

    calls = []

    class FakeTransport:
        def chat(self, model, prompt, **kwargs):
            calls.append({"model": model, "prompt": prompt, **kwargs})
            return json.dumps({
                "full_text": "Герой открывает дверь. За ней появляется дракон.",
                "visual_cues": [
                    {"text": "Герой открывает дверь", "panel_ids": [1]},
                    {"text": "За ней появляется дракон", "panel_ids": [2, 999]},
                ],
            }, ensure_ascii=False)

    monkeypatch.setitem(
        sys.modules,
        "llm_transport",
        types.SimpleNamespace(as_transport=lambda backend: FakeTransport()),
    )

    result = generate_full_recap_script(
        [{"scene_id": "scene_001", "panels": [
            {"panel_id": 1, "visual_note": "Герой открывает дверь"},
            {"panel_id": 2, "visual_note": "За дверью дракон"},
        ]}],
        backend=object(),
        text_model="test-model",
    )

    assert len(calls) == 1
    assert result["full_text"] == "Герой открывает дверь. За ней появляется дракон."
    assert result["visual_cues"][1]["panel_ids"] == [2]


def test_short_narration_cue_does_not_create_rapid_visual_cuts():
    text = "Герой внезапно открыл древнюю дверь."
    words = [
        {"word": "Герой", "start": 0.0, "end": 0.45},
        {"word": "внезапно", "start": 0.45, "end": 0.95},
        {"word": "открыл", "start": 0.95, "end": 1.35},
        {"word": "древнюю", "start": 1.35, "end": 1.8},
        {"word": "дверь", "start": 1.8, "end": 2.4},
    ]
    timeline = build_visual_timeline(
        text,
        [{"text": text, "panel_ids": [1, 2, 3, 4, 5]}],
        words,
        audio_duration=3.0,
        fallback_panel_ids=[1, 2, 3, 4, 5],
    )
    assert len(timeline["entries"]) == 1
    assert timeline["entries"][0]["panel_id"] == 1
    assert timeline["entries"][0]["end"] == 3.0
