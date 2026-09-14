from typing import Optional, List

from pydantic import BaseModel, Field


class LayoutZoneCreate(BaseModel):
    zone_number: int = Field(..., ge=1, le=8)
    position_x: float = Field(..., ge=0, le=100)
    position_y: float = Field(..., ge=0, le=100)
    width: float = Field(..., ge=0, le=100)
    height: float = Field(..., ge=0, le=100)
    is_active: bool = False


class LayoutZoneOut(LayoutZoneCreate):
    layout_zone_id: int


class LayoutCreate(BaseModel):
    name: str = Field(..., max_length=150)
    is_active: bool = True
    zones: List[LayoutZoneCreate]


class LayoutUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    is_active: Optional[bool] = None
    zones: Optional[List[LayoutZoneCreate]] = None


class LayoutOut(BaseModel):
    layout_id: int
    name: str
    is_active: bool
    active_zone_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LayoutDetailOut(BaseModel):
    layout_id: int
    name: str
    is_active: bool
    active_zone_count: int = 0
    zones: List[LayoutZoneOut] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
