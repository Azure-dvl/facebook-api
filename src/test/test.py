import httpx
from facebook_api.config import settings

BASE_URL = f"http://localhost:{settings.APP_PORT}"


def get_active_session_id() -> str:
    resp = httpx.get(f"{BASE_URL}/auth/sessions", timeout=10)
    resp.raise_for_status()
    sessions = resp.json().get("sessions", [])
    active = [s for s in sessions if s.get("is_active")]
    if not active:
        raise RuntimeError("No hay sesiones activas. Logueate primero con main.py")
    return active[0]["id"]


def publish_test_post(session_id: str) -> dict:
    body = {
        "session_id": session_id,
        "target": "profile",
        "text": "Prueba",
    }
    resp = httpx.post(f"{BASE_URL}/posts/create", json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    session_id = get_active_session_id()
    print(f"Usando sesion: {session_id}")
    result = publish_test_post(session_id)
    print("Resultado:", result)
