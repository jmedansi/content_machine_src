"""Unified API routes for all platforms."""
from fastapi import APIRouter
from typing import Optional, List
from core.shared.base import PlatformType, ContentType
from scheduler.models import PlatformTask, TaskStatus
from api.schemas import TaskCreateRequest, TaskResponse, PlatformStatus

router = APIRouter(prefix="/api/v1", tags=["tasks"])

tasks_storage: dict = {}


@router.get("/health")
async def health_check():
    """Check API health."""
    return {
        "status": "ok",
        "platforms": ["facebook", "linkedin", "twitter"],
        "version": "1.0.0"
    }


@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreateRequest):
    """Create a new publishing task."""
    task = PlatformTask()
    task.platform = PlatformType(request.platform)
    task.persona = request.persona
    task.content_type = ContentType(request.content_type)
    task.topic = request.topic
    task.text = request.text
    task.media_url = request.media_url

    tasks_storage[task.id] = task

    return TaskResponse(
        id=task.id,
        platform=task.platform.value,
        persona=task.persona,
        content_type=task.content_type.value,
        topic=task.topic,
        status=task.status.value,
        priority=task.priority.value,
        created_at=task.created_at.isoformat()
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get a task by ID."""
    task = tasks_storage.get(task_id)
    if not task:
        return {"error": "Task not found"}

    return TaskResponse(
        id=task.id,
        platform=task.platform.value if task.platform else None,
        persona=task.persona,
        content_type=task.content_type.value,
        topic=task.topic,
        status=task.status.value,
        priority=task.priority.value,
        created_at=task.created_at.isoformat(),
        completed_at=task.completed_at.isoformat() if task.completed_at else None
    )


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks():
    """List all tasks."""
    return [
        TaskResponse(
            id=task.id,
            platform=task.platform.value,
            persona=task.persona,
            content_type=task.content_type.value,
            topic=task.topic,
            status=task.status.value,
            priority=task.priority.value,
            created_at=task.created_at.isoformat()
        )
        for task in tasks_storage.values()
    ]


@router.get("/platforms")
async def list_platforms():
    """List available platforms and their personas."""
    return {
        "platforms": [
            {
                "name": "facebook",
                "personas": ["b2b_expert", "networker", "carousel_pro"],
                "content_types": ["post", "reel", "story"]
            },
            {
                "name": "linkedin",
                "personas": ["b2b_expert", "networker", "carousel_pro"],
                "content_types": ["post", "carousel"]
            },
            {
                "name": "twitter",
                "personas": ["hot_take", "thread_maker", "meme_lord"],
                "content_types": ["post", "thread"]
            }
        ]
    }