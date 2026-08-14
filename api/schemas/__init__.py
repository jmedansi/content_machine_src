"""Pydantic schemas for unified API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class TaskCreateRequest(BaseModel):
    """Request to create a new task."""
    platform: str
    persona: str = "default"
    content_type: str = "post"
    topic: str = ""
    text: Optional[str] = None
    media_url: Optional[str] = None
    priority: int = 2

class TaskResponse(BaseModel):
    """Task response model."""
    id: str
    platform: str
    persona: str
    content_type: str
    topic: str
    status: str
    priority: int
    created_at: str
    completed_at: Optional[str] = None
    result_url: Optional[str] = None
    error: Optional[str] = None

class DailyPlanResponse(BaseModel):
    """Daily plan response."""
    date: str
    total_tasks: int
    tasks_by_platform: dict
    created_at: str

class PlatformStatus(BaseModel):
    """Platform status."""
    platform: str
    personas: list[str]
    supported_content_types: list[str]
    is_active: bool

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    platforms: list[PlatformStatus]
    version: str = "1.0.0"