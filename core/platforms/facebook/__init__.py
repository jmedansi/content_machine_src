"""Facebook platform plugin for Content Machine.

This plugin wraps the existing machines/facebook-machine functionality.
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


def register():
    """Register the Facebook platform."""
    PlatformRegistry.register(PlatformType.FACEBOOK)(FacebookPlatform)


class FacebookPlatform(BasePlatform):
    """Facebook platform implementation.
    
    Wraps the existing facebook-machine agents:
    - copywriter: generates posts
    - image_creator: generates images
    - publisher: publishes to Facebook Graph API
    """
    
    platform_type = PlatformType.FACEBOOK
    
    def __init__(self, config: dict):
        self.base_dir = config.get("base_dir", "machines/facebook_machine")
        self.config = config
        super().__init__(config)
    
    def _validate_config(self) -> None:
        """Validate required Facebook configuration."""
        required = ["page_id", "access_token"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
        
        if not Path(self.base_dir).exists():
            raise FileNotFoundError(f"Facebook base dir not found: {self.base_dir}")
    
    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.POST,
            ContentType.REEL,
            ContentType.STORY,
        ]
    
    async def publish(self, content: ContentItem) -> PublishingResult:
        """Publish content to Facebook.
        
        Uses the existing publisher agent under the hood.
        """
        if content.content_type == ContentType.POST:
            return await self._publish_post(content)
        elif content.content_type == ContentType.REEL:
            return await self._publish_reel(content)
        else:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=f"Unsupported content type: {content.content_type}"
            )
    
    async def _publish_post(self, content: ContentItem) -> PublishingResult:
        """Publish a text post with optional image."""
        import requests
        
        page_id = self.config["page_id"]
        token = self.config["access_token"]
        
        try:
            if content.media_url:
                url = f"https://graph.facebook.com/v18.0/{page_id}/photos"
                data = {
                    "url": content.media_url,
                    "caption": content.text,
                    "access_token": token,
                }
            else:
                url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
                data = {
                    "message": content.text,
                    "access_token": token,
                }
            
            response = requests.post(url, data=data, timeout=30)
            result = response.json()
            
            if "id" in result:
                post_id = result["id"]
                return PublishingResult(
                    success=True,
                    platform=self.platform_type,
                    post_id=post_id,
                    url=f"https://www.facebook.com/{page_id}/posts/{post_id}"
                )
            else:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error=result.get("error", {}).get("message", "Unknown error")
                )
                
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    async def _publish_reel(self, content: ContentItem) -> PublishingResult:
        """Publish a reel (video) to Facebook."""
        # Uses the 3-phase Reels API
        # Phase 1: init -> Phase 2: upload -> Phase 3: finish
        import requests
        
        page_id = self.config["page_id"]
        token = self.config["access_token"]
        
        if not content.media_url:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error="No video URL provided"
            )
        
        try:
            # Phase 1: Start upload
            init_url = f"https://graph.facebook.com/v18.0/{page_id}/video_reels"
            init_data = {
                "upload_phase": "start",
                "access_token": token,
            }
            init_response = requests.post(init_url, data=init_data, timeout=30)
            init_result = init_response.json()
            
            if "upload_session_id" not in init_result:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error="Failed to start upload"
                )
            
            session_id = init_result["upload_session_id"]
            upload_url = init_result["upload_url"]
            
            # Phase 2: Upload video (simplified - would need binary upload)
            # For now, we'll use the simple video upload endpoint
            finish_url = f"https://graph.facebook.com/v18.0/{page_id}/video_reels"
            finish_data = {
                "upload_phase": "finish",
                "upload_session_id": session_id,
                "video_url": content.media_url,
                "access_token": token,
            }
            finish_response = requests.post(finish_url, data=finish_data, timeout=60)
            finish_result = finish_response.json()
            
            if "id" in finish_result:
                return PublishingResult(
                    success=True,
                    platform=self.platform_type,
                    post_id=finish_result["id"],
                )
            else:
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error=finish_result.get("error", {}).get("message", "Upload failed")
                )
                
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    async def get_post(self, post_id: str) -> Optional[ContentItem]:
        """Retrieve a post by ID."""
        import requests
        
        try:
            url = f"https://graph.facebook.com/v18.0/{post_id}"
            token = self.config["access_token"]
            params = {"access_token": token}
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "message" in data:
                return ContentItem(
                    text=data["message"],
                    content_type=ContentType.POST,
                    platform=self.platform_type,
                    persona="unknown",
                    metadata=data
                )
            
            return None
            
        except Exception:
            return None
    
    async def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID."""
        import requests
        
        try:
            url = f"https://graph.facebook.com/v18.0/{post_id}"
            token = self.config["access_token"]
            params = {"access_token": token}
            
            response = requests.delete(url, params=params, timeout=30)
            return response.status_code == 200
            
        except Exception:
            return False
    
    # Convenience methods for the existing agents
    
    def get_personas(self) -> list[str]:
        """Get available personas for this platform."""
        # Support both 'personas' and 'persona' directory names
        for dir_name in ["persona", "personas"]:
            personas_dir = Path(self.base_dir) / dir_name
            
            if personas_dir.exists():
                personas = []
                for entry in os.listdir(personas_dir):
                    if entry.startswith("_"):
                        continue
                    if (personas_dir / entry).is_dir():
                        personas.append(entry)
                return personas
        
        return []
    
    def get_persona_config(self, persona_name: str) -> dict:
        """Load persona configuration."""
        for dir_name in ["persona", "personas"]:
            config_file = Path(self.base_dir) / dir_name / persona_name / "config.json"
            
            if config_file.exists():
                with open(config_file) as f:
                    return json.load(f)
        
        return {}
    
    def get_persona_prompt(self, persona_name: str) -> str:
        """Load persona system prompt."""
        for dir_name in ["persona", "personas"]:
            prompt_file = Path(self.base_dir) / dir_name / persona_name / "system_prompt.md"
            
            if prompt_file.exists():
                with open(prompt_file) as f:
                    return f.read()
        
        return ""