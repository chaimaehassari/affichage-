from pydantic import BaseModel


class SupervisionPostOut(BaseModel):
    post_id: int
    code: str
    name: str
    is_online: bool
    is_up_to_date: bool
    last_sync_at: str | None = None
    last_heartbeat_at: str | None = None
    display_enabled: bool
    status: str


class SupervisionSiteOut(BaseModel):
    site_id: int
    code: str
    name: str
    posts: list[SupervisionPostOut]


class HeartbeatRequest(BaseModel):
    post_id: int
