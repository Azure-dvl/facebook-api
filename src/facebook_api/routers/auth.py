from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from facebook_api.database import get_db
from facebook_api.models.session import FacebookSession
from facebook_api.schemas.auth import (
    CredentialRequest,
    SessionInfo,
    SessionListResponse,
    StartAuthResponse,
)
from facebook_api.services.auth import complete_auth, start_auth_flow
from facebook_api.utils.state import login_state

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/start", response_model=StartAuthResponse)
async def auth_start(request: Request):
    host = request.headers.get("host", "localhost")
    flow = start_auth_flow(host)
    return StartAuthResponse(**flow)


LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Facebook Login - API</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #f0f2f5; display: flex; justify-content: center; align-items: center;
               min-height: 100vh; padding: 20px; }
        .card { background: white; border-radius: 8px; padding: 40px; width: 100%;
                max-width: 400px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #1877f2; margin-bottom: 8px; font-size: 24px; }
        p { text-align: center; color: #65676b; margin-bottom: 24px; font-size: 14px; }
        input { width: 100%; padding: 12px; border: 1px solid #dddfe2; border-radius: 6px;
                font-size: 16px; margin-bottom: 12px; outline: none; }
        input:focus { border-color: #1877f2; }
        button { width: 100%; padding: 12px; background: #1877f2; color: white; border: none;
                 border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:hover { background: #166fe5; }
        .error { color: #dc3545; text-align: center; margin-top: 12px; display: none; }
        .success { color: #28a745; text-align: center; margin-top: 12px; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Facebook API</h1>
        <p>Ingresa tus credenciales para autenticar</p>
        <form id="loginForm">
            <input type="hidden" id="token" name="token">
            <input type="text" id="email" placeholder="Email o teléfono" required>
            <input type="password" id="password" placeholder="Contraseña" required>
            <input type="text" id="session_name" placeholder="Nombre de sesión (opcional)" value="default">
            <button type="submit">Autenticar</button>
        </form>
        <div class="error" id="error"></div>
        <div class="success" id="success">¡Autenticación exitosa! Ya puedes cerrar esta ventana.</div>
    </div>
    <script>
        const params = new URLSearchParams(window.location.search);
        document.getElementById('token').value = params.get('t') || '';
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errDiv = document.getElementById('error');
            const sucDiv = document.getElementById('success');
            errDiv.style.display = 'none';
            sucDiv.style.display = 'none';
            try {
                const resp = await fetch('/auth/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token: document.getElementById('token').value,
                        email: document.getElementById('email').value,
                        password: document.getElementById('password').value,
                        session_name: document.getElementById('session_name').value || 'default'
                    })
                });
                const data = await resp.json();
                if (resp.ok) {
                    sucDiv.style.display = 'block';
                } else {
                    errDiv.textContent = data.detail || 'Error en la autenticación';
                    errDiv.style.display = 'block';
                }
            } catch (err) {
                errDiv.textContent = 'Error de conexión';
                errDiv.style.display = 'block';
            }
        });
    </script>
</body>
</html>"""


@router.get("/login", response_class=HTMLResponse)
async def auth_login_page(t: str = ""):
    return HTMLResponse(content=LOGIN_PAGE_HTML)


@router.post("/credentials")
async def auth_credentials(req: CredentialRequest, db: AsyncSession = Depends(get_db)):
    try:
        session = await complete_auth(
            req.token, req.email, req.password, req.session_name, db
        )
        login_state.mark_logged_in(str(session.id))
        return {"session_id": str(session.id), "status": "authenticated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FacebookSession).where(FacebookSession.is_active))
    sessions = result.scalars().all()
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=str(s.id),
                session_name=s.session_name,
                fb_email=s.fb_email,
                is_active=s.is_active,
                created_at=s.created_at.isoformat() if s.created_at else "",
                last_used=s.last_used.isoformat() if s.last_used else None,
            )
            for s in sessions
        ]
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FacebookSession).where(FacebookSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_active = False
    await db.commit()
    return {"status": "deleted"}
