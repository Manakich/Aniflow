from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
EXTENSION_ORIGIN = "chrome-extension://binchgjcpbadmbeaaioniglmgdiimdjf"
DOWNLOAD_SUBDIR = "MangaRecapAutomation"
MAX_SCRIPT_CHARS = 100_000


def safe_name(value: str) -> str:
    import re

    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", value.strip())
    value = value.strip("._-")
    return value[:80] or "secretvoicer_audio"


def run_bridge(script_path: Path, output_name: str, port: int, timeout_seconds: int) -> int:
    if not script_path.exists():
        raise FileNotFoundError(f"Файл сценария не найден: {script_path}")
    script_text = script_path.read_text(encoding="utf-8-sig").strip()
    if not script_text:
        raise ValueError("Файл сценария пуст.")
    if len(script_text) > MAX_SCRIPT_CHARS:
        raise ValueError(
            f"В сценарии {len(script_text):,} символов. Лимит этой интеграции — "
            f"{MAX_SCRIPT_CHARS:,} символов."
        )

    job_id = uuid.uuid4().hex
    state: dict[str, Any] = {
        "job_id": job_id,
        "text": script_text,
        "output_name": safe_name(output_name),
        "claimed": False,
        "event": threading.Event(),
        "result": None,
        "error": None,
        "lock": threading.Lock(),
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "MangaRecapBridge/0.1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _origin_allowed(self) -> bool:
            return self.headers.get("Origin") == EXTENSION_ORIGIN

        def _cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", EXTENSION_ORIGIN)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Некорректный Content-Length") from exc
            if length < 1 or length > 128_000:
                raise ValueError("Недопустимый размер запроса")
            raw = self.rfile.read(length)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Тело запроса должно содержать корректный JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("Ожидался JSON-объект")
            return value

        def do_OPTIONS(self) -> None:
            if not self._origin_allowed():
                self.send_error(403, "Extension origin is not allowed")
                return
            self.send_response(204)
            self._cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            if not self._origin_allowed():
                self.send_error(403, "Extension origin is not allowed")
                return
            path = urlparse(self.path).path
            if path == "/api/health":
                self._json(200, {"ok": True, "pending": not state["claimed"], "job_id": job_id})
                return
            if path == "/api/next":
                with state["lock"]:
                    if state["claimed"]:
                        self._json(409, {"ok": False, "error": "Это задание уже было получено расширением."})
                        return
                    state["claimed"] = True
                self._json(200, {
                    "ok": True,
                    "job_id": state["job_id"],
                    "text": state["text"],
                    "output_name": state["output_name"],
                })
                return
            self._json(404, {"ok": False, "error": "Неизвестный endpoint"})

        def do_POST(self) -> None:
            if not self._origin_allowed():
                self.send_error(403, "Extension origin is not allowed")
                return
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if payload.get("job_id") != job_id:
                    raise ValueError("Идентификатор задания не совпадает")

                if path == "/api/error":
                    message = str(payload.get("error") or "Неизвестная ошибка")[:1500]
                    state["error"] = message
                    state["event"].set()
                    self._json(200, {"ok": True})
                    return

                if path != "/api/complete":
                    self._json(404, {"ok": False, "error": "Неизвестный endpoint"})
                    return

                raw_path = payload.get("download_path")
                if not isinstance(raw_path, str) or not raw_path.strip():
                    raise ValueError("Расширение не передало путь к скачанному MP3")
                source = Path(raw_path).expanduser().resolve()
                if source.name.lower() != f"{job_id}.mp3".lower() or source.parent.name != DOWNLOAD_SUBDIR:
                    raise ValueError(
                        "Файл не совпадает с ожидаемой загрузкой. Проверь папку загрузок браузера."
                    )
                if not source.is_file() or source.stat().st_size <= 0:
                    raise ValueError("Скачанный MP3 не найден или имеет нулевой размер")

                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                target = OUTPUT_DIR / f"{state['output_name']}.mp3"
                if target.exists():
                    target = OUTPUT_DIR / f"{state['output_name']}_{job_id[:8]}.mp3"
                shutil.copy2(source, target)
                state["result"] = {
                    "output_path": str(target),
                    "download_path": str(source),
                    "size_bytes": target.stat().st_size,
                }
                state["event"].set()
                self._json(200, {"ok": True, "saved": str(target)})
            except (ValueError, OSError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    worker = threading.Thread(target=httpd.serve_forever, name="secret-voicer-bridge", daemon=True)
    worker.start()

    print("\nЛокальный мост Manga Recap запущен.")
    print(f"Сценарий: {script_path}")
    print(f"Символов: {len(script_text):,}")
    print(f"Задание: {job_id}")
    print("Теперь открой вкладку Secret Voicer, нажми значок расширения и выбери «Запустить задание из Python».")
    print("Не закрывай вкладку Secret Voicer во время генерации.")
    print(f"Ожидаю результат (до {timeout_seconds // 60} мин.)...\n")

    try:
        finished = state["event"].wait(timeout=timeout_seconds)
        if not finished:
            print("ОШИБКА: истекло время ожидания. Проверь браузер и расширение.", file=sys.stderr)
            return 1
        if state["error"]:
            print(f"ОШИБКА в браузере: {state['error']}", file=sys.stderr)
            return 1
        result = state["result"]
        if not result:
            print("ОШИБКА: браузер завершил задачу без файла.", file=sys.stderr)
            return 1
        print("Готово! MP3 сохранён в проект:")
        print(f"  {result['output_path']}")
        print(f"Размер: {result['size_bytes']:,} байт")
        print(f"Исходная загрузка браузера: {result['download_path']}")
        return 0
    except KeyboardInterrupt:
        print("\nОперация отменена.", file=sys.stderr)
        return 130
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Локальный мост между Python и расширением Secret Voicer."
    )
    parser.add_argument("script", type=Path, help="UTF-8 TXT/MD файл со сценарием")
    parser.add_argument("--name", default="secretvoicer_audio", help="Имя MP3 в automation/outputs")
    parser.add_argument("--port", type=int, default=8765, help="Локальный порт (по умолчанию 8765)")
    parser.add_argument("--timeout", type=int, default=900, help="Ожидание расширения в секундах (по умолчанию 900)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        print("ОШИБКА: порт должен быть в диапазоне 1–65535", file=sys.stderr)
        return 2
    if args.timeout < 60:
        print("ОШИБКА: таймаут должен быть не меньше 60 секунд", file=sys.stderr)
        return 2
    try:
        return run_bridge(args.script, args.name, args.port, args.timeout)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
