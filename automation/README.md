# Secret Voicer automation — first integration step

This isolated Playwright module does not initialize AniFlow narration, TTS, or video-rendering pipelines.

## Install

From the repository root, in Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r automation\requirements.txt
~~~

The default browser mode uses the locally installed Google Chrome. If Chrome is not installed:

~~~powershell
python -m playwright install chromium
~~~

Then pass --browser chromium to the commands below.

## First run: inspect the interface

~~~powershell
python automation\secret_voicer.py inspect
~~~

A separate persistent browser profile is created at automation/.local/chrome-profile. Sign in manually in the opened browser window (including any Telegram confirmation), open the audio-generation screen, and press Enter in the terminal.

The script saves a screenshot and a JSON description of visible controls under automation/.local. The JSON excludes cookies, local storage, passwords, and current form values. Check the screenshot for personal details before sharing it. Never share the chrome-profile folder.

## Яндекс Браузер: работа через обычный профиль

Не запускай `python automation\\secret_voicer.py --browser yandex inspect`: этот режим специально отключён. Он открывает отдельный профиль, а Telegram-подтверждение у тебя возвращается в обычный Яндекс Браузер. Подключать обычный каталог `User Data` через Playwright тоже нельзя: Chromium блокирует remote debugging для стандартного профиля, а одновременное использование профиля вызывает блокировки файлов.

Для Яндекс Браузера используется расширение, которое работает с уже открытой вкладкой Secret Voicer в обычном профиле:

1. Установи расширение из `automation/extension` по инструкции в `automation/extension/README.md`.
2. Открой Secret Voicer и войди через Telegram.
3. Нажми значок расширения и выполни проверку страницы.
4. Передай полученный JSON для настройки точных элементов интерфейса.

Пока расширение находится на диагностическом этапе: оно только считывает описания видимых элементов, не управляет генерацией и не скачивает MP3. Не передавай никому папку профиля, cookies, пароль или коды Telegram.

## Configure selectors

After inspecting the logged-in screen, copy selectors.example.json to selectors.json and fill in the CSS selectors. Each selector must match exactly one element.

- script_input: text area or contenteditable script field.
- generate_button: the control that starts generation.
- download_button: the control that downloads completed audio.
- completion: optional selector that appears only after generation finishes. If omitted, the script waits for the download control.
- voice_select and voice_option: optional; only for a native HTML select. With a custom voice picker, choose the voice manually during the confirmation pause.

Do not guess selectors. Verify them against the current page diagnostics.

## Generate a test audio

Create a short UTF-8 file such as automation/test_script.txt and run:

~~~powershell
python automation\secret_voicer.py generate automation\test_script.txt --name first_test
~~~

The script inserts the text, pauses for a visual check of the voice/settings, clicks Generate, waits for completion, and saves the download under automation/outputs.

The public Secret Voicer page advertises support for up to 100,000 characters in one submission. This module also rejects input longer than 100,000 characters.

## Security

- Do not commit .local, outputs, or selectors.json.
- The browser uses a dedicated automation profile, not your everyday Chrome profile.
- Never put Telegram codes, passwords, cookies, or browser storage in source code or GitHub.
- This first version operates visible page controls only; it does not call undocumented/private service endpoints.
