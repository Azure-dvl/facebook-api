from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from facebook_api.database import get_db
from facebook_api.models.post import PostLog, PostStatus, TargetType
from facebook_api.models.session import FacebookSession
from facebook_api.schemas.post import (
    CreatePostRequest,
    PostHistoryResponse,
    PostLogEntry,
    PostResponse,
)
from facebook_api.services.facebook import post_to_group, post_to_profile
from facebook_api.utils.crypto import decrypt_data

router = APIRouter(prefix="/posts", tags=["posts"])


async def _get_active_session(
    session_id: str, db: AsyncSession
) -> FacebookSession:
    result = await db.execute(
        select(FacebookSession).where(
            FacebookSession.id == session_id, FacebookSession.is_active
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or inactive")
    return session


@router.post("/create", response_model=PostResponse)
async def create_post(req: CreatePostRequest, db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(req.session_id, db)

    if req.target == "group" and not req.target_id:
        raise HTTPException(
            status_code=400, detail="target_id required for group posts"
        )

    if req.target == "group":
        result = await post_to_group(
            session.encrypted_cookies,
            decrypt_data,
            req.target_id,
            req.text,
            req.image_urls,
        )
        target_id = req.target_id
        target_type = TargetType.group
    else:
        result = await post_to_profile(
            session.encrypted_cookies,
            decrypt_data,
            req.text,
            req.image_urls,
        )
        target_id = "me"
        target_type = TargetType.profile

    status = PostStatus.success if result["status"] == "success" else PostStatus.failed

    log = PostLog(
        session_id=session.id,
        target_type=target_type,
        target_id=target_id,
        content_text=req.text,
        image_paths=req.image_urls,
        status=status,
        error_message=result.get("error"),
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return PostResponse(
        status=result["status"],
        post_id=str(log.id),
        error=result.get("error"),
    )


@router.get("/history", response_model=PostHistoryResponse)
async def post_history(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PostLog)
        .where(PostLog.session_id == session_id)
        .order_by(PostLog.created_at.desc())
    )
    posts = result.scalars().all()
    return PostHistoryResponse(
        posts=[
            PostLogEntry(
                id=str(p.id),
                target_type=p.target_type.value,
                target_id=p.target_id,
                content_text=p.content_text,
                image_paths=p.image_paths,
                status=p.status.value,
                error_message=p.error_message,
                created_at=p.created_at.isoformat() if p.created_at else "",
            )
            for p in posts
        ]
    )


@router.get("/{post_id}", response_model=PostLogEntry)
async def get_post(post_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PostLog).where(PostLog.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return PostLogEntry(
        id=str(post.id),
        target_type=post.target_type.value,
        target_id=post.target_id,
        content_text=post.content_text,
        image_paths=post.image_paths,
        status=post.status.value,
        error_message=post.error_message,
        created_at=post.created_at.isoformat() if post.created_at else "",
    )
