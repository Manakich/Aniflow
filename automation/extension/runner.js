const BRIDGE = "http://127.0.0.1:8765";
const statusNode = document.getElementById("status");
const detailsNode = document.getElementById("details");
const retryButton = document.getElementById("retry");

function status(message) {
  statusNode.textContent = message;
}

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function bridgeJson(path, options = {}) {
  const response = await fetch(BRIDGE + path, {
    cache: "no-store",
    ...options,
    headers: { ...(options.headers || {}), ...(options.body ? { "Content-Type": "application/json" } : {}) }
  });
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.error || "Локальный мост ответил HTTP " + response.status);
  return payload;
}

function executePageJob(tabId, job) {
  return chrome.scripting.executeScript({
    target: { tabId },
    args: [job],
    func: async (task) => {
      const input = document.querySelector("#text-input");
      const submit = document.querySelector("#submit-btn");
      if (!(input instanceof HTMLTextAreaElement)) {
        throw new Error("Не найдено поле сценария #text-input.");
      }
      if (!(submit instanceof HTMLButtonElement)) {
        throw new Error("Не найдена кнопка озвучки #submit-btn.");
      }

      const baseline = new Set(
        Array.from(document.querySelectorAll("a.audio-download-btn"))
          .map((link) => {
            try { return new URL(link.href, location.href).pathname; } catch { return ""; }
          })
          .filter(Boolean)
      );

      const valueSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      if (valueSetter) valueSetter.call(input, task.text);
      else input.value = task.text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));

      if (input.value !== task.text) {
        throw new Error("Не удалось вставить сценарий в поле Secret Voicer.");
      }
      if (submit.disabled) {
        throw new Error("Кнопка «Озвучить» сейчас недоступна. Проверь страницу и лимиты сервиса.");
      }

      submit.click();
      const startedAt = Date.now();
      const timeoutMs = 12 * 60 * 1000;

      while (Date.now() - startedAt < timeoutMs) {
        const candidates = Array.from(document.querySelectorAll("a.audio-download-btn"))
          .map((link) => {
            try {
              const url = new URL(link.href, location.href);
              return { link, url };
            } catch {
              return null;
            }
          })
          .filter((item) => item &&
            item.url.origin === location.origin &&
            item.url.pathname.startsWith("/media/audio_output/") &&
            item.url.pathname.toLowerCase().endsWith(".mp3") &&
            !baseline.has(item.url.pathname));

        const unique = new Map();
        for (const item of candidates) {
          if (!unique.has(item.url.pathname)) unique.set(item.url.pathname, item);
        }

        if (unique.size > 0) {
          const fresh = unique.values().next().value;
          await new Promise((resolve) => setTimeout(resolve, 1200));
          return {
            ok: true,
            download_url: fresh.url.href,
            href_path: fresh.url.pathname,
            filename: task.job_id + ".mp3"
          };
        }

        await new Promise((resolve) => setTimeout(resolve, 1000));
      }

      throw new Error("За 12 минут не появилась новая ссылка MP3. Возможно, генерация не завершилась.");
    }
  });
}

async function start() {
  retryButton.style.display = "none";
  let job = null;
  try {
    status("Проверяю подключение к Python на этом компьютере…");
    const health = await bridgeJson("/api/health");
    if (!health.pending) throw new Error("Задание уже получено расширением. Перезапусти Python-команду для нового задания.");

    const tabIdParam = new URLSearchParams(location.search).get("tabId");
    const tabId = Number(tabIdParam);
    if (!Number.isInteger(tabId) || tabId <= 0) throw new Error("Не удалось определить вкладку Secret Voicer.");
    const tab = await chrome.tabs.get(tabId);
    if (!tab.url || new URL(tab.url).origin !== "https://secretvoicer.com") {
      throw new Error("Вкладка Secret Voicer закрыта или находится на другом сайте. Открой сайт и запусти задание снова.");
    }

    job = await bridgeJson("/api/next");
    status("Получил сценарий из Python (" + job.text.length.toLocaleString("ru-RU") + " символов). Запускаю озвучку…");
    const injected = await executePageJob(tabId, job);
    const result = injected?.[0]?.result;
    if (!result?.ok || !result.download_url) throw new Error("Secret Voicer не вернул новую ссылку на MP3.");

    const audioUrl = new URL(result.download_url);
    if (audioUrl.origin !== "https://secretvoicer.com" || !audioUrl.pathname.startsWith("/media/audio_output/")) {
      throw new Error("Ссылка скачивания не прошла проверку безопасности.");
    }

    status("Озвучка готова. Скачиваю MP3 через браузер…");
    const downloadId = await new Promise((resolve, reject) => {
      chrome.downloads.download({
        url: audioUrl.href,
        filename: "MangaRecapAutomation/" + job.job_id + ".mp3",
        saveAs: false,
        conflictAction: "uniquify"
      }, (id) => {
        const error = chrome.runtime.lastError;
        if (error) reject(new Error(error.message));
        else resolve(id);
      });
    });

    let downloadItem = null;
    const downloadTimeout = Date.now() + 5 * 60 * 1000;
    while (Date.now() < downloadTimeout) {
      const items = await new Promise((resolve, reject) => {
        chrome.downloads.search({ id: downloadId }, (found) => {
          const error = chrome.runtime.lastError;
          if (error) reject(new Error(error.message));
          else resolve(found);
        });
      });
      downloadItem = items?.[0];
      if (downloadItem?.state === "complete") break;
      if (downloadItem?.state === "interrupted") {
        throw new Error("Браузер прервал скачивание: " + (downloadItem.error || "неизвестная причина"));
      }
      await pause(700);
    }

    if (!downloadItem || downloadItem.state !== "complete" || !downloadItem.filename) {
      throw new Error("Браузер не завершил скачивание MP3 за 5 минут.");
    }

    status("MP3 скачан. Передаю локальному Python-проекту…");
    const completion = await bridgeJson("/api/complete", {
      method: "POST",
      body: JSON.stringify({ job_id: job.job_id, download_path: downloadItem.filename })
    });
    status("Готово! MP3 сохранён в automation/outputs.");
    detailsNode.textContent = completion.saved || "Файл передан в Python-проект.";
  } catch (error) {
    const message = error?.message || String(error);
    status("Ошибка: " + message);
    detailsNode.textContent = "Исправь указанную проблему и запусти задание повторно.";
    retryButton.style.display = "inline-block";
    if (job?.job_id) {
      try {
        await bridgeJson("/api/error", {
          method: "POST",
          body: JSON.stringify({ job_id: job.job_id, error: message })
        });
      } catch {}
    }
  }
}

retryButton.addEventListener("click", start);
start();
