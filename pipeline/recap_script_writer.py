"""Long-form Russian manhwa recap writer built on AniFlow's existing panel extraction."""
from __future__ import annotations

import re
from typing import Any, Callable

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[’'-][A-Za-zА-Яа-яЁё0-9]+)*", re.UNICODE)

RECAP_STYLE_PROFILE_RU = """Единый редакционный профиль для длинных русскоязычных пересказов манги/манхвы. Это оригинальная смесь общих приёмов из приложенных успешных сценариев: подробного сюжетного изложения, энергичной разговорной подачи, ироничных авторских ремарок и ясного объяснения игровых/магических систем. Не копируй узнаваемую манеру одного конкретного канала.

1. ЗАХОД И УДЕРЖАНИЕ
- Начинай не с приветствия, а с самой цепляющей завязки: необычной ситуации, противоречия, унизительного положения героя, смертельной угрозы или неожиданного поворота.
- Первые 3–6 предложений должны быстро дать зрителю причину смотреть дальше и обозначить центральную интригу.
- После крючка коротко представь героя и исходное положение. Не растягивай вступление общими словами.
- Внутри пересказа создавай небольшие сюжетные крючки на переходах: что герой обнаружил, почему привычный план провалился, какая новая угроза появилась.

2. ПОВЕСТВОВАНИЕ
- Основной голос — уверенный, живой рассказчик от третьего лица, который объясняет историю другу.
- Излагай события последовательно и подробно: кто что сделал, чего хотел, почему принял решение, к чему это привело и что изменилось после.
- Не превращай текст в перечень панелей. Объединяй несколько кадров в одну сцену, а одну важную сцену раскрывай несколькими абзацами.
- Чередуй короткие ударные фразы, средние предложения и более длинные объяснения. Ритм должен быть удобен для слуха, без длинных монотонных конструкций.
- Используй естественные переходы между местами, персонажами и временными линиями. Не повторяй постоянно «тем временем», «в этот момент», «как оказалось».
- Не пересказывай одно и то же дважды ради объёма. Объём набирай раскрытием реальных событий, мотивации, правил мира и последствий.

3. АВТОРСКИЙ ГОЛОС И ЮМОР
- Добавляй короткие комментарии рассказчика, когда ситуация абсурдна, герой ведёт себя нелепо, противник самоуверен или система выдаёт странное правило.
- Используй лёгкую иронию, сухой сарказм, неожиданные бытовые сравнения, самоиронию и иногда риторический вопрос. Комментарии должны усиливать сцену, а не перебивать её.
- Можно использовать разговорные слова и живую интонацию; грубость и мат — редко, только когда органичны событию.
- Не превращай каждое предложение в шутку. Между смешными ремарками оставляй место серьёзным, эмоциональным и напряжённым моментам.
- Не обращайся к зрителю в каждом абзаце, не придумывай постоянное прозвище аудитории и не используй чужие фирменные приветствия, мемы или словечки.

4. ОБЪЯСНЕНИЕ СИСТЕМЫ И МИРА
- Если в истории есть уровни, ранги, навыки, квесты, магия, способности, экономика или правила мира, объясняй их простым языком при первом появлении.
- Показывай практический эффект способности: что герой теперь может сделать, почему это важно и как меняет баланс сил.
- Сложные правила раскрывай через пример из текущей сцены, а не через длинную энциклопедическую справку.
- В боевых сценах передавай последовательность действий, преимущество сторон, неожиданный приём, цену победы и последствия.

5. ДИАЛОГИ И ФАКТЫ
- Это самостоятельный пересказ сюжета, а не перевод манги и не переписывание реплик по очереди.
- Передавай диалоги преимущественно косвенной речью и собственными словами. Прямую короткую цитату оставляй только тогда, когда без неё теряется важная мысль или комический эффект.
- Сохраняй имена, отношения, последовательность событий, способности, числа и важные детали только в той мере, в какой они подтверждаются исходными кадрами и извлечённым текстом.
- Не добавляй мысли персонажа, которых нельзя вывести из материала. Если мотив неясен, описывай действие, а не выдумывай объяснение.
- Ошибки OCR/распознавания, обрывки фраз, повторы и случайные слова не повторяй. Если имя или термин распознан сомнительно, используй нейтральное обозначение или контекстно подтверждённый вариант.

6. СТРУКТУРА ДЛИННОГО ВЫПУСКА
- В начале — сильная завязка и быстрое знакомство с главным конфликтом.
- В основной части — подробное хронологическое развитие, мотивация, препятствия, открытия, второстепенные персонажи и эскалация ставок.
- Важные повороты подавай через контраст: ожидание героя против реальности, его слабость против скрытой силы, слова персонажа против поступков.
- Между сюжетными блоками используй короткие переходы, но не начинай историю заново.
- Если несколько глав продолжают одну сцену, сохраняй непрерывность и не делай искусственных вступлений к каждой главе.
- Если исходный материал обрывается, честно закончи на последнем подтверждённом событии или клиффхэнгере.

7. ЧЕГО НЕ ДЕЛАТЬ
- Не копируй фразы, абзацы, шутки, обращения к аудитории или узнаваемые формулировки из приложенных сценариев.
- Не копируй оригинальные диалоги большими фрагментами.
- Не выдумывай сюжет ради целевого количества слов.
- Не используй монтажные комментарии вроде «на этой картинке», «следующий кадр», «сейчас мы видим».
- Не вставляй приветствия каналу, просьбы лайкнуть, подписаться, рекламные блоки, таймкоды, заголовки глав, списки или технические пометки в сам сценарий.
- Не имитируй ошибки распознавания речи из текстовых файлов. Они являются шумом транскрипции, а не частью авторского стиля.

Цель: подробный, легко слушаемый пересказ с темпом и ясностью успешных длинных recap-видео, с заметным, но дозированным характером рассказчика и полностью оригинальными формулировками."""


SYSTEM_PROMPT_RU = """Ты пишешь оригинальный подробный русскоязычный пересказ манги/манхвы для YouTube.
Следуй стилевому профилю и опирайся только на факты из переданного материала.
Не копируй реплики, диалоги и формулировки источника длинными фрагментами: пересказывай своими словами,
обычно косвенной речью. Не копируй узнаваемые фразы или шутки каналов-референсов.
Не выдумывай имена, числа, отношения, способности, мотивы, события и исходы.
Соблюдай хронологию, причинно-следственные связи и непрерывность между частями.
Игнорируй явные ошибки OCR, обрывки и повторы распознавания.
Пиши живым разговорным русским языком, чередуй короткие и средние предложения,
используй уместную иронию дозированно. Не добавляй приветствия, CTA, рекламу,
таймкоды, списки, названия глав или комментарии о кадрах.
Если данных не хватает, не заполняй пробел фантазией; осторожно опиши подтверждённое действие.
Если исходник обрывается, закончи на последнем подтверждённом событии."""


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


def merge_chapter_panels(
    chapter_panels: list[tuple[int, list[dict[str, Any]]]]
) -> list[dict[str, Any]]:
    """Merge already-cropped panels from chapters with stable unique IDs.

    Panel files are reused as-is; this helper only adds metadata and does not
    open, filter, crop, resize or otherwise process image files.
    """
    merged: list[dict[str, Any]] = []
    sequence = 0
    for chapter_number, panels in chapter_panels:
        for panel in panels:
            sequence += 1
            item = dict(panel)
            original_id = panel.get("panel_id", sequence)
            safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(original_id)).strip("_") or str(sequence)
            item["source_chapter"] = int(chapter_number)
            item["source_panel_id"] = original_id
            item["panel_id"] = f"ch{int(chapter_number):05d}_{safe_id}"
            item["sequence_number"] = sequence
            merged.append(item)
    return merged


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
