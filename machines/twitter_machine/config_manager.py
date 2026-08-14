# config_manager.py — Configuration Twitter
import os

# Twitter API v2
TWITTER_TOKEN = os.getenv("TWITTER_TOKEN", "")
TWITTER_USER_ID = os.getenv("TWITTER_USER_ID", "")

# Groq (fallback)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

def validate_config():
    """Valide la configuration."""
    if not TWITTER_TOKEN:
        print("⚠️ TWITTER_TOKEN manquant dans .env")
        return False
    if not TWITTER_USER_ID:
        print("⚠️ TWITTER_USER_ID manquant dans .env")
        return False
    return True