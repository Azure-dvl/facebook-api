import httpx
from facebook_api.config import settings

BASE_URL = settings.PUBLIC_BASE_URL


def check_api_ready() -> None:
    try:
        resp = httpx.get(f"{BASE_URL}/", timeout=5)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"No se puede conectar con la API en {BASE_URL}. "
            f"Levantala con: uv run python main.py. Error: {e}"
        )


def get_active_session_id() -> str:
    resp = httpx.get(f"{BASE_URL}/auth/sessions", timeout=10)
    resp.raise_for_status()
    sessions = resp.json().get("sessions", [])
    active = [s for s in sessions if s.get("is_active")]
    if not active:
        raise RuntimeError(
            "No hay sesiones activas. Autenticate primero:\n"
            "  1. Arranca la API: uv run python main.py\n"
            "  2. Abre https://www.facebook.com y logueate con tu cuenta.\n"
            "  3. Pulsa el icono de la extension de navegador (carpeta extension/) "
            "y 'Exportar sesion'."
        )
    return active[0]["id"]


def publish_test_post(session_id: str) -> dict:
    body = {
        "session_id": session_id,
        "target": "profile",
        "text": "Prueba",
    }
    resp = httpx.post(f"{BASE_URL}/posts/create", json=body, timeout=180)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        detail = resp.text if resp.headers.get("content-type", "").startswith("text") else ""
        if not detail:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
        raise RuntimeError(
            f"La API respondio {resp.status_code}: {detail or resp.text}"
        )
    return resp.json()


if __name__ == "__main__":
    check_api_ready()
    session_id = get_active_session_id()
    print(f"Usando sesion: {session_id}")
    result = publish_test_post(session_id)
    print("Resultado:", result)