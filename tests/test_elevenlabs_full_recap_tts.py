import base64

import pytest

from pipeline.elevenlabs_tts import ElevenLabsTTS


def test_elevenlabs_character_alignment_maps_russian_words():
    text = "Привет, герой!"
    starts = [index * 0.1 for index in range(len(text))]
    ends = [start + 0.08 for start in starts]
    words = ElevenLabsTTS._character_alignment_to_words(
        text,
        {
            "characters": list(text),
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    )
    assert [item["word"] for item in words] == ["Привет", "герой"]
    assert words[0]["start"] == 0.0
    assert words[1]["start"] > words[0]["start"]
    assert words[1]["source"] == "elevenlabs_character_alignment"


def test_elevenlabs_character_alignment_rejects_normalized_text_mismatch():
    words = ElevenLabsTTS._character_alignment_to_words(
        "Текст оригинала",
        {
            "characters": list("Текст нормализован"),
            "character_start_times_seconds": [0.1] * 18,
            "character_end_times_seconds": [0.2] * 18,
        },
    )
    assert words == []


def test_elevenlabs_full_recap_uses_one_flash_request_and_returns_timestamps(monkeypatch, tmp_path):
    client = ElevenLabsTTS()
    client.set_api_key("test-key")
    text = "Привет герой"
    starts = [index * 0.1 for index in range(len(text))]
    ends = [start + 0.08 for start in starts]
    payloads = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "audio_base64": base64.b64encode(b"fake-mp3-bytes").decode("ascii"),
                "alignment": {
                    "characters": list(text),
                    "character_start_times_seconds": starts,
                    "character_end_times_seconds": ends,
                },
            }

    def fake_post(url, **kwargs):
        payloads.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("pipeline.elevenlabs_tts.requests.post", fake_post)
    monkeypatch.setattr(client, "_get_audio_duration", lambda path: 1.2)

    result = client.generate_speech_with_timestamps(
        text, str(tmp_path / "full.mp3"), voice="voice-123"
    )

    assert len(payloads) == 1
    assert payloads[0][0].endswith("/text-to-speech/voice-123/with-timestamps")
    assert payloads[0][1]["json"]["model_id"] == "eleven_flash_v2_5"
    assert payloads[0][1]["json"]["language_code"] == "ru"
    assert result["duration"] == 1.2
    assert [item["word"] for item in result["word_timestamps"]] == ["Привет", "герой"]
    assert (tmp_path / "full.mp3").read_bytes() == b"fake-mp3-bytes"


def test_elevenlabs_full_recap_rejects_over_limit_without_network_request(monkeypatch, tmp_path):
    client = ElevenLabsTTS()
    client.set_api_key("test-key")
    calls = []
    monkeypatch.setattr(
        "pipeline.elevenlabs_tts.requests.post",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(RuntimeError, match="40,000"):
        client.generate_speech_with_timestamps(
            "я" * 40001, str(tmp_path / "too-long.mp3"), voice="voice-123"
        )
    assert calls == []
