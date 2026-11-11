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

## Use the existing signed-in Yandex Browser profile

The user's existing Yandex Browser profile is stored at:

- Profile Path: `%LOCALAPPDATA%\\Yandex\\YandexBrowser\\User Data\\Default`
- User Data directory: `%LOCALAPPDATA%\\Yandex\\YandexBrowser\\User Data`
- Executable: `C:/Program Files/Yandex/YandexBrowser/Application/browser.exe`

The `--browser yandex` mode launches the installed Yandex Browser through Playwright using the existing `User Data` folder and `--profile-directory=Default`. It does not copy cookies or create a separate profile. This is intended to reuse the already authenticated Secret Voicer session.

**Before every run, fully exit all Yandex Browser windows and background processes.** Chromium-based browsers do not allow two processes to use the same User Data directory concurrently. Do not launch the script while your regular Yandex Browser is open.

Run:

~~~powershell
python automation\\secret_voicer.py --browser yandex inspect
~~~

The browser window launched by Playwright should show the existing session. The Telegram login link may still invoke the desktop Telegram app and return to the system-default Yandex process; because both use the same `User Data` folder, the returned session should be the one the automation uses. If it still redirects to login, stop and report the URL and screenshot; do not copy cookies or browser profile files manually.

Playwright documents `launch_persistent_context` as using the supplied User Data directory for cookies and local storage, and warns that only one browser instance can use it at a time. The `executable_path` option runs the installed Yandex build rather than Playwright's bundled Chromium; compatibility with vendor builds is not guaranteed.

Keep the profile directory private. It contains signed-in sessions and other personal browser data. Do not upload it or send it to anyone.

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
