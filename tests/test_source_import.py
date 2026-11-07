import zipfile
from pathlib import Path

from PIL import Image

from pipeline.downloader import load_from_archive_file


def _write_image_zip(archive_path, image_entries):
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, color in image_entries:
            image_path = archive_path.parent / (name.replace("/", "_") + ".tmp.png")
            Image.new("RGB", (32, 32), color).save(image_path, format="PNG")
            archive.write(image_path, arcname=name)
            image_path.unlink()


def test_cbz_import_sorts_pages_naturally_and_never_extracts_original_paths(tmp_path):
    archive_path = tmp_path / "chapter.cbz"
    _write_image_zip(archive_path, [
        ("nested/page10.png", (0, 0, 255)),
        ("nested/page2.png", (255, 0, 0)),
        ("../../escape.jpg", (0, 255, 0)),
    ])

    output = load_from_archive_file(str(archive_path), str(tmp_path / "chapter"))

    assert len(output) == 3
    assert [Path(path).name for path in output] == [
        "page_00001.jpg", "page_00002.png", "page_00003.png"
    ]
    assert all(Path(path).parent.name == "archive_pages" for path in output)
    assert not (tmp_path / "escape.jpg").exists()
    with Image.open(output[0]) as first:
        assert first.getpixel((0, 0)) == (0, 255, 0)
    with Image.open(output[1]) as second:
        assert second.getpixel((0, 0)) == (255, 0, 0)


def test_single_image_file_import_creates_numbered_page(tmp_path):
    source = tmp_path / "page.png"
    Image.new("RGB", (24, 32), (50, 60, 70)).save(source)
    result = load_from_archive_file(str(source), str(tmp_path / "chapter"))
    assert len(result) == 1
    assert Path(result[0]).name == "page_00001.png"
    with Image.open(result[0]) as image:
        assert image.size == (24, 32)


def test_unsupported_archive_extension_fails_clearly(tmp_path):
    source = tmp_path / "chapter.rar"
    source.write_bytes(b"not supported")
    try:
        load_from_archive_file(str(source), str(tmp_path / "chapter"))
    except ValueError as exc:
        assert "ZIP" in str(exc)
    else:
        raise AssertionError("Expected unsupported archive type to fail")
