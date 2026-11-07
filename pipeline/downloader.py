"""
Manhwa Chapter Image Downloader
Supports: Direct folder loading, URL-based downloading
"""
import os
import re
import shutil
import requests
from PIL import Image
from urllib.parse import urlparse


def load_from_folder(folder_path: str, project_dir: str) -> list[str]:
    """
    Load manhwa chapter images from a local folder.
    Copies images to the project directory and returns sorted list of paths.
    """
    images_dir = os.path.join(project_dir, "raw_pages")
    os.makedirs(images_dir, exist_ok=True)

    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    image_files = []

    for f in sorted(os.listdir(folder_path)):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_extensions:
            src = os.path.join(folder_path, f)
            dst = os.path.join(images_dir, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            image_files.append(dst)

    # Sort naturally (page1, page2, ..., page10, page11)
    image_files.sort(key=_natural_sort_key)
    return image_files


def download_from_urls(urls: list[str], project_dir: str, headers: dict = None) -> list[str]:
    """
    Download manhwa chapter images from a list of URLs.
    Returns sorted list of downloaded file paths.
    """
    images_dir = os.path.join(project_dir, "raw_pages")
    os.makedirs(images_dir, exist_ok=True)

    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': _get_referer(urls[0]) if urls else '',
        }

    downloaded = []
    for i, url in enumerate(urls):
        ext = _get_extension(url)
        filename = f"page_{i+1:04d}{ext}"
        filepath = os.path.join(images_dir, filename)

        if os.path.exists(filepath):
            downloaded.append(filepath)
            continue

        try:
            resp = requests.get(url, headers=headers, timeout=30, stream=True)
            resp.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded.append(filepath)
        except Exception as e:
            print(f"[Downloader] Failed to download {url}: {e}")

    downloaded.sort(key=_natural_sort_key)
    return downloaded





def load_from_archive_file(archive_path: str, output_dir: str) -> list[str]:
    """Import one image, ZIP/CBZ archive or PDF into numbered page images.

    ZIP entries are never extracted using their original paths. Only image
    bytes are copied to generated page filenames, which prevents ZIP path
    traversal and avoids collisions from nested folders.
    """
    import io
    import zipfile
    from pathlib import Path

    archive_path = os.path.abspath(os.path.expanduser(archive_path))
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Файл не найден: {archive_path}")

    os.makedirs(output_dir, exist_ok=True)
    extract_dir = os.path.join(output_dir, "archive_pages")
    os.makedirs(extract_dir, exist_ok=True)

    # Clear only files created by this importer; keep the chapter state and other assets.
    for name in os.listdir(extract_dir):
        path = os.path.join(extract_dir, name)
        if os.path.isfile(path) and name.startswith("page_"):
            os.remove(path)

    ext = Path(archive_path).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF, optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "Для импорта PDF установите PyMuPDF: pip install PyMuPDF"
            ) from exc

        document = fitz.open(archive_path)
        try:
            if document.page_count > 2000:
                raise ValueError("PDF содержит более 2000 страниц; разделите файл на части.")
            output = []
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                target = os.path.join(extract_dir, f"page_{index:05d}.jpg")
                pixmap.save(target, jpg_quality=92)
                output.append(target)
            if not output:
                raise ValueError("PDF не содержит страниц.")
            return output
        finally:
            document.close()

    if ext in image_exts:
        from PIL import Image
        target = os.path.join(extract_dir, f"page_00001{ext}")
        shutil.copy2(archive_path, target)
        with Image.open(target) as image:
            image.verify()
        return [target]

    if ext not in {".zip", ".cbz"}:
        raise ValueError("Поддерживаются ZIP, CBZ, PDF и отдельные изображения.")

    from PIL import Image

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            image_entries = [
                info for info in archive.infolist()
                if not info.is_dir()
                and os.path.splitext(info.filename)[1].lower() in image_exts
            ]
            image_entries.sort(key=lambda info: _natural_sort_key(info.filename))
            if not image_entries:
                raise ValueError("В архиве не найдены страницы JPG/PNG/WEBP/BMP/GIF.")
            if len(image_entries) > 2000:
                raise ValueError("В архиве более 2000 изображений; разделите его на части.")

            total_uncompressed = sum(info.file_size for info in image_entries)
            if total_uncompressed > 1024 * 1024 * 1024:
                raise ValueError("Суммарный размер изображений в архиве превышает 1 ГБ.")

            output = []
            for index, info in enumerate(image_entries, start=1):
                if info.file_size > 100 * 1024 * 1024:
                    continue
                data = archive.read(info)
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        image.verify()
                except Exception:
                    print(f"[Downloader] Skipping invalid archive image: {info.filename}")
                    continue

                suffix = os.path.splitext(info.filename)[1].lower()
                target = os.path.join(extract_dir, f"page_{index:05d}{suffix}")
                with open(target, "wb") as file:
                    file.write(data)
                output.append(target)

            if not output:
                raise ValueError("В архиве нет читаемых изображений.")
            return output
    except zipfile.BadZipFile as exc:
        raise ValueError("Файл не является корректным ZIP/CBZ-архивом.") from exc
\n\ndef validate_images(image_paths: list[str]) -> list[str]:
    """Validate that all image files are readable and return valid ones."""
    valid = []
    for path in image_paths:
        try:
            with Image.open(path) as img:
                img.verify()
            valid.append(path)
        except Exception as e:
            print(f"[Downloader] Invalid image {path}: {e}")
    return valid


def _natural_sort_key(s):
    """Sort strings with embedded numbers naturally."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]


def _get_extension(url: str) -> str:
    """Extract file extension from URL."""
    parsed = urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}:
        return ext
    return '.jpg'  # default


def _get_referer(url: str) -> str:
    """Extract base domain for referer header."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"
