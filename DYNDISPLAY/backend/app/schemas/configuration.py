from datetime import date, time
from typing import Optional, List

from pydantic import BaseModel, Field


class ZoneMediaItem(BaseModel):
    media_id: Optional[int] = None
    duration_seconds: Optional[int] = Field(None, ge=1)


class ZoneMediaAssignment(BaseModel):
    zone_number: int = Field(..., ge=1, le=8)
    media_id: Optional[int] = None
    duration_seconds: Optional[int] = Field(None, ge=1)
    display_order: Optional[int] = Field(None, ge=1)


class ZonePlaylist(BaseModel):
    media_id: Optional[int] = None
    duration_seconds: Optional[int] = Field(None, ge=1)


class ScheduleCreate(BaseModel):
    name: str = Field(..., max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    days_of_week: Optional[str] = Field(None, max_length=50)
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    days_of_week: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class ScheduleOut(BaseModel):
    schedule_id: int
    post_id: int
    name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PostConfigurationUpdate(BaseModel):
    layout_id: Optional[int] = None
    loop_enabled: bool = True
    schedule_enabled: bool = False
    display_enabled: bool = True
    zones: List[ZoneMediaAssignment] = []


class PostConfigurationOut(BaseModel):
    post_id: int
    code: str = ""
    name: str = ""
    layout: Optional[dict] = None
    zones: List[dict] = []
    loop_enabled: bool = True
    schedule_enabled: bool = False
    display_enabled: bool = True
    schedules: List[ScheduleOut] = []


class MessageResponse(BaseModel):
    message: str
