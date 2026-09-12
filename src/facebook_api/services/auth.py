import asyncio
import json
import logging

from sqlalchemy import select, update

from facebook_api.models.session import FacebookSession
from facebook_api.services.facebook import (
    _cookies_are_session_cookies,
    verify_cookies,
)
from facebook_api.utils.browser import random_user_agent
from facebook_api.utils.crypto import encrypt_data
from facebook_api.utils.state import login_state

logger = logging.getLogger("facebook-api")

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

    # Facebook a veces responde con timeout o pagina de login en el primer
    # intento con un contexto nuevo. Reintentamos la verificacion antes de
    # rechazar la sesion importada.
    verification = {"valid": False, "reason": "No se pudo verificar"}
    last_error = None
    for attempt in range(3):
        try:
            verification = await verify_cookies(cookies)
        except Exception as e:
            last_error = str(e)
            verification = {"valid": False, "reason": str(e)}
        if verification["valid"]:
            break
        await asyncio.sleep(1.5 * (attempt + 1))

    if not verification["valid"]:
        reason = verification.get("reason") or last_error or "desconocido"
        logger.warning("Import de cookies rechazado tras reintentos: %s", reason)
        raise ValueError(f"Cookies invalidas: {reason}")

    resolved_user_id = fb_user_id or verification.get("fb_user_id")
    encrypted = encrypt_data(json.dumps(cookies))

    # Nueva sesion activa: desactivamos las anteriores para que siempre se
    # use la ultima sesion exportada.
    await db.execute(
        update(FacebookSession)
        .where(FacebookSession.is_active == True)
        .values(is_active=False)
    )
    await db.flush()

    session = FacebookSession(
        session_name=session_name,
        fb_user_id=resolved_user_id,
        fb_email=fb_email,
        encrypted_cookies=encrypted,
        user_agent=random_user_agent(),
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    login_state.mark_logged_in(str(session.id))
    return session


async def get_last_active_session(db) -> FacebookSession | None:
    result = await db.execute(
        select(FacebookSession)
        .where(FacebookSession.is_active)
        .order_by(FacebookSession.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
