"""Long-form Russian manhwa recap writer built on AniFlow's existing panel extraction."""
from __future__ import annotations

import re
from typing import Any, Callable

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[’'-][A-Za-zА-Яа-яЁё0-9]+)*", re.UNICODE)

RECAP_STYLE_PROFILE_RU = """Подробный, динамичный русскоязычный пересказ манги/манхвы для YouTube.

Подача и структура:
- Начни с цепляющей завязки, сильного противоречия или необычной ситуации из этой истории.
  Не начинай с приветствия каналу, имени автора или просьбы поставить лайк.
- Быстро представь главного героя и его исходное положение, затем развивай историю
  последовательно, сохраняя хронологию и причинно-следственные связи.
- Пиши как уверенный разговорный рассказчик, который пересказывает сюжет другу.
  Предложения должны легко восприниматься на слух: меняй длину и ритм, делай
  естественные переходы между сценами и сюжетными линиями.
- Подробно раскрывай важные действия, решения, мотивацию, конфликты, развитие героя,
  способности, систему уровней, правила мира, планы и последствия. Не пропускай
  детали, без которых следующий поворот становится непонятным.
- Сильные повороты и эмоциональные моменты подавай через контраст и темп, но не
  превращай каждую фразу в кликбейт.

Авторский голос:
- Добавляй короткие уместные замечания, иронию, сарказм и риторические вопросы,
  когда это естественно вытекает из поступка персонажа или абсурдности ситуации.
- Юмор должен разбавлять повествование, а не перебивать каждую сцену. Допускаются
  живые разговорные формулировки; мат и грубость — редко и только если оправданы.
- Не используй постоянные обращения к зрителю, навязчивые мемы, одинаковые шутки
  и однотипные эмоциональные восклицания.

Работа с источником:
- Это самостоятельный пересказ, а не перевод и не переписывание реплик по порядку.
  Передавай диалоги преимущественно косвенной речью и своими словами.
- Не выдумывай события, имена, числа, отношения, способности, мотивы и исходы.
  Если OCR испорчен или визуальный факт неясен, не делай категоричных выводов.
- Не копируй фразы, шутки, приветствия, фирменные обращения или абзацы каналов-
  референсов. Перенимай только общие приёмы повествования.
- Не пиши монтажные комментарии вроде «на этой картинке» или «в следующем кадре»,
  не вставляй таймкоды, главы-списки, технические пометки и просьбы поставить лайк.
- Если предоставленный материал заканчивается на клиффхэнгере, закончи на нём,
  не сочиняя отсутствующее продолжение."""


SYSTEM_PROMPT_RU = """Ты профессиональный сценарист русскоязычных YouTube-пересказов манги и манхвы.
Пиши полноценный самостоятельный сюжетный пересказ, а не подписи к кадрам.
Извлечённые реплики используй только как источник фактов и передавай их своими
словами, преимущественно косвенной речью. Не копируй длинные оригинальные реплики.
Не выдумывай имена, способности, числа, мотивы, отношения, события и исходы.
Соблюдай причинно-следственные связи и хронологию. Если OCR ошибочный или
неразборчивый, не делай из него неподтверждённых выводов.
Не используй фразы «на этой картинке», «на следующем кадре», «автор показывает».
Избегай повторяющихся связок, пустого кликбейта, таймкодов, списков и технических
комментариев. Пиши на естественном русском языке. Если история обрывается,
честно закончи на клиффхэнгере."""


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def target_video_duration_seconds(word_count: int) -> float:
    if word_count < 0:
        raise ValueError("Количество слов не может быть отрицательным")
    return round(int(word_count) * 0.72, 3)


def build_panel_context(panels: list[dict[str, Any]], scene_size: int = 20) -> list[dict[str, Any]]:
    """Group the already-cropped AniFlow panels without filtering or model calls."""
    if not panels:
        raise ValueError("Нет готовых панелей. Сначала выполните штатную обработку AniFlow.")
    scenes = []
    size = max(1, int(scene_size))
    for start in range(0, len(panels), size):
        group = panels[start:start + size]
        scenes.append({
            "scene_id": f"scene_{len(scenes) + 1:03d}",
            "panels": [
                {
                    "panel_id": panel.get("panel_id"),
                    "sequence_number": panel.get("sequence_number", start + offset + 1),
                    "source_chapter": panel.get("source_chapter"),
                    "visual_note": (panel.get("visual_description") or panel.get("visual_note") or "").strip(),
                    "dialogue": (panel.get("text") or panel.get("dialogue") or "").strip(),
                }
                for offset, panel in enumerate(group)
            ],
        })
    return scenes


def _flatten_context(scene_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [panel for scene in scene_contexts for panel in scene.get("panels", [])]


def _make_batches(panels: list[dict[str, Any]], batch_size: int = 70) -> list[list[dict[str, Any]]]:
    return [panels[index:index + batch_size] for index in range(0, len(panels), batch_size)]


def _allocate_word_targets(weights: list[int], total_words: int) -> list[int]:
    """Allocate an exact word target proportionally without negative tail batches."""
    if not weights:
        return []
    total_words = max(1, int(total_words))
    positive = [max(1, int(weight)) for weight in weights]
    total_weight = sum(positive)
    allocated = []
    cumulative_weight = 0
    previous_boundary = 0
    for weight in positive:
        cumulative_weight += weight
        boundary = round(total_words * cumulative_weight / total_weight)
        allocated.append(boundary - previous_boundary)
        previous_boundary = boundary
    return allocated


def generate_full_recap_script(
    scene_contexts: list[dict[str, Any]],
    backend: Any,
    text_model: str,
    *,
    style_profile: str = RECAP_STYLE_PROFILE_RU,
    story_context: str = "",
    target_words: int = 5000,
    timeout: int = 360,
    max_tokens: int = 9000,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Generate a long connected recap in chronological writing batches."""
    import llm_transport

    panels = _flatten_context(scene_contexts)
    if not panels:
        raise ValueError("Нет подготовленных панелей для сценария")

    batches = _make_batches(panels)
    weights = [
        max(1, sum(len(p.get("visual_note", "")) + len(p.get("dialogue", "")) + 1 for p in batch))
        for batch in batches
    ]
    chunk_targets = _allocate_word_targets(weights, target_words)

    transport = llm_transport.as_transport(backend)
    parts: list[str] = []
    previous_context = ""
    for index, (batch, words_for_part) in enumerate(zip(batches, chunk_targets), start=1):
        if progress_callback:
            progress_callback(index - 1, len(batches), f"Написание сценария: часть {index}/{len(batches)}")

        source = []
        for panel in batch:
            source.append(
                f"Глава {panel.get('source_chapter', '—')}, кадр {panel.get('sequence_number')}, "
                f"ID {panel.get('panel_id')}: {panel.get('visual_note') or 'визуальное описание отсутствует'}. "
                f"Извлечённый текст: {panel.get('dialogue') or 'нет'}."
            )

        prompt = f"""Напиши часть {index} из {len(batches)} единого подробного пересказа.

СТИЛЬ:
{style_profile}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ИСТОРИИ:
{story_context or 'Не задан.'}

ПРЕДЫДУЩАЯ ЧАСТЬ ДЛЯ НЕПРЕРЫВНОСТИ:
{previous_context[-5000:] or 'Это начало истории.'}

СОБЫТИЯ В ПОРЯДКЕ ЧТЕНИЯ:
{chr(10).join(source)}

ЦЕЛЕВОЙ ОБЪЁМ ЭТОЙ ЧАСТИ: примерно {words_for_part} слов.
Продолжай с того места, где закончилась предыдущая часть. Не повторяй начало
истории и уже пересказанные события. Пересказывай события своими словами, а
реплики передавай преимущественно косвенной речью. Подробно объясняй важные
поступки, мотивы, способности, правила мира, конфликты и последствия. Сохраняй
все ключевые факты. В первой части сделай естественную сюжетную завязку; в следующих
частях не начинай историю заново и не добавляй новые приветствия.
Не заполняй объём пустыми фразами. Не используй заголовок части, списки, номера
кадров, диалоги от первого лица и технические комментарии.
Верни только связный русский текст сценария."""

        response = transport.chat(
            text_model,
            prompt,
            system=SYSTEM_PROMPT_RU,
            temperature=0.62,
            top_p=0.92,
            max_tokens=min(max_tokens, max(1800, int(words_for_part * 2.1))),
            timeout=timeout,
        )
        part = str(response or "").strip()
        if not part:
            raise RuntimeError(f"Модель вернула пустую часть сценария {index}/{len(batches)}")
        parts.append(part)
        previous_context = "\n\n".join(parts)
        if progress_callback:
            progress_callback(index, len(batches), f"Готова часть {index}/{len(batches)}")

    full_text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip()
    words = count_words(full_text)
    if not full_text:
        raise ValueError("Модель не вернула сценарий")

    return {
        "full_text": full_text,
        "word_count": words,
        "target_words": int(target_words),
        "target_duration_seconds": target_video_duration_seconds(words),
        "panel_ids": [panel.get("panel_id") for panel in panels],
        "writing_batches": len(batches),
        "language": "ru",
        "style_profile": "recap_competitor_blend_v1",
    }
