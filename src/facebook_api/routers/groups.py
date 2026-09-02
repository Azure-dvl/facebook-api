from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from facebook_api.database import get_db
from facebook_api.models.session import FacebookSession
from facebook_api.schemas.group import GroupInfo, GroupListResponse
from facebook_api.services.facebook import list_groups
from facebook_api.utils.crypto import decrypt_data

router = APIRouter(prefix="/groups", tags=["groups"])


async def _get_session(session_id: str, db: AsyncSession) -> FacebookSession:
    result = await db.execute(
        select(FacebookSession).where(
            FacebookSession.id == session_id, FacebookSession.is_active
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return session


@router.get("", response_model=GroupListResponse)
async def get_groups(
    session_id: str = Query(..., description="Session ID"),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, db)
    groups = await list_groups(session.encrypted_cookies, decrypt_data)
    return GroupListResponse(
        groups=[GroupInfo(id=g["id"], name=g["name"]) for g in groups]
    )


@router.get("/{group_id}", response_model=GroupInfo)
async def get_group_info(group_id: str, session_id: str = Query(...)):
    return GroupInfo(id=group_id, name=f"Group {group_id}")
