"""Synthesize one complete recap script into one continuous audio file."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable


def _edge_single_request(text: str, output_path: str, *, voice=None, rate=None, pitch=None):
    """Use AniFlow's Edge-TTS single stream (audio + word boundaries)."""
    from pipeline.tts_engine import _generate_speech_edge_single_stream

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_generate_speech_edge_single_stream(
            text, output_path, voice=voice, rate=rate, pitch=pitch
        ))
    raise RuntimeError("TTS должен запускаться в рабочем потоке, а не внутри event loop")


def generate_full_narration_audio(
    full_text: str,
    output_path: str,
    *,
    engine: str = "edge",
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    speed: float = 1.0,
    elevenlabs_model: str = "eleven_multilingual_v2",
    synthesize_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send the whole script to the selected TTS engine exactly once.

    There is intentionally no chunking, per-panel synthesis, duration fitting,
    or automatic re-generation. Alignment happens later and never changes audio.
    """
    text = (full_text or "").strip()
    if not text:
        raise ValueError("Сценарий пустой — озвучивать нечего")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if synthesize_fn is not None:
        result = synthesize_fn(
            text=text, output_path=output_path, voice=voice,
            rate=rate, pitch=pitch, engine=engine, speed=speed,
        )
    elif engine == "edge":
        result = _edge_single_request(
            text, output_path, voice=voice, rate=rate, pitch=pitch
        )
    elif engine == "elevenlabs":
        # The legacy wrapper defaults to a monolingual English model.
        # Full Recap defaults to the multilingual model for Russian narration.
        from pipeline.elevenlabs_tts import get_elevenlabs_tts
        client = get_elevenlabs_tts()
        if not client.available:
            raise RuntimeError("ElevenLabs API key is not configured")
        result = client.generate_speech(
            text, output_path, voice=voice, model=elevenlabs_model
        )
    else:
        from pipeline.tts_engine import generate_speech
        result = generate_speech(
            text=text, output_path=output_path, voice=voice,
            rate=rate, pitch=pitch, engine=engine, speed=speed,
        )

    if not isinstance(result, dict):
        raise RuntimeError("TTS-провайдер вернул неожиданный результат")

    audio_path = result.get("audio_path") or output_path
    if not os.path.isfile(audio_path) or os.path.getsize(audio_path) <= 0:
        raise RuntimeError("TTS не создал непустой аудиофайл")

    return {
        **result,
        "audio_path": audio_path,
        "script_characters": len(text),
        "generation_mode": "single_full_text_request",
    }
