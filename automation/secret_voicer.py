from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

APP_URL = "https://secretvoicer.com/app/"
BASE_DIR = Path(__file__).resolve().parent
LOCAL_DIR = BASE_DIR / ".local"
PROFILE_DIR = LOCAL_DIR / "chrome-profile"
DOWNLOAD_DIR = BASE_DIR / "outputs"
CONFIG_PATH = BASE_DIR / "selectors.json"


def safe_name(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", value.strip())
    value = value.strip("._-")
    return value[:80] or "secretvoicer_audio"


def launch_context(playwright: Any, browser_name: str):
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "accept_downloads": True,
        "downloads_path": str(DOWNLOAD_DIR),
        "no_viewport": True,
    }
    if browser_name == "chrome":
        kwargs["channel"] = "chrome"
    try:
        return playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as exc:
        if browser_name == "chrome":
            raise RuntimeError(
                "Не удалось запустить установленный Chrome. Закрой окна "
                "автоматизационного профиля. При отсутствии Chrome повтори "
                "с --browser chromium после установки браузера Playwright. "
                f"Исходная ошибка: {exc}"
            ) from exc
        raise


def connect_or_launch_context(playwright: Any, browser_name: str):
    """Return (context, cleanup); Yandex connects over localhost CDP."""
    if browser_name == "yandex":
        endpoint = "http://127.0.0.1:9222"
        try:
            browser = playwright.chromium.connect_over_cdp(endpoint, timeout=10_000)
        except Exception as exc:
            raise RuntimeError(
                "Не удалось подключиться к Яндекс Браузеру по CDP на 127.0.0.1:9222. "
                "Сначала полностью закрой Яндекс Браузер, запусти его с "
                "--remote-debugging-port=9222 по инструкции automation/README.md "
                f"и повтори команду. Исходная ошибка: {exc}"
            ) from exc
        contexts = browser.contexts
        if not contexts:
            browser.close()
            raise RuntimeError("Playwright не видит контекст Яндекс Браузера.")
        return contexts[0], browser.close
    context = launch_context(playwright, browser_name)
    return context, context.close

def get_page(context: Any):
    for page in reversed(context.pages):
        if "secretvoicer.com" in page.url:
            return page
    return context.new_page()


def inspect_page(page: Any) -> list[dict[str, Any]]:
    selector = (
        "input, textarea, select, button, [role='button'], "
        "[role='textbox'], [contenteditable='true'], a"
    )
    return page.locator(selector).evaluate_all(
        """elements => elements.map((el, index) => {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          const visible = !!(rect.width || rect.height) &&
            style.display !== 'none' && style.visibility !== 'hidden';
          const text = (el.innerText || el.textContent || '')
            .replace(/\\s+/g, ' ').trim().slice(0, 160);
          return {
            index,
            tag: el.tagName.toLowerCase(),
            type: el.getAttribute('type'),
            role: el.getAttribute('role'),
            text,
            aria_label: el.getAttribute('aria-label'),
            placeholder: el.getAttribute('placeholder'),
            title: el.getAttribute('title'),
            name: el.getAttribute('name'),
            id: el.id || null,
            data_testid: el.getAttribute('data-testid'),
            contenteditable: el.getAttribute('contenteditable'),
            disabled: !!el.disabled,
            visible,
            outer_html: el.outerHTML.slice(0, 500)
          };
        }).filter(item => item.visible)"""
    )


def write_diagnostics(page: Any) -> tuple[Path, Path]:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshot_path = LOCAL_DIR / f"secretvoicer-{stamp}.png"
    json_path = LOCAL_DIR / f"secretvoicer-{stamp}.json"
    details = {
        "url": page.url,
        "title": page.title(),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "interactive_elements": inspect_page(page),
        "note": "No cookies, local storage, passwords, input values, or browser profile contents are included."
    }
    json_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    page.screenshot(path=str(screenshot_path), full_page=True)
    return json_path, screenshot_path


def open_app(page: Any, timeout_ms: int) -> None:
    page.set_default_timeout(timeout_ms)
    page.goto(APP_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(3500)


def run_inspect(browser_name: str, timeout_ms: int) -> int:
    with sync_playwright() as playwright:
        context, cleanup = connect_or_launch_context(playwright, browser_name)
        page = get_page(context)
        try:
            open_app(page, timeout_ms)
            if browser_name == "yandex":
                print("\nPlaywright подключён к твоему Яндекс Браузеру.")
                print("Используется уже сохранённая сессия профиля Default.")
            else:
                print("\nSecret Voicer открыт в отдельном профиле Chromium.")
                print("Войди в аккаунт вручную именно в этом окне.")
            input(
                "Когда в Chromium откроется рабочая страница /app/ (не /login/), "
                "нажми Enter здесь... "
            )
            page.wait_for_timeout(1500)
            authenticated = "/login/" not in page.url and "/login?" not in page.url
            json_path, screenshot_path = write_diagnostics(page)
            print("\nДиагностика сохранена:")
            print(f"  JSON: {json_path}")
            print(f"  Скриншот: {screenshot_path}")
            if authenticated:
                print("Страница уже не находится на маршруте входа.")
            else:
                print(
                    "ВНИМАНИЕ: Chromium всё ещё показывает страницу входа. "
                    "Сессия в этом профиле пока НЕ подтверждена. "
                    "Не переходи к генерации — заверши Telegram-вход именно "
                    "в Chromium и повтори inspect."
                )
            print("Проверь скриншот на личные данные перед отправкой.")
        finally:
            cleanup()
    return 0


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Не найден файл настроек {path}. Скопируй selectors.example.json "
            "в selectors.json и заполни CSS-селекторы после команды inspect."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("selectors"), dict):
        raise ValueError("В selectors.json ожидается объект с полем selectors.")
    return data


def unique_locator(page: Any, selector: str, label: str):
    locator = page.locator(selector)
    count = locator.count()
    if count != 1:
        raise RuntimeError(
            f"Для элемента «{label}» селектор {selector!r} нашёл {count} "
            "элементов. Нужен точный CSS-селектор, совпадающий ровно с одним."
        )
    return locator


def run_generate(
    browser_name: str,
    timeout_ms: int,
    script_path: Path,
    output_name: str,
    config_path: Path,
) -> int:
    if not script_path.exists():
        raise FileNotFoundError(f"Файл сценария не найден: {script_path}")
    script_text = script_path.read_text(encoding="utf-8-sig").strip()
    if not script_text:
        raise ValueError("Файл сценария пуст.")
    if len(script_text) > 100_000:
        raise ValueError(
            f"В сценарии {len(script_text):,} символов. Публичная страница "
            "Secret Voicer заявляет поддержку до 100 000 символов за раз."
        )

    config = load_config(config_path)
    selectors = config["selectors"]
    input_selector = selectors.get("script_input")
    generate_selector = selectors.get("generate_button")
    download_selector = selectors.get("download_button")
    completion_selector = selectors.get("completion")
    if not all([input_selector, generate_selector, download_selector]):
        raise ValueError(
            "В selectors.json должны быть заданы script_input, "
            "generate_button и download_button."
        )

    with sync_playwright() as playwright:
        context, cleanup = connect_or_launch_context(playwright, browser_name)
        page = get_page(context)
        try:
            open_app(page, timeout_ms)
            script_box = unique_locator(page, input_selector, "поле сценария")
            script_box.fill(script_text)

            voice_selector = selectors.get("voice_select")
            voice_option = selectors.get("voice_option")
            if voice_selector and voice_option:
                voice_box = unique_locator(page, voice_selector, "выбор голоса")
                voice_box.select_option(label=voice_option)

            print("\nСценарий вставлен. Проверь выбранный голос и настройки.")
            input("Когда всё готово, нажми Enter — начнётся генерация... ")

            unique_locator(page, generate_selector, "кнопка генерации").click()
            wait_selector = completion_selector or download_selector
            wait_label = "завершение генерации" if completion_selector else "кнопка скачивания"
            print(f"Ожидаю {wait_label}...")
            unique_locator(page, wait_selector, wait_label).wait_for(
                state="visible", timeout=timeout_ms
            )

            download_button = unique_locator(page, download_selector, "кнопка скачивания")
            with page.expect_download(timeout=timeout_ms) as download_info:
                download_button.click()
            download = download_info.value

            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            base = safe_name(output_name)
            suffix = Path(download.suggested_filename).suffix or ".mp3"
            if suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
                suffix = ".mp3"
            output_path = DOWNLOAD_DIR / f"{base}{suffix}"
            download.save_as(str(output_path))
            failure = download.failure()
            if failure:
                raise RuntimeError(f"Ошибка загрузки файла: {failure}")
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("Скачанный аудиофайл отсутствует или пуст.")
            print(f"\nАудио сохранено: {output_path}")
            print(f"Размер: {output_path.stat().st_size:,} байт")
            return 0
        except Exception:
            try:
                json_path, screenshot_path = write_diagnostics(page)
                print(f"Диагностика: {json_path}")
                print(f"Скриншот: {screenshot_path}")
            except Exception as diagnostic_error:
                print(f"Не удалось сохранить диагностику: {diagnostic_error}")
            raise
        finally:
            cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Локальная автоматизация Secret Voicer через Playwright."
    )
    parser.add_argument(
        "--browser", choices=("chrome", "chromium", "yandex"), default="chrome",
        help="Chrome/Chromium с отдельным профилем или Яндекс Браузер через CDP."
    )
    parser.add_argument(
        "--timeout", type=int, default=600_000,
        help="Таймаут операций в миллисекундах (по умолчанию 10 минут)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect", help="Открыть сайт и сохранить диагностику.")
    generate = subparsers.add_parser("generate", help="Сгенерировать и скачать MP3.")
    generate.add_argument("script", type=Path, help="Путь к TXT/MD со сценарием.")
    generate.add_argument("--name", default="test_voiceover", help="Имя итогового аудио.")
    generate.add_argument("--config", type=Path, default=CONFIG_PATH, help="Путь к selectors.json.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "inspect":
            return run_inspect(args.browser, args.timeout)
        if args.command == "generate":
            return run_generate(
                args.browser, args.timeout, args.script, args.name, args.config
            )
    except (FileNotFoundError, ValueError, RuntimeError, PlaywrightTimeoutError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nОперация отменена.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
