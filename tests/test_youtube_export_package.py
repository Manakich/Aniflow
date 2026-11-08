import json
from pathlib import Path

from pipeline.full_recap_renderer import add_youtube_package_to_export


def test_youtube_package_files_and_thumbnails_are_added_to_export(tmp_path):
    export_dir = tmp_path / "export"
    source_dir = tmp_path / "source_thumbnails"
    source_dir.mkdir()
    thumbnails = []
    for index in range(1, 4):
        path = source_dir / f"thumbnail_{index:02d}.jpg"
        path.write_bytes(f"image-{index}".encode("ascii"))
        thumbnails.append({
            "index": index,
            "filename": path.name,
            "path": str(path),
            "title": f"Название {index}",
            "thumbnail_text": f"ТЕКСТ {index}",
        })

    titles = [
        {"title": "Герой получил запретную силу", "angle": "power"},
        {"title": "Его предали, но он вернулся сильнее", "angle": "twist"},
        {"title": "Монстр оказался ближе, чем думали", "angle": "mystery"},
    ]
    description = "Описание видео.\n\nХэштеги: #манхва #пересказ"
    pinned = "Какой поступок героя удивил вас больше всего?"

    result = add_youtube_package_to_export(
        str(export_dir),
        titles=titles,
        description=description,
        pinned_comment=pinned,
        selected_title=titles[1],
        thumbnails=thumbnails,
    )

    assert result["copied_thumbnails"] == 3
    assert len(list((export_dir / "thumbnails").glob("*.jpg"))) == 3
    assert (export_dir / "script.txt").exists() is False  # supplied by silent video export
    assert (export_dir / "youtube_package.json").is_file()
    assert (export_dir / "title_options.txt").read_text(encoding="utf-8").splitlines() == [
        "1. Герой получил запретную силу",
        "2. Его предали, но он вернулся сильнее",
        "3. Монстр оказался ближе, чем думали",
    ]
    assert (export_dir / "description.txt").read_text(encoding="utf-8") == description + "\n"
    assert (export_dir / "pinned_comment.txt").read_text(encoding="utf-8") == pinned + "\n"

    package = json.loads((export_dir / "youtube_package.json").read_text(encoding="utf-8"))
    assert package["selected_title"] == titles[1]
    assert len(package["thumbnails"]) == 3
