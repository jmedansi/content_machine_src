"""Base publishing strategies for each platform."""
from abc import ABC, abstractmethod
from core.shared.base import PlatformType, ContentType, ContentItem, PublishingResult
from scheduler.models import PlatformTask
import asyncio

class PublisherStrategy(ABC):
    """Abstract base for platform publishing strategies."""
    
    platform_type: PlatformType
    
    @abstractmethod
    async def publish_task(self, task: PlatformTask) -> PublishingResult:
        """Publish a single task."""
        pass
    
    @abstractmethod
    async def generate_content(self, task: PlatformTask) -> ContentItem:
        """Generate content for a task using persona."""
        pass

class FacebookPublisher(PublisherStrategy):
    """Facebook publishing strategy."""
    
    platform_type = PlatformType.FACEBOOK
    
    def __init__(self, platform_instance):  # type: ignore
        self.platform = platform_instance
    
    async def publish_task(self, task: PlatformTask) -> PublishingResult:
        """Publish a task to Facebook."""
        if task.status.value == "running":
            return PublishingResult(success=False, platform=self.platform_type, error="Task already running")
        
        try:
            task.status.value = "running"
            content = await self.generate_content(task)
            result = await self.platform.publish(content)
            task.result = result
            return result
        except Exception as e:
            return PublishingResult(success=False, platform=self.platform_type, error=str(e))
    
    async def generate_content(self, task: PlatformTask) -> ContentItem:
        """Generate content using Facebook's persona system."""
        # Load persona prompt and generate content
        persona_prompt = self.platform.get_persona_prompt(task.persona)
        persona_config = self.platform.get_persona_config(task.persona)
        
        return ContentItem(
            text=task.text or "",  # Would be generated via LLM
            content_type=task.content_type,
            platform=task.platform,
            persona=task.persona,
            media_url=task.media_url,
            metadata={"prompt": persona_prompt, "config": persona_config}
        )

class LinkedInPublisher(PublisherStrategy):
    """LinkedIn publishing strategy."""
    
    platform_type = PlatformType.LINKEDIN
    
    def __init__(self, platform_instance):  # type: ignore
        self.platform = platform_instance
    
    async def publish_task(self, task: PlatformTask) -> PublishingResult:
        """Publish a task to LinkedIn."""
        content = await self.generate_content(task)
        return await self.platform.publish(content)
    
    async def generate_content(self, task: PlatformTask) -> ContentItem:
        """Generate content using LinkedIn's persona."""
        persona_config = self.platform.get_persona_config(task.persona)
        
        return ContentItem(
            text=task.text or "",
            content_type=task.content_type,
            platform=task.platform,
            persona=task.persona,
            media_url=task.media_url,
            metadata={"config": persona_config}
        )

class TwitterPublisher(PublisherStrategy):
    """Twitter publishing strategy."""
    
    platform_type = PlatformType.TWITTER
    
    def __init__(self, platform_instance):  # type: ignore
        self.platform = platform_instance
    
    async def publish_task(self, task: PlatformTask) -> PublishingResult:
        """Publish a task to Twitter."""
        content = await self.generate_content(task)
        return await self.platform.publish(content)
    
    async def generate_content(self, task: PlatformTask) -> ContentItem:
        """Generate content for Twitter."""
        return ContentItem(
            text=task.text or "",
            content_type=task.content_type,
            platform=task.platform,
            persona=task.persona,
            media_url=task.media_url
        )