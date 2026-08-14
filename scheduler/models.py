"""Models for unified scheduler."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

from core.shared.base import PlatformType, ContentType


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class TaskSchedule:
    """Schedule time for a task."""
    hour: int
    minute: int = 0
    days_of_week: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])


@dataclass
class TaskResult:
    """Result of a published task."""
    post_id: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class PlatformTask:
    """A task for a specific platform."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    platform: PlatformType = None
    persona: str = "default"
    content_type: ContentType = ContentType.POST
    topic: str = ""
    text: Optional[str] = None
    media_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    
    status: TaskStatus = TaskStatus.PENDING
    schedule: Optional[TaskSchedule] = None
    scheduled_at: Optional[datetime] = None
    result: Optional[TaskResult] = None
    
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    retries: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "platform": self.platform.value if self.platform else None,
            "persona": self.persona,
            "content_type": self.content_type.value,
            "topic": self.topic,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PlatformTask":
        """Create from dictionary."""
        task = cls()
        task.id = data.get("id", task.id)
        if data.get("platform"):
            task.platform = PlatformType(data["platform"])
        task.persona = data.get("persona", "default")
        task.content_type = ContentType(data.get("content_type", "post"))
        task.topic = data.get("topic", "")
        task.status = TaskStatus(data.get("status", "pending"))
        return task


@dataclass
class DailyPlan:
    """Daily plan containing multiple tasks."""
    date: str
    platform_tasks: dict[PlatformType, list[PlatformTask]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_task(self, task: PlatformTask) -> None:
        """Add a task to the plan."""
        if task.platform not in self.platform_tasks:
            self.platform_tasks[task.platform] = []
        self.platform_tasks[task.platform].append(task)
    
    def get_tasks(self, platform: PlatformType = None) -> list[PlatformTask]:
        """Get tasks, optionally filtered by platform."""
        if platform:
            return self.platform_tasks.get(platform, [])
        return sum(self.platform_tasks.values(), [])