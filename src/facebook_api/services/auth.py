import base64
import json

from facebook_api.config import settings
from facebook_api.models.session import FacebookSession
from facebook_api.services.facebook import (
    _cookies_are_session_cookies,
    login_facebook,
    verify_cookies,
)
from facebook_api.utils.crypto import encrypt_data
from facebook_api.utils.qrcode import (
    consume_qr_token,
    create_qr_token,
    generate_qr_image,
    validate_qr_token,
)
from facebook_api.utils.state import login_state

_SAMESITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
}


def normalize_cookie(c: dict) -> dict | None:
    name = c.get("name")
    value = c.get("value")
    if name is None or value is None:
        return None

    domain = c.get("domain") or ".facebook.com"
    if domain.startswith(".") and not domain.endswith("facebook.com"):
        domain = ".facebook.com"

    expires = -1
    raw_exp = c.get("expirationDate") or c.get("expires")
    if raw_exp is not None:
        try:
            expires = float(raw_exp)
        except (TypeError, ValueError):
            expires = -1

    ss_raw = c.get("sameSite")
    same_site = _SAMESITE_MAP.get((ss_raw or "").lower())

    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": c.get("path") or "/",
        "expires": expires,
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": bool(c.get("secure", True)),
        **({"sameSite": same_site} if same_site else {}),
    }


async def import_cookies(
    cookies: list[dict],
    db,
    fb_user_id: str | None = None,
    fb_email: str = "extension",
    session_name: str = "default",
) -> FacebookSession:
    cookies = [normalize_cookie(c) for c in cookies]
    cookies = [c for c in cookies if c]
    if not cookies:
        raise ValueError("No se enviaron cookies")

    if not _cookies_are_session_cookies(cookies):
        raise ValueError(
            "Las cookies no parecen de una sesion logueada. "
            "Faltan c_user y xs/datr."
        )

    verification = await verify_cookies(cookies)
    if not verification["valid"]:
        raise ValueError(
            f"Cookies invalidas: {verification.get('reason', 'desconocido')}"
        )

    resolved_user_id = fb_user_id or verification.get("fb_user_id")
    encrypted = encrypt_data(json.dumps(cookies))

    session = FacebookSession(
        session_name=session_name,
        fb_user_id=resolved_user_id,
        fb_email=fb_email,
        encrypted_cookies=encrypted,
        user_agent="extension",
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    login_state.mark_logged_in(str(session.id))
    return session


def start_auth_flow() -> dict:
    token = create_qr_token()
    login_url = f"{settings.PUBLIC_BASE_URL}/auth/login?t={token}"
    qr_bytes = generate_qr_image(login_url)
    qr_b64 = base64.b64encode(qr_bytes).decode()
    return {
        "qr_image_base64": qr_b64,
        "login_url": login_url,
        "expires_in": settings.QR_TOKEN_TTL,
    }


async def complete_auth(
    token: str, email: str, password: str, session_name: str, db
) -> FacebookSession:
    if not validate_qr_token(token):
        raise ValueError("El link es invalido o expiro. Genera un nuevo QR.")

    result = await login_facebook(email, password)

    consume_qr_token(token)

    cookies_json = json.dumps(result["cookies"])
    encrypted = encrypt_data(cookies_json)

    session = FacebookSession(
        session_name=session_name,
        fb_user_id=result.get("fb_user_id"),
        fb_email=email,
        encrypted_cookies=encrypted,
        user_agent=result["user_agent"],
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
