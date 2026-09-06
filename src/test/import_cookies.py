import json
import sys

import httpx

from facebook_api.config import settings

BASE_URL = settings.PUBLIC_BASE_URL

NOTA = """
NOTA: El flujo RECOMENDADO es la extension de navegador (carpeta extension/),
que exporta las cookies automaticamente. Este script es un fallback manual
por si no puedes usar la extension.
"""


def get_cookies_from_snippet() -> list[dict]:
    print(NOTA)
    print(
        """
Para obtener las cookies:

1. Abre https://www.facebook.com en tu navegador y logueate (sesion activa).
2. Instala la extension "Cookie-Editor" (https://cookie-editor.cgagnier.ca) o "EditThisCookie".
3. Abre la extension en la pestana de facebook.com (habra muchas cookies listadas).
4. Pulsa "Export" / "Exportar" y copia el JSON completo (empieza con "[" y termina con "]").
   En Cookie-Editor usa "Export" > "JSON" > "Copy to clipboard".

Nota: las cookies usa `document.cookie` no sirve; estas cookies de sesion
(c_user, xs, datr) son httpOnly y solo las lee la extension.

5. Pega aqui el JSON copiado.
"""
    )
    raw = input("Pega el JSON de las cookies aqui (o deja vacio para usar un archivo): ").strip()

    if not raw:
        path = input("Ruta del archivo JSON con las cookies: ").strip()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"No existe el archivo: {path}")
        except json.JSONDecodeError:
            raise RuntimeError("El archivo no es JSON valido")

    try:
        cookies = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("El JSON pegado no es valido")
    return cookies


def import_cookies(cookies: list[dict], session_name: str) -> dict:
    resp = httpx.post(
        f"{BASE_URL}/auth/import-cookies",
        json={"cookies": cookies, "session_name": session_name},
        timeout=60,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", str(resp.text))
        except Exception:
            detail = str(resp.text)
        raise RuntimeError(f"La API respondio {resp.status_code}: {detail}")
    return resp.json()


if __name__ == "__main__":
    session_name = sys.argv[1] if len(sys.argv) > 1 else "default"
    try:
        cookies = get_cookies_from_snippet()
        if not cookies:
            raise RuntimeError("No se obtuvieron cookies")
        result = import_cookies(cookies, session_name)
        print("OK:", result["session_id"], "->", result["status"])
    except RuntimeError as e:
        print("ERROR:", e)
        sys.exit(1)