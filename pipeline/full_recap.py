"""Compatibility exports for the single-product Recap Studio pipeline.

All panel extraction and cropping are performed by AniFlow's original workflow.
This module contains no image filtering, detection, cropping, OCR or TTS logic.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pipeline.recap_script_writer import (
    RECAP_STYLE_PROFILE_RU,
    SYSTEM_PROMPT_RU,
    build_panel_context,
    count_words,
    generate_full_recap_script,
    merge_chapter_panels,
    target_video_duration_seconds,
)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object returned by a configured text model."""
    if not raw:
        return None
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
