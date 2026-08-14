"""Twitter/X platform plugin for Content Machine."""

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
    """Register the Twitter platform."""
    PlatformRegistry.register(PlatformType.TWITTER)(TwitterPlatform)


class TwitterPlatform(BasePlatform):
    """Twitter/X platform implementation.
    
    Supports:
    - Tweets (text posts)
    - Threads (multi-tweet posts)
    - Replies
    """
    
    platform_type = PlatformType.TWITTER
    
    def __init__(self, config: dict):
        self.config = config
        super().__init__(config)
    
    def _validate_config(self) -> None:
        """Validate required Twitter configuration."""
        required = ["api_key", "api_secret", "access_token", "access_token_secret"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"Missing required config: {missing}")
    
    @property
    def supported_content_types(self) -> list[ContentType]:
        return [
            ContentType.POST,
            ContentType.THREAD,
        ]
    
    async def publish(self, content: ContentItem) -> PublishingResult:
        """Publish content to Twitter."""
        if content.content_type == ContentType.POST:
            return await self._publish_tweet(content)
        elif content.content_type == ContentType.THREAD:
            return await self._publish_thread(content)
        else:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=f"Unsupported content type: {content.content_type}"
            )
    
    async def _publish_tweet(self, content: ContentItem) -> PublishingResult:
        """Publish a single tweet."""
        try:
            import requests
            
            api_key = self.config["api_key"]
            api_secret = self.config["api_secret"]
            access_token = self.config["access_token"]
            access_token_secret = self.config["access_token_secret"]
            
            # Using OAuth 1.0a - simplified implementation
            # In production, use a proper OAuth library like Tweepy
            url = "https://api.twitter.com/2/tweets"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            data = {"text": content.text[:280]}  # Enforce character limit
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            result = response.json()
            
            if "data" in result:
                tweet_id = result["data"]["id"]
                return PublishingResult(
                    success=True,
                    platform=self.platform_type,
                    post_id=tweet_id,
                    url=f"https://twitter.com/user/status/{tweet_id}"
                )
            else:
                error_msg = result.get("detail", result.get("title", "Unknown error"))
                return PublishingResult(
                    success=False,
                    platform=self.platform_type,
                    error=error_msg
                )
                
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    async def _publish_thread(self, content: ContentItem) -> PublishingResult:
        """Publish a thread (series of connected tweets)."""
        tweets = content.metadata.get("tweets", [])
        
        if not tweets:
            tweets = self._split_into_tweets(content.text)
        
        if not tweets:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error="No tweets provided for thread"
            )
        
        try:
            import requests
            
            api_key = self.config["api_key"]
            access_token = self.config["access_token"]
            
            url = "https://api.twitter.com/2/tweets"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            previous_tweet_id = None
            thread_ids = []
            
            for i, tweet_text in enumerate(tweets):
                data = {"text": tweet_text[:280]}
                
                if previous_tweet_id:
                    data["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}
                
                response = requests.post(url, json=data, headers=headers, timeout=30)
                result = response.json()
                
                if "data" not in result:
                    return PublishingResult(
                        success=False,
                        platform=self.platform_type,
                        error=f"Failed to post tweet {i+1}: {result}"
                    )
                
                tweet_id = result["data"]["id"]
                thread_ids.append(tweet_id)
                previous_tweet_id = tweet_id
            
            return PublishingResult(
                success=True,
                platform=self.platform_type,
                post_id=thread_ids[0],  # First tweet ID
                url=f"https://twitter.com/user/status/{thread_ids[0]}",
                metadata={"thread_ids": thread_ids}
            )
            
        except Exception as e:
            return PublishingResult(
                success=False,
                platform=self.platform_type,
                error=str(e)
            )
    
    def _split_into_tweets(self, text: str) -> list[str]:
        """Split long text into tweet-sized chunks."""
        tweets = []
        lines = text.split("\n")
        current = ""
        
        for line in lines:
            if len(current) + len(line) + 1 <= 270:
                current += ("\n" if current else "") + line
            else:
                if current:
                    tweets.append(current)
                    current = line
                else:
                    tweets.append(line[:270])
                    line = line[270:]
        
        if current:
            tweets.append(current)
        
        return tweets[:25]  # Max 25 tweets per thread
    
    async def get_post(self, post_id: str) -> Optional[ContentItem]:
        """Retrieve a post by ID."""
        try:
            import requests
            
            access_token = self.config["access_token"]
            url = f"https://api.twitter.com/2/tweets/{post_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()
            
            if "data" in data:
                return ContentItem(
                    text=data["data"]["text"],
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
        try:
            import requests
            
            access_token = self.config["access_token"]
            url = f"https://api.twitter.com/2/tweets/{post_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            response = requests.delete(url, headers=headers, timeout=30)
            return response.status_code in [200, 202]
            
        except Exception:
            return False
    
    # Platform-specific methods
    
    def get_personas(self) -> list[str]:
        """Get available personas for Twitter."""
        personas_dir = Path("machines/twitter-machine/personas")
        
        if not personas_dir.exists():
            return []
        
        personas = []
        for entry in os.listdir(personas_dir):
            if entry.startswith("_"):
                continue
            if (personas_dir / entry).is_dir():
                personas.append(entry)
        
        return ["hot_take", "thread_maker", "meme_lord"]
    
    def get_persona_config(self, persona_name: str) -> dict:
        """Load persona configuration."""
        configs = {
            "hot_take": {
                "name": "Hot Take",
                "max_length": 280,
                "tone": "bold",
            },
            "thread_maker": {
                "name": "Thread Maker",
                "max_tweets": 25,
                "tone": "educational",
            },
            "meme_lord": {
                "name": "Meme Lord",
                "max_length": 280,
                "tone": "humorous",
            }
        }
        return configs.get(persona_name, {})