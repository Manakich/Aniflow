"""Generate one coherent Russian recap script with semantic visual cues.

This module intentionally does not create narration per panel or per scene.
Panels provide source context; the result is one complete script plus metadata
that tells the editor which panels illustrate portions of that script.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Callable


SYSTEM_PROMPT_RU = """Ты профессиональный автор русскоязычных пересказов манги, манхвы и комиксов для YouTube.
Пиши естественно, увлекательно и связно, как рассказчик, который объясняет зрителю историю.
Сохраняй хронологию, причинно-следственные связи и характеры персонажей. Не выдумывай события,
мотивы, имена или детали, которых нет в исходных материалах. Не пересказывай каждую панель
отдельной подписью. Не используй фразы «на этом кадре», «на следующей картинке» и технические
комментарии. Не копируй длинные оригинальные реплики дословно. Результат должен быть на русском
языке и подходить для непрерывной дикторской озвучки."""


def _quick_blank_reason(image_path: str) -> str:
    """Catch only truly blank single-colour pages; preserve story-relevant scenery."""
    if not image_path or not os.path.isfile(image_path):
        return ""
    try:
        from PIL import Image, ImageStat
        with Image.open(image_path) as source:
            image = source.convert("L")
            image.thumbnail((64, 64), Image.Resampling.LANCZOS)
            stat = ImageStat.Stat(image)
            mean = stat.mean[0]
            deviation = stat.stddev[0]
            if deviation < 1.0 and (mean > 252 or mean < 3):
                return "uniform blank background"
    except Exception:
        return ""
    return ""


def _extract_recap_panel_note(
    panel: dict[str, Any],
    backend: Any,
    vision_model: str,
    timeout: int = 180,
) -> tuple[bool, str, str]:
    """Return keep flag, grounded description, and optional skip reason."""
    from pipeline.scene_narrator import _encode_image_small, MAX_IMG_SIDE_ALL
    import llm_transport

    image_path = panel.get("path", "")
    if not image_path or not os.path.isfile(image_path):
        return True, "", "image path unavailable"

    image = _encode_image_small(image_path, MAX_IMG_SIDE_ALL)
    if not image:
        return True, "", "image could not be encoded"

    prompt = """Ты фильтруешь панели манги/манхвы для сюжетного YouTube-пересказа.

Сначала реши, полезно ли это изображение для понимания истории.

KEEP — если есть персонаж, действие, эмоция, важный предмет, сюжетный текст,
значимое место или атмосферный establishing shot, который объясняет сцену.
Даже если в кадре нет человека, сохрани его, когда локация или событие важны.

SKIP — только если это действительно пустой однотонный фон, декоративный
разделитель без сюжетного смысла, техническая страница, рекламный/промо-блок,
логотип/кредиты, водяной знак или изображение, которое не добавляет ничего к истории.

Если сомневаешься — обязательно KEEP. Не отбрасывай важные пейзажи, интерьеры
или кадры-переходы, если они раскрывают место или атмосферу.

Верни строго одну строку:
KEEP: краткое фактическое описание изображения
или
SKIP: короткая причина

Не выдумывай персонажей и события."""
    try:
        raw = llm_transport.as_transport(backend).chat(
            vision_model, prompt, [image],
            temperature=0.1, top_p=0.8, max_tokens=220, timeout=timeout,
        )
        raw = (raw or "").strip()
        if re.match(r"^SKIP(?:\\s*:|\\s|$)", raw, flags=re.IGNORECASE):
            return False, "", raw.split(":", 1)[-1].strip() or "vision model marked as non-story"
        if raw.upper().startswith("KEEP:"):
            raw = raw.split(":", 1)[-1].strip()
        return True, raw, ""
    except Exception as exc:
        # An unavailable vision pass must not silently delete story artwork.
        print(f"[FullRecap] Panel classification failed for {panel.get('panel_id')}: {exc}")
        return True, "", "vision classification unavailable"


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

    from pipeline.scene_narrator import group_into_scenes

    scenes = []
    total = len(panels)
    completed = 0
    contexts: list[dict[str, Any]] = []
    seen_hashes = set()
    kept_panels = []
    skipped = []

    # First pass: exact duplicate and truly blank panel filtering.
    for panel in panels:
        if cancel_check and cancel_check():
            raise InterruptedError("Анализ изображений отменён")
        image_path = panel.get("path", "")
        blank_reason = _quick_blank_reason(image_path)
        if blank_reason:
            skipped.append({"panel_id": panel.get("panel_id"), "reason": blank_reason})
            completed += 1
            if progress_callback:
                progress_callback(completed, total, f"Пропуск пустого кадра: {completed}/{total}")
            continue
        if image_path and os.path.isfile(image_path):
            try:
                with open(image_path, "rb") as image_file:
                    fingerprint = hashlib.sha256(image_file.read()).digest()
                if fingerprint in seen_hashes:
                    skipped.append({"panel_id": panel.get("panel_id"), "reason": "exact duplicate"})
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total, f"Пропуск дубликата: {completed}/{total}")
                    continue
                seen_hashes.add(fingerprint)
            except OSError:
                pass
        kept_panels.append(panel)

    # Second pass: vision model marks decorative/non-story pages. If it is unsure,
    # the panel is kept. Every accepted panel receives a sequential display number.
    vision_kept = []
    for panel in kept_panels:
        if cancel_check and cancel_check():
            raise InterruptedError("Анализ изображений отменён")
        keep, note, reason = _extract_recap_panel_note(
            panel, backend, vision_model, timeout=timeout
        )
        if keep:
            panel_copy = dict(panel)
            panel_copy["_full_recap_visual_note"] = note
            vision_kept.append(panel_copy)
        else:
            skipped.append({"panel_id": panel.get("panel_id"), "reason": reason})
        completed += 1
        if progress_callback:
            progress_callback(completed, total, f"Анализ и фильтрация изображений: {completed}/{total}")

    if not vision_kept:
        raise ValueError("После фильтрации не осталось содержательных изображений. Проверьте набор панелей.")

    scenes = group_into_scenes(vision_kept, scene_size=max(1, int(scene_size)))
    sequence_number = 0

    for scene_index, scene_panels in enumerate(scenes, start=1):
        if cancel_check and cancel_check():
            raise InterruptedError("Анализ изображений отменён")

        scene_items = []
        for panel in scene_panels:
            if cancel_check and cancel_check():
                raise InterruptedError("Анализ изображений отменён")

            sequence_number += 1
            panel_id = panel.get("panel_id")
            scene_items.append({
                "panel_id": panel_id,
                "sequence_number": sequence_number,
                "visual_note": (panel.get("_full_recap_visual_note") or "").strip(),
                "dialogue": (panel.get("text") or panel.get("dialogue") or "").strip(),
                "panel_type": panel.get("panel_type", "standard"),
            })

        contexts.append({
            "scene_id": f"scene_{scene_index:03d}",
            "panels": scene_items,
        })

    contexts.append({
        "scene_id": "filter_summary",
        "panels": [],
        "kept_count": sequence_number,
        "skipped_count": len(skipped),
        "skipped_panels": skipped,
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
