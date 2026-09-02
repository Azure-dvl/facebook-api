import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from facebook_api.database import Base


class FacebookSession(Base):
    __tablename__ = "facebook_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_name: Mapped[str] = mapped_column(String(255))
    fb_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fb_email: Mapped[str] = mapped_column(String(255))
    encrypted_cookies: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )
