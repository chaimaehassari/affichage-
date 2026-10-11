from datetime import date, datetime, time
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator

from app.services.reboot_schedule_service import (
    check_reboot_once_format,
    check_reboot_once_future,
    validate_reboot_time,
)


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
    reboot_enabled: Optional[bool] = None
    reboot_time: Optional[str] = None
    reboot_once_at: Optional[datetime] = None

    @field_validator("reboot_time")
    @classmethod
    def _validate_reboot_time(cls, v):
        return validate_reboot_time(v) if v is not None else None

    @field_validator("reboot_once_at", mode="before")
    @classmethod
    def _validate_reboot_once_format(cls, v):
        check_reboot_once_format(v)
        # Chaîne vide = pas de valeur (même convention que reboot_time) : elle
        # annule le ponctuel au lieu de retomber sur le message générique de
        # Pydantic sur les datetime.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("reboot_once_at")
    @classmethod
    def _validate_reboot_once_future(cls, v):
        check_reboot_once_future(v)
        return v


class PostConfigurationOut(BaseModel):
    post_id: int
    code: str = ""
    name: str = ""
    layout: Optional[dict] = None
    zones: List[dict] = []
    loop_enabled: bool = True
    schedule_enabled: bool = False
    display_enabled: bool = True
    reboot_enabled: bool = False
    reboot_time: Optional[str] = None
    next_reboot_at: Optional[str] = None
    reboot_once_at: Optional[str] = None
    schedules: List[ScheduleOut] = []


class MessageResponse(BaseModel):
    message: str
