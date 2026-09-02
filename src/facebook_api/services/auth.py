import base64
import json

from facebook_api.config import settings
from facebook_api.models.session import FacebookSession
from facebook_api.services.facebook import login_facebook
from facebook_api.utils.crypto import encrypt_data
from facebook_api.utils.qrcode import (
    consume_qr_token,
    create_qr_token,
    generate_qr_image,
)


def start_auth_flow(host: str) -> dict:
    token = create_qr_token()
    login_url = f"http://{host}:{settings.APP_PORT}/auth/login?t={token}"
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
    if not consume_qr_token(token):
        raise ValueError("Invalid or expired token")

    result = await login_facebook(email, password)

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
