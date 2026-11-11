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

## Yandex Browser automation profile

Yandex mode launches the installed Yandex Browser with a separate persistent profile under `automation/.local/yandex-profile`. It deliberately does not point Playwright at the ordinary `%LOCALAPPDATA%\\Yandex\\YandexBrowser\\User Data` directory.

Why: recent Chromium security changes block Playwright's remote-debugging automation against the default browser data directory. Playwright documents that the regular profile should not be passed to `launch_persistent_context`; use a distinct user-data directory instead. Never copy the ordinary browser profile or cookies into the repository.

Run:

~~~powershell
python automation\\secret_voicer.py --browser yandex inspect
~~~

On the first run the automation profile is empty and must be authenticated. The Secret Voicer login page offers Telegram, Google, and Yandex sign-in. Use an alternate provider only if it is already linked to the same Secret Voicer account/subscription. If the account is Telegram-only and Telegram's return always opens the everyday browser, stop: do not assume the new profile is authenticated. The next supported path is a small browser extension installed in the already signed-in Yandex profile that talks to a local Python bridge; this avoids remote-debugging the default profile.

The browser process must not already be using `automation/.local/yandex-profile` when the script starts. The automation profile contains its own session and must remain private. It is ignored by Git.

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
