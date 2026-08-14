"""Base classes for Content Machine multi-platform architecture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PlatformType(Enum):
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    THREADS = "threads"


class ContentType(Enum):
    POST = "post"
    CAROUSEL = "carousel"
    REEL = "reel"
    THREAD = "thread"
    STORY = "story"


@dataclass
class ContentItem:
    """Represents a piece of content."""
    text: str
    content_type: ContentType
    platform: PlatformType
    persona: str
    media_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PublishingResult:
    """Result of a publish operation."""
    success: bool
    platform: PlatformType
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class BasePlatform(ABC):
    """Base class for all platform implementations.
    
    Each platform (Facebook, LinkedIn, Twitter) must inherit from this
    and implement the required methods.
    """
    
    platform_type: PlatformType
    
    def __init__(self, config: dict):
        self.config = config
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate platform-specific configuration."""
        pass
    
    @abstractmethod
    async def publish(self, content: ContentItem) -> PublishingResult:
        """Publish content to the platform."""
        pass
    
    @abstractmethod
    async def get_post(self, post_id: str) -> ContentItem:
        """Retrieve a post by ID."""
        pass
    
    @abstractmethod
    async def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID."""
        pass
    
    @property
    @abstractmethod
    def supported_content_types(self) -> list[ContentType]:
        """List of supported content types for this platform."""
        pass
    
    def get_config(self, key: str, default=None):
        """Safe config access."""
        return self.config.get(key, default)


class BasePersona(ABC):
    """Base class for all personas.
    
    Each persona defines how content is generated for a specific style/voice.
    """
    
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
    
    @abstractmethod
    def generate_prompt(self, topic: str, context: dict) -> str:
        """Generate the system prompt for content generation."""
        pass
    
    @abstractmethod
    def format_output(self, raw_content: str) -> str:
        """Format the raw content for the platform."""
        pass
    
    @abstractmethod
    def get_characteristics(self) -> dict:
        """Return persona characteristics (tone, length, etc.)."""
        pass


class BasePublisher(ABC):
    """Base class for publishing content."""
    
    @abstractmethod
    async def publish(self, content: ContentItem) -> PublishingResult:
        pass


class BaseImageGenerator(ABC):
    """Base class for image generation."""
    
    @abstractmethod
    async def generate(self, prompt: str, style: str) -> str:
        """Generate image and return URL."""
        pass


class PlatformRegistry:
    """Registry for platform plugins using Factory pattern."""
    
    _platforms: dict[PlatformType, type[BasePlatform]] = {}
    _instances: dict[PlatformType, BasePlatform] = {}
    
    @classmethod
    def register(cls, platform_type: PlatformType):
        """Decorator to register a platform class."""
        def decorator(platform_class: type[BasePlatform]):
            cls._platforms[platform_type] = platform_class
            return platform_class
        return decorator
    
    @classmethod
    def create(cls, platform_type: PlatformType, config: dict) -> BasePlatform:
        """Create a platform instance."""
        if platform_type not in cls._platforms:
            raise ValueError(f"Platform {platform_type} not registered")
        
        if platform_type not in cls._instances:
            cls._instances[platform_type] = cls._platforms[platform_type](config)
        
        return cls._instances[platform_type]
    
    @classmethod
    def get_available(cls) -> list[PlatformType]:
        """Get list of registered platforms."""
        return list(cls._platforms.keys())
    
    @classmethod
    def clear_instances(cls):
        """Clear all instances (useful for testing)."""
        cls._instances.clear()