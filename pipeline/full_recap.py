"""Generate one coherent Russian recap script with semantic visual cues.

This module intentionally does not create narration per panel or per scene.
Panels provide source context; the result is one complete script plus metadata
that tells the editor which panels illustrate portions of that script.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable


SYSTEM_PROMPT_RU = """Ты профессиональный автор русскоязычных пересказов манги, манхвы и комиксов для YouTube.
Пиши естественно, увлекательно и связно, как рассказчик, который объясняет зрителю историю.
Сохраняй хронологию, причинно-следственные связи и характеры персонажей. Не выдумывай события,
мотивы, имена или детали, которых нет в исходных материалах. Не пересказывай каждую панель
отдельной подписью. Не используй фразы «на этом кадре», «на следующей картинке» и технические
комментарии. Не копируй длинные оригинальные реплики дословно. Результат должен быть на русском
языке и подходить для непрерывной дикторской озвучки."""


def build_panel_context(
    panels: list[dict[str, Any]],
    backend: Any,
    vision_model: str,
    *,
    scene_size: int = 5,
    timeout: int = 180,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Read the images in their existing reading order and collect visual notes.

    The vision helper describes each source image. It does not write narration,
    produce audio, or decide the final shot duration.
    """
    if not panels:
        raise ValueError("Нет изображений для анализа")

    from pipeline.scene_narrator import group_into_scenes, _extract_visual_beat_for_panel

    scenes = group_into_scenes(panels, scene_size=max(1, int(scene_size)))
    total = len(panels)
    completed = 0
    contexts: list[dict[str, Any]] = []

    for scene_index, scene_panels in enumerate(scenes, start=1):
        if cancel_check and cancel_check():
            raise InterruptedError("Анализ изображений отменён")

        scene_items = []
        for panel in scene_panels:
            if cancel_check and cancel_check():
                raise InterruptedError("Анализ изображений отменён")

            panel_id = panel.get("panel_id")
            note = _extract_visual_beat_for_panel(
                panel, backend, vision_model, timeout=timeout
            )
            scene_items.append({
                "panel_id": panel_id,
                "visual_note": (note or "").strip(),
                "dialogue": (panel.get("text") or panel.get("dialogue") or "").strip(),
                "panel_type": panel.get("panel_type", "standard"),
            })
            completed += 1
            if progress_callback:
                progress_callback(completed, total, f"Анализ изображений: {completed}/{total}")

        contexts.append({
            "scene_id": f"scene_{scene_index:03d}",
            "panels": scene_items,
        })

    return contexts


def _extract_json_object(raw: str) -> dict[str, Any] | None:
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


def generate_full_recap_script(
    scene_contexts: list[dict[str, Any]],
    backend: Any,
    text_model: str,
    *,
    cast_characters: list[str] | None = None,
    style_profile: str = "Динамичный, естественный русскоязычный пересказ для YouTube.",
    story_context: str = "",
    timeout: int = 240,
    max_tokens: int = 9000,
) -> dict[str, Any]:
    """Generate one full text and semantic cue map with one LLM request."""
    import llm_transport

    if not scene_contexts:
        raise ValueError("Нет проанализированных сцен")

    known_ids: dict[str, Any] = {}
    context_lines: list[str] = []
    for scene in scene_contexts:
        context_lines.append(f"\n[{scene.get('scene_id', 'scene')}]")
        for panel in scene.get("panels", []):
            panel_id = panel.get("panel_id")
            if panel_id is None:
                continue
            known_ids[str(panel_id)] = panel_id
            context_lines.append(
                f"Панель {panel_id}: {panel.get('visual_note') or 'описание отсутствует'}. "
                f"Распознанный текст: {panel.get('dialogue') or 'нет'}."
            )

    if not known_ids:
        raise ValueError("В контексте не найдено ни одной панели")

    context_blob = "\n".join(context_lines)
    if len(context_blob) > 180_000:
        raise ValueError(
            "Слишком большой объём визуального контекста для одного запроса. "
            "Сначала обработайте меньше глав или используйте режим пакетного анализа."
        )

    cast = ", ".join(
        item.strip() for item in (cast_characters or [])
        if isinstance(item, str) and item.strip()
    )
    prompt = f"""Создай один полноценный, связный пересказ всего материала ниже.

СТИЛЬ:
{style_profile}

ИЗВЕСТНЫЕ ПЕРСОНАЖИ:
{cast or 'Не заданы; не придумывай имена.'}

КОНТЕКСТ ИСТОРИИ:
{story_context or 'Дополнительного контекста нет.'}

СЦЕНЫ И ПАНЕЛИ В ПОРЯДКЕ ЧТЕНИЯ:
{context_blob}

ТРЕБОВАНИЯ К full_text:
- Только русский язык; один цельный рассказ, а не набор подписей к картинкам.
- Связывай события логично и причинно-следственно, убирай повторы.
- Не добавляй событий, которых нет в исходном материале.
- Не используй заголовки, списки, номера панелей или указания монтажёру.
- Не подгоняй объём под фиксированную длительность.

ТРЕБОВАНИЯ К visual_cues:
- Разбей весь рассказ на естественные смысловые отрезки.
- Не используй правило «одно предложение — одна картинка».
- text каждого cue должен быть точным непрерывным фрагментом full_text.
- panel_ids — одна или несколько панелей, которые действительно иллюстрируют этот фрагмент.
- Одна панель может оставаться подходящей на протяжении нескольких предложений.
- Используй только ID из переданного материала.
- Покрой cue весь рассказ по порядку, не создавай лишние короткие отрезки.

Верни только JSON:
{{
  "full_text": "Полный непрерывный русский сценарий...",
  "visual_cues": [
    {{"text": "дословный фрагмент full_text", "panel_ids": [1, 2]}}
  ]
}}"""

    raw = llm_transport.as_transport(backend).chat(
        text_model,
        prompt,
        system=SYSTEM_PROMPT_RU,
        temperature=0.55,
        top_p=0.9,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    parsed = _extract_json_object(raw)
    full_text = str((parsed or {}).get("full_text") or (raw if parsed is None else "")).strip()
    if not full_text:
        raise ValueError("Модель вернула пустой сценарий")

    cues = (parsed or {}).get("visual_cues", [])
    valid_cues = []
    for cue in cues if isinstance(cues, list) else []:
        if not isinstance(cue, dict):
            continue
        cue_text = str(cue.get("text") or "").strip()
        ids = [
            known_ids[str(panel_id)]
            for panel_id in (cue.get("panel_ids") or [])
            if str(panel_id) in known_ids
        ]
        if cue_text and cue_text.casefold() in full_text.casefold() and ids:
            valid_cues.append({"text": cue_text, "panel_ids": ids})

    if not valid_cues:
        valid_cues = [{
            "text": full_text,
            "panel_ids": list(known_ids.values()),
            "fallback": True,
        }]

    return {
        "full_text": full_text,
        "visual_cues": valid_cues,
        "panel_ids": list(known_ids.values()),
        "language": "ru",
    }
