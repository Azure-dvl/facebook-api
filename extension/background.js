const DEFAULT_API_URL = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(async () => {
  const { apiUrl } = await chrome.storage.local.get("apiUrl");
  if (!apiUrl) {
    await chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
  }
});

async function readFacebookCookies() {
  return chrome.cookies.getAll({ domain: ".facebook.com" });
}

async function exportSession() {
  const { apiUrl } = await chrome.storage.local.get("apiUrl");
  const base = apiUrl || DEFAULT_API_URL;
  const url = `${base.replace(/\/$/, "")}/auth/import-cookies`;

  const cookies = await readFacebookCookies();
  if (!cookies || cookies.length === 0) {
    return {
      ok: false,
      error:
        "No se encontraron cookies de Facebook. Abre primero facebook.com y logueate.",
    };
  }

  const payload = {
    cookies: cookies.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      expirationDate: c.expirationDate || c.expires || undefined,
      httpOnly: c.httpOnly,
      secure: c.secure,
      sameSite: c.sameSite || undefined,
    })),
    session_name: "extension",
  };

  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    return {
      ok: false,
      error: `No se pudo conectar con la API en ${base}. Revisa que este corriendo (uv run python main.py) y que la URL sea correcta. Detalle: ${err}`,
    };
  }

  let data = null;
  try {
    data = await resp.json();
  } catch (_) {
    data = null;
  }

  if (!resp.ok) {
    const detail =
      (data && data.detail) || `HTTP ${resp.status} ${resp.statusText}`;
    return {
      ok: false,
      error: detail,
    };
  }

  return { ok: true, data };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "EXPORT_SESSION") {
    exportSession().then(sendResponse);
    return true;
  }
  return false;
});
