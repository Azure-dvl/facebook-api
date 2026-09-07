import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from facebook_api.database import get_db
from facebook_api.models.session import FacebookSession
from facebook_api.schemas.auth import ImportCookiesRequest, SessionInfo, SessionListResponse
from facebook_api.services.auth import import_cookies

logger = logging.getLogger("facebook-api")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/import-cookies")
async def auth_import_cookies(
    req: ImportCookiesRequest, db: AsyncSession = Depends(get_db)
):
    try:
        session = await import_cookies(
            cookies=[c.model_dump() for c in req.cookies],
            db=db,
            fb_user_id=req.fb_user_id,
            fb_email=req.fb_email,
            session_name=req.session_name,
        )
        return {"session_id": str(session.id), "status": "authenticated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error en /auth/import-cookies:\n%s", traceback.format_exc()
        )
        raise HTTPException(status_code=500, detail=f"Error importando cookies: {e}")


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
