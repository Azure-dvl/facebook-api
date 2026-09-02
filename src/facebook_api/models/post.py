import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from facebook_api.database import Base


class TargetType(enum.Enum):
    group = "group"
    profile = "profile"


class PostStatus(enum.Enum):
    success = "success"
    failed = "failed"


class PostLog(Base):
    __tablename__ = "post_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facebook_sessions.id")
    )
    target_type: Mapped[TargetType] = mapped_column(
        Enum(TargetType, name="target_type_enum")
    )
    target_id: Mapped[str] = mapped_column(String(100))
    content_text: Mapped[str] = mapped_column(Text)
    image_paths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, name="post_status_enum")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
