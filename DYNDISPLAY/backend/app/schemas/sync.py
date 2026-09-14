from typing import Optional, List

from pydantic import BaseModel


class SyncJobCreate(BaseModel):
    scheduled_at: Optional[str] = None


class SyncItemOut(BaseModel):
    sync_item_id: int
    media_id: Optional[int] = None
    item_type: str
    item_path: Optional[str] = None
    status: str
    progress_percent: int = 0


class SyncJobOut(BaseModel):
    sync_job_id: int
    post_id: int
    status: str
    progress_percent: int = 0
    transfer_speed: int = 0
    estimated_remaining_seconds: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    scheduled_at: Optional[str] = None
    items: List[SyncItemOut] = []
