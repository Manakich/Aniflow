"""Align semantic visual cues to one continuous narration audio track.

Timestamps are used only by the video editor. This module never edits, splits,
slows down, or re-synthesizes the narration audio.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


TOKEN_RE = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
SRT_TIME_RE = re.compile(
    r"(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)


def _tokens(text: str) -> list[str]:
    return [m.group(0).casefold().replace("ё", "е") for m in TOKEN_RE.finditer(text or "")]


def _seconds(match: re.Match, prefix: str) -> float:
    return (
        int(match.group(prefix + "h")) * 3600
        + int(match.group(prefix + "m")) * 60
        + int(match.group(prefix + "s"))
        + int(match.group(prefix + "ms")) / 1000.0
    )


def parse_srt_word_timestamps(srt_text: str) -> list[dict[str, Any]]:
    """Parse word-level Edge-TTS SRT; spread phrase cues as an approximation."""
    output = []
    for block in re.split(r"\n\s*\n", (srt_text or "").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_line = next((line for line in lines if "-->" in line), None)
        if not timing_line:
            continue
        match = SRT_TIME_RE.search(timing_line)
        if not match:
            continue
        start, end = _seconds(match, "s"), _seconds(match, "e")
        words = _tokens(" ".join(line for line in lines if "-->" not in line and not line.isdigit()))
        if not words or end < start:
            continue
        step = (end - start) / len(words)
        for index, word in enumerate(words):
            output.append({
                "word": word,
                "start": start + step * index,
                "end": end if index == len(words) - 1 else start + step * (index + 1),
                "source": "srt_approximation",
            })
    return output


def transcribe_word_timestamps(
    audio_path: str,
    *,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
) -> list[dict[str, Any]]:
    """Fallback for TTS engines that do not expose word-boundary timestamps."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Для синхронизации установите faster-whisper либо используйте Edge TTS "
            "с доступными временными метками."
        ) from exc

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        audio_path, language="ru", word_timestamps=True, vad_filter=True
    )
    words = []
    for segment in segments:
        for word in getattr(segment, "words", None) or []:
            token = (getattr(word, "word", "") or "").strip()
            if token:
                words.append({
                    "word": token,
                    "start": float(word.start),
                    "end": float(word.end),
                    "source": "faster_whisper",
                })
    return words


def align_script_tokens(
    full_text: str,
    word_timestamps: list[dict[str, Any]],
    audio_duration: float,
) -> list[dict[str, Any]]:
    """Map script tokens to ASR/TTS times; interpolate words ASR did not match."""
    script = _tokens(full_text)
    if not script:
        return []
    duration = max(0.001, float(audio_duration))

    heard = []
    for item in word_timestamps or []:
        words = _tokens(str(item.get("word", "")))
        if not words:
            continue
        start = float(item.get("start", 0.0))
        end = max(start, float(item.get("end", start)))
        step = (end - start) / len(words)
        for index, word in enumerate(words):
            heard.append({
                "token": word,
                "start": start + step * index,
                "end": end if index == len(words) - 1 else start + step * (index + 1),
            })

    matched: list[dict[str, float] | None] = [None] * len(script)
    matcher = SequenceMatcher(
        a=script, b=[item["token"] for item in heard], autojunk=False
    )
    known = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            si, hi = block.a + offset, block.b + offset
            matched[si] = {"start": heard[hi]["start"], "end": heard[hi]["end"]}
            known.append(si)

    if not known:
        step = duration / len(script)
        return [{
            "token": token, "start": step * index,
            "end": step * (index + 1), "confidence": 0.15,
        } for index, token in enumerate(script)]

    bounds = [-1] + known + [len(script)]
    for left, right in zip(bounds, bounds[1:]):
        missing = list(range(left + 1, right))
        if not missing:
            continue
        left_end = matched[left]["end"] if left >= 0 else 0.0
        right_start = matched[right]["start"] if right < len(script) else duration
        right_start = max(left_end, right_start)
        step = (right_start - left_end) / len(missing)
        for offset, index in enumerate(missing):
            matched[index] = {
                "start": left_end + step * offset,
                "end": left_end + step * (offset + 1),
            }

    result = []
    cursor = 0.0
    for index, (token, timing) in enumerate(zip(script, matched)):
        timing = timing or {"start": cursor, "end": cursor}
        start = max(cursor, min(duration, float(timing["start"])))
        end = max(start, min(duration, float(timing["end"])))
        result.append({
            "token": token,
            "start": start,
            "end": end,
            "confidence": 0.9 if index in known else 0.35,
        })
        cursor = end
    return result


def _find_phrase_span(tokens: list[str], phrase: str, start_at: int = 0):
    target = _tokens(phrase)
    if not target:
        return None
    last_start = len(tokens) - len(target)
    for start in range(max(0, start_at), last_start + 1):
        if tokens[start:start + len(target)] == target:
            return start, start + len(target)

    best, best_ratio = None, 0.0
    for start in range(max(0, start_at), last_start + 1):
        ratio = SequenceMatcher(
            a=target, b=tokens[start:start + len(target)], autojunk=False
        ).ratio()
        if ratio > best_ratio:
            best, best_ratio = (start, start + len(target)), ratio
    return best if best_ratio >= 0.72 else None


def build_visual_timeline(
    full_text: str,
    visual_cues: list[dict[str, Any]],
    word_timestamps: list[dict[str, Any]],
    audio_duration: float,
    fallback_panel_ids: list[Any] | None = None,
) -> dict[str, Any]:
    """Create contiguous shots covering the full audio; pauses hold the last image."""
    duration = max(0.001, float(audio_duration))
    aligned = align_script_tokens(full_text, word_timestamps, duration)
    tokens = [item["token"] for item in aligned]
    raw_shots = []
    search_cursor = 0

    for cue in visual_cues or []:
        if not isinstance(cue, dict):
            continue
        span = _find_phrase_span(tokens, str(cue.get("text") or ""), search_cursor)
        panel_ids = cue.get("panel_ids") or []
        if not span or not panel_ids:
            continue
        start_index, end_index = span
        search_cursor = end_index
        start = aligned[start_index]["start"]
        end = aligned[end_index - 1]["end"]
        if end <= start:
            continue

        # Multiple panels may illustrate one phrase. Start with equal intervals;
        # users can later refine these in the visual timeline editor.
        step = (end - start) / len(panel_ids)
        for index, panel_id in enumerate(panel_ids):
            raw_shots.append({
                "panel_id": panel_id,
                "start": start + step * index,
                "end": end if index == len(panel_ids) - 1 else start + step * (index + 1),
                "confidence": 0.2 if cue.get("fallback") else 0.85,
            })

    if not raw_shots:
        ids = list(fallback_panel_ids or [])
        if not ids:
            raise ValueError("Нет панелей для построения визуального таймлайна")
        step = duration / len(ids)
        raw_shots = [{
            "panel_id": panel_id,
            "start": step * index,
            "end": duration if index == len(ids) - 1 else step * (index + 1),
            "confidence": 0.15,
        } for index, panel_id in enumerate(ids)]

    raw_shots.sort(key=lambda item: (item["start"], item["end"]))
    motions = ["slow_zoom_in", "slow_pan_left", "slow_zoom_out", "slow_pan_right"]
    shots = []
    cursor = 0.0
    for item in raw_shots:
        start = max(0.0, min(duration, float(item["start"])))
        end = max(0.0, min(duration, float(item["end"])))
        if end <= cursor:
            continue
        if not shots:
            start = 0.0
        else:
            start = max(cursor, start)
            if start > cursor:
                shots[-1]["end"] = round(start, 3)
        if end <= start:
            continue
        shots.append({
            "panel_id": item["panel_id"],
            "start": round(start, 3),
            "end": round(end, 3),
            "motion": motions[len(shots) % len(motions)],
            "confidence": float(item.get("confidence", 0.5)),
        })
        cursor = end

    if not shots:
        raise ValueError("Не удалось построить визуальный таймлайн")

    shots[-1]["end"] = round(duration, 3)
    merged = []
    for shot in shots:
        if merged and str(merged[-1]["panel_id"]) == str(shot["panel_id"]):
            merged[-1]["end"] = shot["end"]
            merged[-1]["confidence"] = min(
                merged[-1]["confidence"], shot["confidence"]
            )
        else:
            merged.append(shot)

    return {
        "audio_duration": duration,
        "alignment_method": (
            word_timestamps[0].get("source") if word_timestamps else "interpolated"
        ),
        "entries": merged,
    }
