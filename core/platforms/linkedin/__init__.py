"""LinkedIn platform plugin for Content Machine.

This plugin wraps the existing machines/linkedin-machine functionality.
Includes the carousel PDF generation feature.
"""

from core.shared.base import (
    PlatformType,
    ContentType,
    ContentItem,
    PublishingResult,
    BasePlatform,
    PlatformRegistry,
)
import os
import json
from pathlib import Path
from typing import Optional
import asyncio


def register():
    """Register the LinkedIn platform."""
    PlatformRegistry.register(PlatformType.LINKEDIN)(LinkedInPlatform)


class LinkedInPlatform(BasePlatform):
    """LinkedIn platform implementation.
    
    Wraps the existing linkedin-machine with carousel PDF generator.
    """
    
    platform_type = PlatformType.LINKEDIN
    
    def __init__(self, config: dict):
        self.base_dir = config.get("base_dir", "machines/linkedin_machine")
        self.config = config
        super().__init__(config)
    
    def _validate_config(self) -> None:
        """Validate required LinkedIn configuration."""
        required = ["access_token"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
        
        if not Path(self.base_dir).exists():
            raise FileNotFoundError(f"LinkedIn base dir not found: {self.base_dir}")
    
    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.POST,
            ContentType.CAROUSEL,
        ]
    
    async def publish(self, content: ContentItem) -> PublishingResult:
        """Publish content to LinkedIn."""
        if content.content_type == ContentType.POST:
            return await self._publish_post(content)
        elif content.content_type == ContentType.CAROUSEL:
            return await self._publish_carousel(content)
        else:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=f"Unsupported content type: {content.content_type}"
            )
    
    async def _publish_post(self, content: ContentItem) -> PublishingResult:
        """Publish a text post with optional image."""
        import requests
        
        token = self.config["access_token"]
        
        try:
            url = "https://api.linkedin.com/v2/ugcPosts"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            }
            
            data = {
                "author": f"urn:li:person:{self.config.get('person_urn', 'me')}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content.text},
                        "shareMediaCategory": "IMAGE" if content.media_url else "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                }
            }
            
            if content.media_url:
                data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
                    "media": content.media_url
                }]
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            result = response.json()
            
            if response.status_code in [200, 201]:
                post_id = result.get("id", result.get("serviceProviderPostId", ""))
                return PublishingResult(
                    success=True,
                    platform=self.platform_type,
                    post_id=post_id,
                    url=f"https://www.linkedin.com/feed/update/{post_id}"
                )
            else:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error=result.get("message", "Unknown error")
                )
                
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    async def _publish_carousel(self, content: ContentItem) -> PublishingResult:
        """Publish a carousel post to LinkedIn.
        
        Uses the existing carousel generator from linkedin-machine.
        """
        try:
            carousel_content = content.metadata.get("slides", [])
            
            if not carousel_content:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error="No slides provided for carousel"
                )
            
            pdf_url = await self._generate_carousel_pdf(carousel_content, content.metadata)
            
            if not pdf_url:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error="Failed to generate carousel PDF"
                )
            
            return await self._publish_post(ContentItem(
                text=content.text,
                content_type=ContentType.POST,
                platform=content.platform,
                persona=content.persona,
                media_url=pdf_url,
                metadata=content.metadata
            ))
            
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    async def _generate_carousel_pdf(self, slides: list[dict], metadata: dict) -> Optional[str]:
        """Generate a carousel PDF using the remotion engine.
        
        Returns a URL to the generated PDF or image.
        """
        try:
            carousel_path = Path(self.base_dir) / "generate_carousel.py"
            
            if carousel_path.exists():
                import sys
                sys.path.insert(0, str(Path(self.base_dir)))
                from generate_carousel import generate_carousel
                
                result = await asyncio.wait_for(
                    generate_carousel(slides, metadata),
                    timeout=300
                )
                return result.get("url")
            
            return None
            
        except Exception as e:
            print(f"Carousel generation error: {e}")
            return None
    
    async def get_post(self, post_id: str) -> Optional[ContentItem]:
        """Retrieve a post by ID."""
        # LinkedIn API implementation
        return None
    
    async def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID."""
        # LinkedIn API implementation
        return False
    
    # Platform-specific methods
    
    def get_personas(self) -> list[str]:
        """Get available personas for LinkedIn."""
        for dir_name in ["persona", "personas"]:
            persona_dir = Path(self.base_dir) / dir_name
            
            if persona_dir.exists():
                personas = []
                for entry in os.listdir(persona_dir):
                    if entry.startswith("_"):
                        continue
                    if (persona_dir / entry).is_dir():
                        personas.append(entry)
                return personas
        
        return []
    
    def get_persona_config(self, persona_name: str) -> dict:
        """Load persona configuration."""
        for dir_name in ["persona", "personas"]:
            persona_dir = Path(self.base_dir) / dir_name
            
            config_file = persona_dir / persona_name / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    return json.load(f)
        
        return {}
    
    def get_carousel_template(self, template_name: str) -> dict:
        """Load a carousel template."""
        templates_dir = Path(self.base_dir) / "templates"
        
        if not templates_dir.exists():
            return {}
        
        template_file = templates_dir / f"{template_name}.json"
        if template_file.exists():
            with open(template_file) as f:
                return json.load(f)
        
        return {}