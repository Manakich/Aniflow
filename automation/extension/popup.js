const runButton = document.getElementById("run");
const inspectButton = document.getElementById("inspect");
const copyButton = document.getElementById("copy");
const statusNode = document.getElementById("status");
const reportNode = document.getElementById("report");

function setStatus(message) {
  statusNode.textContent = message;
}

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url) throw new Error("Не удалось определить активную вкладку.");
    const pageUrl = new URL(tab.url);
    if (pageUrl.origin !== "https://secretvoicer.com") {
      throw new Error("Сначала открой https://secretvoicer.com/app/ и войди через Telegram.");
    }
    const runnerUrl = chrome.runtime.getURL("runner.html") + "?tabId=" + encodeURIComponent(tab.id);
    await chrome.tabs.create({ url: runnerUrl, active: true });
    setStatus("Открыл окно выполнения. Следи за его сообщениями.");
    window.close();
  } catch (error) {
    setStatus(error?.message || String(error));
    runButton.disabled = false;
  }
});

inspectButton.addEventListener("click", async () => {
  inspectButton.disabled = true;
  copyButton.disabled = true;
  reportNode.value = "";
  setStatus("Проверяю активную вкладку…");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url) throw new Error("Не удалось определить активную вкладку.");
    const pageUrl = new URL(tab.url);
    if (pageUrl.origin !== "https://secretvoicer.com") {
      throw new Error("Сначала открой https://secretvoicer.com/ и войди в аккаунт через Telegram.");
    }

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const selector = ["input", "textarea", "select", "button", "[role='button']", "[role='textbox']", "[contenteditable='true']", "a"].join(",");
        const isVisible = (element) => {
          const rect = element.getBoundingClientRect();
          const style = window.getComputedStyle(element);
          return (rect.width > 0 || rect.height > 0) && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
        };
        const elements = Array.from(document.querySelectorAll(selector)).filter(isVisible).map((element, index) => {
          const tag = element.tagName.toLowerCase();
          const type = element.getAttribute("type");
          const isTextEntry = tag === "textarea" ||
            (tag === "input" && !["button", "submit", "reset", "checkbox", "radio"].includes(type)) ||
            element.getAttribute("role") === "textbox" || element.getAttribute("contenteditable") === "true";
          return {
            index, tag, type, role: element.getAttribute("role"),
            text: isTextEntry ? "" : (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 140),
            aria_label: element.getAttribute("aria-label"),
            placeholder: element.getAttribute("placeholder"),
            title: element.getAttribute("title"),
            name: element.getAttribute("name"),
            id: element.id || null,
            data_testid: element.getAttribute("data-testid"),
            contenteditable: element.getAttribute("contenteditable"),
            disabled: Boolean(element.disabled)
          };
        });
        const resultLinks = Array.from(document.querySelectorAll("a.audio-download-btn")).map((link) => {
          const url = new URL(link.href, location.href);
          return {
            text: (link.innerText || link.textContent || "").trim().slice(0, 80),
            href_kind: url.origin === location.origin ? "same-origin" : "external",
            href_path: url.pathname,
            download_attribute: link.getAttribute("download")
          };
        });
        const media = Array.from(document.querySelectorAll("audio,video")).map((item) => ({
          tag: item.tagName.toLowerCase(),
          ready_state: item.readyState,
          duration_seconds: Number.isFinite(item.duration) ? Math.round(item.duration * 100) / 100 : null,
          paused: item.paused
        }));
        return {
          url: location.href, title: document.title, captured_at: new Date().toISOString(),
          interactive_elements: elements, result_links: resultLinks, media,
          privacy_note: "No cookies, passwords, local storage, or live input values were read."
        };
      }
    });
    const report = results?.[0]?.result;
    if (!report) throw new Error("Браузер не вернул диагностику страницы.");
    reportNode.value = JSON.stringify(report, null, 2);
    copyButton.disabled = false;
    setStatus("Готово. Просмотри JSON перед копированием.");
  } catch (error) {
    setStatus(error?.message || String(error));
  } finally {
    inspectButton.disabled = false;
  }
});

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(reportNode.value);
    setStatus("JSON скопирован. Проверь его перед отправкой.");
  } catch {
    reportNode.focus();
    reportNode.select();
    setStatus("Автокопирование недоступно: выдели текст и нажми Ctrl+C.");
  }
});
