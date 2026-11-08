"""Generate title ideas and three YouTube thumbnails for a Full Recap project.

Title generation uses AniFlow's configured LLM transport and a built-in style
profile derived from the user's uploaded channel examples. Thumbnail generation
uses the OpenAI Images edits endpoint with actual source panels and the built-in
visual profile; per-episode screenshots are optional overrides. API keys are
read from environment variables only.
"""
from __future__ import annotations

import base64
import json
import os
import re
import textwrap
import uuid
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont


ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_REFERENCE_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_COUNT = 16
THUMBNAIL_SIZE = (1280, 720)


DEFAULT_TITLE_STYLE_PROFILE_RU = """Встроенный редакционный профиль названий по предоставленным примерам успешных роликов:
- Сразу выноси в начало самое понятное и сильное событие: кем герой был, что неожиданно получил/сделал, против кого выступил и к чему это привело.
- Строй фразу на контрасте или перемене статуса: слабый → опасный, обычный → невероятный, изгнанник → сильнейший, ошибка → неожиданная выгода.
- Предпочитай конкретные глаголы действия и понятные ставки вместо абстрактного «невероятное приключение».
- Можно использовать одно акцентное слово ЗАГЛАВНЫМИ буквами или многоточие, но не превращай всё название в крик.
- Название должно интриговать, но обещать только то, что действительно раскрывается в сценарии.
- Не копируй готовые названия, синтаксис целиком, характерные словечки или фирменные формулировки из примеров.
- Делай три разных угла подачи: главный поворот истории; необычная способность/рост героя; конфликт или угроза с высокими ставками.
- Ориентир по длине — примерно 45–95 символов, если более короткая формулировка яснее и сильнее."""


DEFAULT_THUMBNAIL_STYLE_PROFILE_RU = """Встроенный визуальный профиль YouTube-превью по предоставленным примерам:
- Формат 16:9, очень высокий контраст и насыщенные цвета; композиция читается даже в маленьком размере.
- Один главный визуальный центр: крупное выразительное лицо героя, необычная способность, противник или драматичный момент.
- Добавляй короткую надпись на русском из 2–5 слов. Основной вариант оформления — крупный жирный жёлтый текст с толстой чёрной обводкой; для особо драматичной версии допустим белый/красный акцент.
- При необходимости используй одну заметную стрелку, круг или графический указатель, который помогает понять сюжетный крючок, а не просто украшает кадр.
- Варианты могут различаться по настроению: яркий/ироничный контраст; красно-чёрная драматичная угроза; эпичный fantasy/action или сравнение «до/после».
- Сохраняй узнаваемость персонажа по исходным панелям манги; не заменяй его случайным generic-аниме персонажем.
- Не копируй точную раскладку, текст, логотипы, водяные знаки или композицию чужого превью. Перенимай только общие принципы читаемости и визуальной иерархии."""


def _safe_name(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Разрешены только PNG, JPG и WEBP")
    return f"{uuid.uuid4().hex}{suffix}"


def save_reference_uploads(project_dir: str, kind: str, uploaded_files) -> list[dict[str, str]]:
    """Persist a group of browser-uploaded reference files inside the project."""
    if kind not in {"thumbnails", "titles"}:
        raise ValueError("Неизвестный тип референсов")
    folder = Path(project_dir) / "full_recap" / "references" / kind
    folder.mkdir(parents=True, exist_ok=True)

    saved = []
    existing = [p for p in folder.iterdir() if p.is_file()]
    if len(existing) >= MAX_REFERENCE_COUNT:
        raise ValueError(f"Можно хранить не более {MAX_REFERENCE_COUNT} референсов этого типа")

    for uploaded in uploaded_files:
        if not uploaded or not getattr(uploaded, "filename", ""):
            continue
        filename = _safe_name(uploaded.filename)
        target = folder / filename
        uploaded.save(str(target))
        if target.stat().st_size > MAX_REFERENCE_BYTES:
            target.unlink(missing_ok=True)
            raise ValueError("Размер одного референса не должен превышать 20 МБ")
        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            continue
        saved.append({
            "name": Path(uploaded.filename).name,
            "filename": filename,
            "path": str(target),
        })
        if len(existing) + len(saved) >= MAX_REFERENCE_COUNT:
            break
    return saved


def list_reference_files(project_dir: str, kind: str) -> list[dict[str, str]]:
    if kind not in {"thumbnails", "titles"}:
        raise ValueError("Неизвестный тип референсов")
    folder = Path(project_dir) / "full_recap" / "references" / kind
    if not folder.is_dir():
        return []
    return [
        {"filename": item.name, "path": str(item)}
        for item in sorted(folder.iterdir())
        if item.is_file() and item.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    ]


def clear_reference_files(project_dir: str, kind: str) -> int:
    """Remove the current project's reference set so the next video can use a new one."""
    if kind not in {"thumbnails", "titles"}:
        raise ValueError("Неизвестный тип референсов")
    folder = Path(project_dir) / "full_recap" / "references" / kind
    if not folder.is_dir():
        return 0
    removed = 0
    for item in folder.iterdir():
        if item.is_file() and item.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
            item.unlink()
            removed += 1
    return removed


def _image_as_data_url(path: str, max_side: int = 1280) -> str:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        import io
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=86, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _read_title_reference_style(
    reference_paths: list[str],
    backend: Any,
    vision_model: str,
) -> str:
    if not reference_paths:
        return "Референсы названий не загружены. Используй ясные, конкретные и интригующие русские формулировки."
    import llm_transport

    images = [_image_as_data_url(path, max_side=1200) for path in reference_paths[:8]]
    prompt = """Проанализируй приложенные скриншоты названий YouTube-видео.
Опиши именно ПРИНЦИПЫ оформления названий: длину, структуру фразы, тип крючка,
эмоциональность, использование цифр, регистра, многоточий и степень конкретики.
Если текст на скриншотах читается, приведи короткие примеры названий.
Не копируй названия дословно и не выдумывай нечитаемые слова.
Ответь по-русски в виде краткого списка правил для генерации новых названий."""
    return llm_transport.as_transport(backend).chat(
        vision_model, prompt, images,
        temperature=0.2, top_p=0.85, max_tokens=1200, timeout=180,
    ).strip()


def generate_title_options(
    full_script: str,
    visual_context: list[dict[str, Any]],
    backend: Any,
    text_model: str,
    *,
    title_reference_text: str = "",
    title_reference_paths: list[str] | None = None,
    vision_model: str | None = None,
) -> dict[str, Any]:
    """Generate three titles, one video description, and one pinned comment."""
    import llm_transport

    reference_style = (title_reference_text or DEFAULT_TITLE_STYLE_PROFILE_RU).strip()
    if title_reference_paths and vision_model:
        extracted = _read_title_reference_style(
            title_reference_paths, backend, vision_model
        )
        if extracted:
            reference_style = (reference_style + "\n" + extracted).strip()

    notes = []
    for scene in visual_context or []:
        for panel in scene.get("panels", []):
            note = (panel.get("visual_note") or "").strip()
            if note:
                notes.append(note)
    story_excerpt = (full_script or "").strip()
    if len(story_excerpt) > 16000:
        story_excerpt = story_excerpt[:11000] + "\n[...]\n" + story_excerpt[-5000:]

    prompt = f"""Ты редактор русскоязычного YouTube-канала с пересказами манги и манхвы.

СОДЕРЖАНИЕ ВЫПУСКА:
{story_excerpt}

ВИЗУАЛЬНЫЕ СОБЫТИЯ:
{chr(10).join(notes[:80])}

СТИЛЬ НАЗВАНИЙ (встроенный профиль + необязательные референсы этого выпуска):
{reference_style}

Сгенерируй ровно 3 РАЗНЫХ названия этого конкретного выпуска.
Требования:
- Русский язык.
- Каждый вариант должен отражать реальные события из сценария.
- Не обещай события, которых нет в выпуске.
- Не используй пустой кликбейт и одинаковые формулировки.
- Различай варианты по крючку: (1) резкий сюжетный поворот/необычная ситуация героя; (2) новая сила, талант или путь от слабости к превосходству; (3) главный конфликт, угроза или цена победы.
- Используй глаголы действия и ясный контраст статуса; допустимо выделить одно ключевое слово заглавными буквами, но не делай всё название капсом.
- Длина названия ориентировочно 45–95 символов, если стиль референсов не требует другого.
- Для каждого названия придумай короткую фразу на обложку (2–5 слов), которая не дублирует название целиком.
- Дополнительно напиши одно описание ролика на русском: 2–3 предложения с завязкой и главным конфликтом, затем короткий CTA и 5–10 релевантных хештегов. Не придумывай факты.
- Напиши один закреплённый комментарий: конкретный вопрос о поступке, выборе или повороте этой истории и короткое приглашение поделиться мнением.

Верни только JSON:
{{
  "titles": [
    {{"title": "...", "thumbnail_text": "...", "angle": "..."}}
  ],
  "description": "...",
  "pinned_comment": "..."
}}"""
    raw = llm_transport.as_transport(backend).chat(
        text_model, prompt,
        system="Ты точно следуешь фактам исходной истории и пишешь качественные русские YouTube-названия.",
        temperature=0.75, top_p=0.92, max_tokens=1200, timeout=180,
    )
    from pipeline.full_recap import _extract_json_object
    parsed = _extract_json_object(raw) or {}
    titles = parsed.get("titles", [])
    cleaned = []
    for item in titles if isinstance(titles, list) else []:
        if not isinstance(item, dict):
            continue
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        hook = re.sub(r"\s+", " ", str(item.get("thumbnail_text") or "")).strip()
        angle = re.sub(r"\s+", " ", str(item.get("angle") or "")).strip()
        if title and hook:
            cleaned.append({"title": title, "thumbnail_text": hook, "angle": angle})
    if len(cleaned) < 3:
        raise RuntimeError("Модель не вернула три корректных названия. Повторите генерацию.")

    description = re.sub(r"\n{3,}", "\n\n", str(parsed.get("description") or "")).strip()
    pinned_comment = re.sub(r"\s+", " ", str(parsed.get("pinned_comment") or "")).strip()
    if not description or not pinned_comment:
        raise RuntimeError("Модель не вернула описание или закреплённый комментарий.")
    return {
        "titles": cleaned[:3],
        "description": description,
        "pinned_comment": pinned_comment,
        "reference_style": reference_style,
    }


def _choose_panel_reference_paths(
    visual_context: list[dict[str, Any]],
    panels: list[dict[str, Any]],
    limit: int = 6,
) -> list[str]:
    panel_paths = {str(p.get("panel_id")): p.get("path") for p in panels}
    scored = []
    for scene in visual_context or []:
        for panel in scene.get("panels", []):
            note = (panel.get("visual_note") or "").lower()
            score = 0
            for token, weight in (
                ("face", 3), ("close-up", 3), ("выражение", 3), ("лицо", 3),
                ("fight", 2), ("fight", 2), ("сраж", 2), ("удар", 2),
                ("выстрел", 2), ("дракон", 2), ("монстр", 2), ("взрыв", 2),
                ("главный герой", 3), ("protagonist", 3), ("hero", 2),
            ):
                if token in note:
                    score += weight
            pid = panel.get("panel_id")
            path = panel_paths.get(str(pid))
            if path and os.path.isfile(path):
                scored.append((score, len(scored), path))
    # Prefer dramatic notes; preserve reading order for ties and remove exact paths.
    chosen, seen = [], set()
    for _score, _order, path in sorted(scored, key=lambda item: (-item[0], item[1])):
        if path not in seen:
            chosen.append(path)
            seen.add(path)
        if len(chosen) >= limit:
            break
    return chosen


def _thumbnail_prompt(
    variant: int,
    episode_script: str,
    title: dict[str, str],
    style_profile: str = DEFAULT_THUMBNAIL_STYLE_PROFILE_RU,
) -> str:
    concepts = [
        "A dramatic close-up of the main protagonist, strong readable facial expression, cinematic high contrast, clear separation from background.",
        "A dynamic action moment that captures the central conflict, strong diagonal composition, motion and energy, unmistakable focal point.",
        "A mysterious cinematic reveal showing the key threat or turning point, atmospheric depth, one dominant visual hook.",
    ]
    return f"""Create one polished YouTube thumbnail illustration for a Russian manhwa recap episode.

Use the supplied manga panels as content references for the characters, clothing, appearance and story world.
Use the supplied thumbnail reference images ONLY as guidance for composition, visual hierarchy, color treatment and overall visual style.
Do not copy any reference thumbnail literally. Do not reproduce another creator's logo, watermark or channel name.

CONCEPT {variant}: {concepts[variant - 1]}

EPISODE CONTEXT (for factual visual choices):
{episode_script[:5000]}

THUMBNAIL HOOK TO LEAVE ROOM FOR:
"{title.get('thumbnail_text', '')}"

VISUAL STYLE PROFILE:
{style_profile}

Composition requirements:
- 16:9 YouTube thumbnail, designed for small-screen readability.
- One dominant subject and one clear story moment; avoid clutter and tiny details.
- Keep a calm high-contrast area for a large Russian caption to be overlaid afterwards.
- High-quality colorful manhwa-inspired illustration, crisp silhouette, dramatic lighting.
- No text, letters, numbers, captions, logos or watermarks in the generated image. Text will be typeset separately.
"""


def _overlay_thumbnail_text(image_path: str, text: str, output_path: str) -> None:
    """Add reliable Russian typography after image generation (no AI text artifacts)."""
    with Image.open(image_path) as original:
        image = original.convert("RGB").resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_candidates = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    font = None
    for candidate in font_candidates:
        try:
            font = ImageFont.truetype(candidate, 88)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Hook text must stay short enough for a large, readable thumbnail caption.
    text = re.sub(r"\s+", " ", text or "").strip()[:48]
    max_width = 650
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font, stroke_width=4)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:3]
    if not lines:
        lines = ["МАНХВА"]

    x, y = 54, 720 - 54
    for line in reversed(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=5)
        height = bbox[3] - bbox[1]
        y -= height + 12
        draw.text(
            (x, y), line, font=font, fill=(255, 231, 0, 255),
            stroke_width=9, stroke_fill=(5, 5, 5, 255),
        )
        draw.text(
            (x, y), line, font=font, fill=(255, 231, 0, 255),
            stroke_width=1, stroke_fill=(255, 231, 0, 255),
        )

    combined = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    combined.save(output_path, format="JPEG", quality=94, optimize=True)


def generate_thumbnail_variants(
    project_dir: str,
    full_script: str,
    visual_context: list[dict[str, Any]],
    panels: list[dict[str, Any]],
    titles: list[dict[str, str]],
    *,
    api_key: str | None = None,
    model: str = "gpt-image-2",
    base_url: str = "https://api.openai.com/v1",
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Generate three reference-guided thumbnail edits through the Images API.

    Reference images are sent as multipart image[] file fields as required by
    the image edits endpoint. The generated image is returned as base64 JSON.
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Для генерации обложек добавьте OPENAI_API_KEY в локальное окружение и перезапустите приложение."
        )

    ref_dir = Path(project_dir) / "full_recap" / "references" / "thumbnails"
    reference_paths = [
        str(path) for path in sorted(ref_dir.iterdir())
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    ] if ref_dir.is_dir() else []
    panel_paths = _choose_panel_reference_paths(visual_context, panels, limit=6)
    # Global visual style is baked into DEFAULT_THUMBNAIL_STYLE_PROFILE_RU.
    # Episode-specific screenshots are optional overrides, never a prerequisite.
    image_paths = (reference_paths[:8] + panel_paths)[:MAX_REFERENCE_COUNT]
    if not panel_paths:
        panel_paths = [
            str(panel.get("path")) for panel in panels
            if panel.get("path") and os.path.isfile(str(panel.get("path")))
        ][:6]
        image_paths = (reference_paths[:8] + panel_paths)[:MAX_REFERENCE_COUNT]
    if not image_paths:
        raise RuntimeError("Не найдены готовые панели для создания превью. Сначала обработайте главы в AniFlow.")

    output_dir = Path(project_dir) / "full_recap" / "thumbnails"
    output_dir.mkdir(parents=True, exist_ok=True)
    endpoint = base_url.rstrip("/") + "/images/edits"
    generated = []

    for index in range(1, 4):
        if progress_callback:
            progress_callback(index - 1, 3, f"Генерация обложки {index}/3…")

        opened_files = []
        files = []
        try:
            for image_path in image_paths:
                handle = open(image_path, "rb")
                opened_files.append(handle)
                mime_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(Path(image_path).suffix.lower(), "application/octet-stream")
                files.append(("image[]", (Path(image_path).name, handle, mime_type)))

            form_data = {
                "model": model,
                "prompt": _thumbnail_prompt(
                    index, full_script, titles[index - 1],
                    style_profile=DEFAULT_THUMBNAIL_STYLE_PROFILE_RU,
                ),
                "size": "1280x720",
                "quality": "high",
                "output_format": "png",
                "n": "1",
            }
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                data=form_data,
                files=files,
                timeout=(45, 900),
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Images API HTTP {response.status_code}: {response.text[:1500]}"
                )
            payload = response.json()
            items = payload.get("data") or []
            if not items or not items[0].get("b64_json"):
                raise RuntimeError("Images API не вернул b64_json с изображением")

            raw_path = output_dir / f"thumbnail_{index:02d}_raw.png"
            raw_path.write_bytes(base64.b64decode(items[0]["b64_json"]))
            final_path = output_dir / f"thumbnail_{index:02d}.jpg"
            _overlay_thumbnail_text(
                str(raw_path),
                titles[index - 1].get("thumbnail_text", ""),
                str(final_path),
            )
            raw_path.unlink(missing_ok=True)

            generated.append({
                "index": index,
                "filename": final_path.name,
                "path": str(final_path),
                "title": titles[index - 1]["title"],
                "thumbnail_text": titles[index - 1]["thumbnail_text"],
                "angle": titles[index - 1].get("angle", ""),
            })
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка соединения с Images API: {exc}") from exc
        finally:
            for handle in opened_files:
                try:
                    handle.close()
                except Exception:
                    pass

        if progress_callback:
            progress_callback(index, 3, f"Готова обложка {index}/3")
    return generated