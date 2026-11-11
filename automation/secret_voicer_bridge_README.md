# Secret Voicer local bridge

Команда:

```powershell
python automation\\secret_voicer_bridge.py automation\\test_script.txt --name first_auto_test
```

Скрипт читает UTF-8 TXT/MD, запускает HTTP-мост только на `127.0.0.1:8765`, ждёт задания от расширения и копирует скачанный MP3 из `Downloads\\MangaRecapAutomation` в `automation\\outputs`.

По умолчанию ожидание — 15 минут. Можно изменить через `--timeout 1200`. Ограничение сценария — 100 000 символов.

Мост закрывается после завершения задания. Для каждого нового файла запускай новую команду.
