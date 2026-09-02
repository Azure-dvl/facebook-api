from pydantic import BaseModel


class CreatePostRequest(BaseModel):
    session_id: str
    target: str
    target_id: str | None = None
    text: str
    image_urls: list[str] | None = None


class PostResponse(BaseModel):
    status: str
    post_id: str | None = None
    error: str | None = None


class PostLogEntry(BaseModel):
    id: str
    target_type: str
    target_id: str
    content_text: str
    image_paths: list[str] | None = None
    status: str
    error_message: str | None = None
    created_at: str


class PostHistoryResponse(BaseModel):
    posts: list[PostLogEntry]
