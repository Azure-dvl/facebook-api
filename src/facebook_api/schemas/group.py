from pydantic import BaseModel


class GroupInfo(BaseModel):
    id: str
    name: str


class GroupListResponse(BaseModel):
    groups: list[GroupInfo]
