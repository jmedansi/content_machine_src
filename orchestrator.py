"""Content Machine Orchestrator - Main entry point for multi-platform content generation."""

import asyncio
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from core.shared.base import (
    PlatformType,
    ContentType,
    ContentItem,
    PublishingResult,
    BasePlatform,
)
from core.shared.loader import PlatformLoader


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    facebook_config: dict = None
    linkedin_config: dict = None
    twitter_config: dict = None
    
    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        """Load configuration from environment variables."""
        return cls(
            facebook_config={
                "base_dir": os.getenv("FACEBOOK_BASE_DIR", "machines/facebook_machine"),
                "page_id": os.getenv("FB_PAGE_ID"),
                "access_token": os.getenv("FB_PAGE_ACCESS_TOKEN"),
            },
            linkedin_config={
                "base_dir": os.getenv("LINKEDIN_BASE_DIR", "machines/linkedin_machine"),
                "access_token": os.getenv("LINKEDIN_ACCESS_TOKEN"),
                "person_urn": os.getenv("LINKEDIN_PERSON_URN"),
            },
            twitter_config={
                "api_key": os.getenv("TWITTER_API_KEY"),
                "api_secret": os.getenv("TWITTER_API_SECRET"),
                "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
                "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
                "bearer_token": os.getenv("TWITTER_BEARER_TOKEN"),
            },
        )


class ContentOrchestrator:
    """Main orchestrator for the Content Machine.
    
    Manages all platforms and orchestrates content generation and publishing.
    """
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig.from_env()
        self.platforms: dict[PlatformType, BasePlatform] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all platforms."""
        if self._initialized:
            return
        
        configs = {
            PlatformType.FACEBOOK: self.config.facebook_config,
            PlatformType.LINKEDIN: self.config.linkedin_config,
            PlatformType.TWITTER: self.config.twitter_config,
        }
        
        for platform_type, config in configs.items():
            if config:
                try:
                    platform = PlatformLoader.load_platform(platform_type, config)
                    self.platforms[platform_type] = platform
                    print(f"Initialized: {platform_type.value}")
                except Exception as e:
                    print(f"Failed to initialize {platform_type.value}: {e}")
        
        self._initialized = True
    
    def get_platform(self, platform_type: PlatformType) -> Optional[BasePlatform]:
        """Get a platform by type."""
        return self.platforms.get(platform_type)
    
    def list_platforms(self) -> list[PlatformType]:
        """List available platforms."""
        return list(self.platforms.keys())
    
    async def generate_and_publish(
        self,
        platform: PlatformType,
        content_type: ContentType,
        text: str,
        persona: str = "default",
        media_url: Optional[str] = None,
    ) -> PublishingResult:
        """Generate and publish content to a platform."""
        if platform not in self.platforms:
            return PublishingResult(
                success=False,
                platform=platform,
                error=f"Platform not initialized: {platform.value}"
            )
        
        content = ContentItem(
            text=text,
            content_type=content_type,
            platform=platform,
            persona=persona,
            media_url=media_url,
        )
        
        return await self.platforms[platform].publish(content)
    
    async def publish_to_all(
        self,
        content_type: ContentType,
        text: str,
        persona: str = "default",
    ) -> dict[PlatformType, PublishingResult]:
        """Publish the same content to all platforms.
        
        Note: Each platform may adapt the content for its format.
        """
        results = {}
        
        for platform_type, platform in self.platforms.items():
            adapted_text = self._adapt_content(text, platform_type)
            content = ContentItem(
                text=adapted_text,
                content_type=content_type,
                platform=platform_type,
                persona=persona,
            )
            
            result = await platform.publish(content)
            results[platform_type] = result
        
        return results
    
    def _adapt_content(self, text: str, platform: PlatformType) -> str:
        """Adapt content for a specific platform."""
        if platform == PlatformType.TWITTER:
            return text[:280]
        elif platform == PlatformType.LINKEDIN:
            return text
        else:
            return text
    
    def get_personas(self, platform: PlatformType) -> list[str]:
        """Get available personas for a platform."""
        if platform in self.platforms:
            return self.platforms[platform].get_personas()
        return []
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        PlatformLoader.reload(PlatformType.FACEBOOK)
        PlatformLoader.reload(PlatformType.LINKEDIN)
        PlatformLoader.reload(PlatformType.TWITTER)


# Convenience functions

async def create_orchestrator() -> ContentOrchestrator:
    """Create and initialize an orchestrator."""
    config = OrchestratorConfig.from_env()
    orchestrator = ContentOrchestrator(config)
    await orchestrator.initialize()
    return orchestrator


async def quick_publish(
    platform: str,
    content_type: str,
    text: str,
) -> PublishingResult:
    """Quick publish helper.
    
    Usage:
        result = await quick_publish("facebook", "post", "Hello world!")
    """
    platform_type = PlatformType(platform.lower())
    content_type_enum = ContentType(content_type.lower())
    
    orchestrator = await create_orchestrator()
    return await orchestrator.generate_and_publish(
        platform_type, content_type_enum, text
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python orchestrator.py <platform> <content_type> [text...]")
        print("  platform:     facebook | linkedin | twitter")
        print("  content_type: post | reel | story")
        sys.exit(1)

    platform = sys.argv[1]
    content_type = sys.argv[2]
    text = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""

    async def _main():
        return await quick_publish(platform, content_type, text)

    result = asyncio.run(_main())
    print(result)