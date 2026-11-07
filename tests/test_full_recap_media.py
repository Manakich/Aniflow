import base64
import io
import json
import sys
import types

from PIL import Image

from pipeline.full_recap_media import (
    generate_thumbnail_variants,
    generate_title_options,
    save_reference_uploads,
)


def test_save_reference_uploads_sanitizes_name_and_stores_file(tmp_path):
    class FakeUpload:
        filename = "../../thumbnail-reference.png"

        def save(self, path):
            with open(path, "wb") as file:
                file.write(b"fake image bytes")

    saved = save_reference_uploads(str(tmp_path), "thumbnails", [FakeUpload()])
    assert len(saved) == 1
    assert saved[0]["filename"].endswith(".png")
    assert "/" not in saved[0]["filename"]
    assert (tmp_path / "full_recap" / "references" / "thumbnails" / saved[0]["filename"]).exists()


def test_save_reference_uploads_rejects_non_image_extension(tmp_path):
    class FakeUpload:
        filename = "payload.txt"

        def save(self, path):
            raise AssertionError("save must not be called for rejected extensions")

    try:
        save_reference_uploads(str(tmp_path), "thumbnails", [FakeUpload()])
    except ValueError as exc:
        assert "PNG" in str(exc)
    else:
        raise AssertionError("Expected invalid extension to be rejected")


def test_generate_title_options_uses_one_llm_call_and_returns_three_titles(monkeypatch):
    calls = []

    class FakeTransport:
        def chat(self, model, prompt, **kwargs):
            calls.append({"model": model, "prompt": prompt, **kwargs})
            return json.dumps({
                "titles": [
                    {"title": "Он пробудил силу, которой боялся весь мир", "thumbnail_text": "СИЛА ПРОБУДИЛАСЬ", "angle": "power"},
                    {"title": "Один шаг героя превратил охоту в катастрофу", "thumbnail_text": "ОХОТА ОБЕРНУЛАСЬ УЖАСОМ", "angle": "twist"},
                    {"title": "В подземелье скрывалось то, что нельзя было разбудить", "thumbnail_text": "НЕ НАДО БЫЛО ЕГО БУДИТЬ", "angle": "mystery"},
                ]
            }, ensure_ascii=False)

    monkeypatch.setitem(
        sys.modules,
        "llm_transport",
        types.SimpleNamespace(as_transport=lambda backend: FakeTransport()),
    )

    result = generate_title_options(
        "Герой пробудил древнюю силу. Из подземелья вышел монстр.",
        [{"panels": [{"visual_note": "герой сражается с монстром"}]}],
        backend=object(),
        text_model="test-model",
    )
    assert len(calls) == 1
    assert len(result["titles"]) == 3
    assert result["titles"][0]["thumbnail_text"] == "СИЛА ПРОБУДИЛАСЬ"


def test_generate_three_reference_guided_thumbnails_with_exact_16_9_size(monkeypatch, tmp_path):
    ref_dir = tmp_path / "full_recap" / "references" / "thumbnails"
    ref_dir.mkdir(parents=True)
    reference = ref_dir / "style.png"
    Image.new("RGB", (640, 360), (25, 40, 70)).save(reference)

    panel_path = tmp_path / "panel_0001.jpg"
    Image.new("RGB", (640, 360), (100, 30, 20)).save(panel_path)

    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), (40, 50, 60)).save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"b64_json": image_b64}]}

    def fake_post(url, **kwargs):
        calls.append({"url": url, "payload": kwargs["json"]})
        return FakeResponse()

    monkeypatch.setattr("pipeline.full_recap_media.requests.post", fake_post)

    titles = [
        {"title": f"Вариант {index}", "thumbnail_text": f"ТЕКСТ {index}", "angle": "test"}
        for index in range(1, 4)
    ]
    variants = generate_thumbnail_variants(
        str(tmp_path),
        "История героя и его битва.",
        [{"panels": [{"panel_id": 1, "visual_note": "close-up of hero face"}]}],
        [{"panel_id": 1, "path": str(panel_path)}],
        titles,
        api_key="test-key",
    )

    assert len(calls) == 3
    assert len(variants) == 3
    assert all(call["url"].endswith("/images/edits") for call in calls)
    assert all(call["payload"]["size"] == "1280x720" for call in calls)
    assert all(call["payload"]["n"] == 1 for call in calls)
    assert len({call["payload"]["prompt"] for call in calls}) == 3
    for variant in variants:
        image = Image.open(variant["path"])
        assert image.size == (1280, 720)
        assert variant["filename"].endswith(".jpg")
