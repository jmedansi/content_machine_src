"""
core/routes/api_helpers.py — Fonctions utilitaires partagées pour les routes API V5
"""

import json
from pathlib import Path
from typing import Optional

from core.config import Config

DATA_DIR    = Config.DATA_DIR
CONTENT_DIR = Config.CONTENT_DIR

_TEXT_FILES  = ["facebook_post.txt", "post.txt", "content.txt"]
_IMAGE_FILES = ["post_image.jpg", "post_image.webp", "image.jpg", "image.webp", "image.png"]
_REEL_FILES  = ["reel/reel.mp4", "reel/video.mp4", "video.mp4"]

DEFAULT_SCHEDULE = [
    {"time": "08:00", "persona": "ia_design",          "type": "post"},
    {"time": "10:30", "persona": "post_court",         "type": "post"},
    {"time": "12:30", "persona": "mini_formation",     "type": "post"},
    {"time": "14:00", "persona": "storytelling_pro",   "type": "post"},
    {"time": "16:30", "persona": "ia_integration",     "type": "post"},
    {"time": "19:00", "persona": "business_auto",      "type": "post"},
    {"time": "20:30", "persona": "cta",                "type": "post"}
]

SCHEDULE = []

def load_schedule():
    global SCHEDULE
    schedule_file = DATA_DIR / "schedule.json"
    if schedule_file.exists():
        try:
            SCHEDULE = json.loads(schedule_file.read_text(encoding="utf-8"))
            return
        except Exception:
            pass
    SCHEDULE = DEFAULT_SCHEDULE.copy()
    save_schedule()

def save_schedule():
    schedule_file = DATA_DIR / "schedule.json"
    schedule_file.write_text(json.dumps(SCHEDULE, indent=2, ensure_ascii=False), encoding="utf-8")

load_schedule()

def _load_ai_responses_config() -> dict:
    f = DATA_DIR / "ai_responses.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": False}

def _find_file(folder: Path, candidates: list) -> Optional[Path]:
    for name in candidates:
        p = folder / name
        if p.exists():
            return p
        for subdir in folder.iterdir():
            if subdir.is_dir():
                p2 = subdir / name
                if p2.exists():
                    return p2
    return None

def _list_post_folders():
    if not CONTENT_DIR.exists():
        return []
    return sorted(
        [d for d in CONTENT_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )

def _read_post(folder: Path) -> dict:
    meta_file  = folder / "meta.json"
    text_file  = _find_file(folder, _TEXT_FILES)
    image_file = _find_file(folder, _IMAGE_FILES)
    reel_file  = _find_file(folder, _REEL_FILES)

    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    text = ""
    if text_file:
        try:
            text = text_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return {
        "folder":           folder.name,
        "persona":          meta.get("persona", "?"),
        "topic":            meta.get("topic", ""),
        "scheduled_time":   meta.get("scheduled_time", ""),
        "status":           meta.get("status", "draft"),
        "published":        meta.get("status") == "published" or meta.get("published", False),
        "word_count":       len(text.split()) if text else 0,
        "preview":          text[:200] if text else "(sans texte)",
        "has_image":        image_file is not None,
        "image_filename":   image_file.name if image_file else None,
        "has_reel":         reel_file is not None,
        "reel_filename":    reel_file.name if reel_file else None,
        "created_at":       meta.get("created_at", ""),
        "llm_provider":     meta.get("llm_provider", ""),
    }

def _save_meta(folder: Path, updates: dict):
    meta_file = folder / "meta.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta.update(updates)
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

def _generate_folder_name(persona: str) -> str:
    from datetime import datetime
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    return f"{date_str}_{persona}_{time_str}"

def _resolve_account_id(account_id) -> Optional[int]:
    if account_id is None:
        return None
    try:
        return int(account_id)
    except (TypeError, ValueError):
        return None


def _get_platform_dir(platform: str) -> Path:
    """Résout le répertoire racine d'une plateforme."""
    platform_key = (platform or "facebook").lower()
    base_dir = Config.BASE_DIR
    bases = {
        "facebook": base_dir,
        "instagram": base_dir,
        "linkedin": base_dir / "machines" / "linkedin_machine",
        "twitter":  base_dir / "machines" / "twitter_machine",
    }
    return bases.get(platform_key, base_dir)


def _get_content_dir(platform: str, account_id: int = None) -> Path:
    """Résout le répertoire de contenu pour une plateforme / un compte."""
    platform_dir = _get_platform_dir(platform)
    if account_id:
        # Canonical layout: machines/<platform>_machine/accounts/<id>/content
        return platform_dir / "accounts" / str(account_id) / "content"
    return platform_dir / "content"


def _get_folder_path(platform: str, folder_name: str, account_id: int = None) -> Path:
    """Résout le dossier de contenu pour un post donné."""
    return _get_content_dir(platform, account_id) / folder_name


def _list_folders(content_dir: Path) -> list:
    """Liste les dossiers de contenu triés par date."""
    if not content_dir.exists():
        return []
    return sorted(
        [d for d in content_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )

def _get_pending_posts(platform_dir: Path) -> list:
    """Récupère les posts en attente pour une plateforme donnée."""
    content_dir = platform_dir / "content"
    if not content_dir.exists():
        return []
    
    posts = []
    for folder in content_dir.iterdir():
        if folder.is_dir():
            post = _read_post(folder)
            if post["status"] == "pending":
                posts.append(post)
    return posts

def _get_accounts(platform: str) -> list:
    """Récupère les comptes pour une plateforme via la DB."""
    try:
        from core.db import SessionLocal, Account
        db = SessionLocal()
        accounts = db.query(Account).filter(Account.platform == platform).all()
        result = [
            {
                "id": acc.id,
                "name": acc.name,
                "status": acc.status
            } for acc in accounts
        ]
        db.close()
        return result
    except Exception:
        return []