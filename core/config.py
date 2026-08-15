import os
from pathlib import Path

# Chargement du fichier .env parent
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

class Config:
    # --- Generation Models ---
    # Clés de repli (source primaire : accounts.settings via le dashboard)
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
    KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
    MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "llama-3.3-70b-versatile")
    FACEBOOK_LLM_MODEL = os.getenv("FACEBOOK_LLM_MODEL", DEFAULT_LLM_MODEL)
    LINKEDIN_LLM_MODEL = os.getenv("LINKEDIN_LLM_MODEL", DEFAULT_LLM_MODEL)
    TWITTER_LLM_MODEL = os.getenv("TWITTER_LLM_MODEL", DEFAULT_LLM_MODEL)
    HF_TOKEN = os.getenv("HF_TOKEN", "")
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
    POST_IMAGE_ENABLED = os.getenv("POST_IMAGE_ENABLED", "true").lower() == "true"
    POST_IMAGE_STYLE = os.getenv("POST_IMAGE_STYLE", "cartoon")
    
    # --- FB Graph API ---
    FB_APP_ID = os.getenv("FB_APP_ID", "")
    FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")
    FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
    FB_VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN", "")
    IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID", "")
    INSTAGRAM_MAX_CAPTION_CHARS = int(os.getenv("INSTAGRAM_MAX_CAPTION_CHARS", "2200"))
    INSTAGRAM_MAX_CAPTION_CHARS = int(os.getenv("INSTAGRAM_MAX_CAPTION_CHARS", "2200"))
    
    # --- Telegram Notifications ---
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # --- Misc Automations ---
    BATCH_MIN_DELAY_SECONDS = int(os.getenv("BATCH_MIN_DELAY_SECONDS", "70"))
    CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")
    GROUPS_PER_DAY = int(os.getenv("GROUPS_PER_DAY", "3"))
    GROUPS_MIN_DELAY_SECONDS = int(os.getenv("GROUPS_MIN_DELAY_SECONDS", "1800"))
    AI_RESPONSES_ENABLED = os.getenv("AI_RESPONSES_ENABLED", "false").lower() == "true"
    MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")
    
    # --- Dashboard Auth ---
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
    
    # --- Paths ---
    BASE_DIR = Path(__file__).resolve().parent.parent
    CONTENT_DIR = BASE_DIR / "content"
    DATA_DIR = BASE_DIR / "data"
    PERSONAS_DIR = BASE_DIR / "persona"

    @classmethod
    def validate_node_deps(cls, node_name: str, required_keys: list):
        missing = [k for k in required_keys if not getattr(cls, k, None)]
        if missing:
            return False, f"Missing config variables for node '{node_name}': {', '.join(missing)}"
        return True, "OK"
