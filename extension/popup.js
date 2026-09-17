const apiUrlInput = document.getElementById("apiUrl");
const exportBtn = document.getElementById("exportBtn");
const statusEl = document.getElementById("status");

function setStatus(text, kind) {
  statusEl.className = `status ${kind || "info"}`;
  statusEl.textContent = text;
}

async function init() {
  const { apiUrl } = await browser.storage.local.get("apiUrl");
  if (apiUrl) apiUrlInput.value = apiUrl;
}

apiUrlInput.addEventListener("change", async () => {
  await browser.storage.local.set({ apiUrl: apiUrlInput.value.trim() });
});

exportBtn.addEventListener("click", async () => {
  exportBtn.disabled = true;
  setStatus("Exportando sesión...", "info");
  try {
    const response = await browser.runtime.sendMessage({ type: "EXPORT_SESSION" });
    if (response && response.ok) {
      setStatus(
        `Sesión exportada correctamente. Session ID: ${response.data.session_id}`,
        "ok"
      );
    } else {
      setStatus((response && response.error) || "Error desconocido", "err");
    }
  } catch (err) {
    setStatus(String(err), "err");
  } finally {
    exportBtn.disabled = false;
  }
});

init();