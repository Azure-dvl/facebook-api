from pydantic import BaseModel


class CredentialRequest(BaseModel):
    token: str
    email: str
    password: str
    session_name: str = "default"


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
