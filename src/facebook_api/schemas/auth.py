from pydantic import BaseModel, Field


class CredentialRequest(BaseModel):
    token: str
    email: str
    password: str
    session_name: str = "default"


class CookieDict(BaseModel):
    name: str
    value: str
    domain: str = ".facebook.com"
    path: str = "/"
    expires: float = -1
    httpOnly: bool = False
    secure: bool = True
    sameSite: str | None = None


class ImportCookiesRequest(BaseModel):
    cookies: list[CookieDict]
    session_name: str = "default"
    fb_user_id: str | None = Field(default=None, description="ID del usuario (opcional, se auto-detecta si no se da)")
    fb_email: str = "imported"


class StartAuthResponse(BaseModel):
    qr_image_base64: str
    login_url: str
    expires_in: int


class SessionInfo(BaseModel):
    id: str
    session_name: str
    fb_email: str
    is_active: bool
    created_at: str
    last_used: str | None


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
