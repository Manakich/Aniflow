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

## Use your already signed-in Yandex Browser profile

The Yandex Browser paths reported by the user are:

- Executable: `C:\\Program Files\\Yandex\\YandexBrowser\\Application\\browser.exe`
- Profile: `%LOCALAPPDATA%\\Yandex\\YandexBrowser\\User Data\\Default`

The User Data directory passed to Chromium is the parent folder (without `Default`). The script's `--browser yandex` mode attaches to Yandex over CDP at `127.0.0.1:9222`; it does not copy, export, or read cookies.

1. Save any work and fully exit every Yandex Browser window. Also exit it from the tray/background menu. Do not kill it while it is writing profile data.
2. In PowerShell, start Yandex with remote debugging enabled and the same existing profile:

~~~powershell
$yandexExe = 'C:\Program Files\Yandex\YandexBrowser\Application\browser.exe'
$userData = Join-Path $env:LOCALAPPDATA 'Yandex\YandexBrowser\User Data'
$arguments = '--remote-debugging-port=9222 --user-data-dir="' + $userData + '" --profile-directory=Default https://secretvoicer.com/app/'
Start-Process -FilePath $yandexExe -ArgumentList $arguments
~~~

3. Verify that the local debugging endpoint is available:

~~~powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version | Format-List Browser,webSocketDebuggerUrl
~~~

4. Attach Playwright to the existing logged-in Yandex profile:

~~~powershell
python automation\secret_voicer.py --browser yandex inspect
~~~

The script disconnects its Playwright client when finished; it does not need to copy browser cookies into the project. After inspection, close Yandex normally to stop the local debugging endpoint.

**Security:** the remote-debugging port gives local software control over the browser and access to signed-in tabs. Keep it bound to localhost (use the command above exactly; do not add a host `0.0.0.0`), do not share the CDP URL or browser profile, and fully exit the debug-enabled browser when automation is not being used. If the endpoint does not start, check the Yandex Browser policy named `RemoteDebuggingAllowed` or use the isolated Chromium profile route instead.

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
