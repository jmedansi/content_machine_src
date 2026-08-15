"""
Centralized path configuration for Content_Machine.
All paths, platform mappings, and shared constants live here.
"""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MACHINES_DIR = ROOT_DIR / "machines"

# Platform base directories
FB_MACHINE = MACHINES_DIR / "facebook_machine"
LI_MACHINE = MACHINES_DIR / "linkedin_machine"
TW_MACHINE = MACHINES_DIR / "twitter_machine"
IG_MACHINE = MACHINES_DIR / "instagram_machine"

PLATFORM_BASE = {
    "facebook": FB_MACHINE,
    "linkedin": LI_MACHINE,
    "twitter": TW_MACHINE,
    "instagram": IG_MACHINE,
}

# Platform database paths
PLATFORM_DB = {
    "facebook": str(MACHINES_DIR / "facebook_machine" / "data" / "leads_station.db"),
    "linkedin": str(MACHINES_DIR / "linkedin_machine" / "data" / "leads_station.db"),
    "twitter": str(MACHINES_DIR / "twitter_machine" / "data" / "leads_station.db"),
    "instagram": str(MACHINES_DIR / "instagram_machine" / "data" / "leads_station.db"),
}

VALID_PLATFORMS = set(PLATFORM_BASE.keys())

# --- GitHub upload config ---
GITHUB_REPO = os.getenv("GITHUB_REPO", "jmedansi/temp")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

# --- Facebook Graph API ---
FB_GRAPH_API_VERSION = os.getenv("FB_GRAPH_API_VERSION", "v18.0")
FB_GRAPH_API_URL = f"https://graph.facebook.com/{FB_GRAPH_API_VERSION}"

# --- LinkedIn API ---
LINKEDIN_API_URL = os.getenv("LINKEDIN_API_URL", "https://api.linkedin.com/v2/ugcPosts")

# --- Chrome debug ---
CHROME_DEBUG_PORT = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
GEMINI_MAX_WAIT = int(os.getenv("GEMINI_MAX_WAIT", "300"))

# --- Image files ---
SUPPORTED_IMAGE_FILES = ["post_image.jpg", "post_image.jpeg", "post_image.png", "post_image.webp", "image.jpg", "image.jpeg", "image.png"]
SUPPORTED_REEL_FILES = ["final_video.mp4", "reel.mp4"]
SUPPORTED_TEXT_FILES = ["facebook_post.txt", "linkedin_post.txt", "tweet.txt", "post_text.txt", "content.txt", "post.txt"]

# --- API defaults ---
API_PORT = int(os.getenv("API_PORT", "8000"))
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_TIMEOUT_SHORT = int(os.getenv("API_TIMEOUT_SHORT", "30"))
API_TIMEOUT_LONG = int(os.getenv("API_TIMEOUT_LONG", "300"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "1000"))
MAX_LOG_ENTRIES = int(os.getenv("MAX_LOG_ENTRIES", "300"))

# --- Batch / scheduling ---
BATCH_HOUR = int(os.getenv("BATCH_HOUR", "21"))
BATCH_MINUTE = int(os.getenv("BATCH_MINUTE", "0"))
AUTO_POLL_INTERVAL = int(os.getenv("AUTO_POLL_INTERVAL", "30"))
MAX_PLANNING_DAYS = int(os.getenv("MAX_PLANNING_DAYS", "31"))

# --- Reels ---
REEL_DESCRIPTION_MAX_CHARS = int(os.getenv("REEL_DESCRIPTION_MAX_CHARS", "2200"))
REEL_RETRY_DELAY = int(os.getenv("REEL_RETRY_DELAY", "10"))

# --- Comments ---
COMMENT_INITIAL_DELAY = int(os.getenv("COMMENT_INITIAL_DELAY", "3"))
COMMENT_DELAY = int(os.getenv("COMMENT_DELAY", "2"))

# --- LinkedIn ---
LINKEDIN_MAX_CHARS = int(os.getenv("LINKEDIN_MAX_CHARS", "3000"))

# --- GitHub upload ---
GITHUB_MAX_RETRIES = int(os.getenv("GITHUB_MAX_RETRIES", "2"))
GITHUB_RETRY_DELAY = int(os.getenv("GITHUB_RETRY_DELAY", "3"))
GITHUB_UPLOAD_TIMEOUT = int(os.getenv("GITHUB_UPLOAD_TIMEOUT", "30"))
MIN_IMAGE_SIZE = int(os.getenv("MIN_IMAGE_SIZE", "100"))
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))  # 10MB
