"""
Module partagé pour l'upload d'images vers GitHub.
Utilisé par : image_creator (gemini_engine), publisher, dashboard (replace_image).
"""
import os
import base64
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Import centralized config
import sys as _sys
_core_dir = str(Path(__file__).resolve().parent.parent)
if _core_dir not in _sys.path:
    _sys.path.insert(0, _core_dir)

from core.paths import (
    GITHUB_REPO, GITHUB_BRANCH,
    GITHUB_MAX_RETRIES, GITHUB_RETRY_DELAY, GITHUB_UPLOAD_TIMEOUT,
    MIN_IMAGE_SIZE, MAX_UPLOAD_SIZE,
)

GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def _get_headers():
    """Return fresh headers with current token."""
    if not GITHUB_TOKEN:
        return {}
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }


def upload_image_to_github(file_path: Path, prefix: str = "post") -> dict:
    """
    Upload une image locale vers GitHub et retourne l'URL publique.

    Args:
        file_path: chemin local de l'image
        prefix: préfixe pour le nom de fichier (ex: 'post', 'manual', 'replace')

    Returns:
        {"success": True, "url": "https://raw.githubusercontent.com/...", "filename": "..."}
        ou {"success": False, "error": "..."}
    """
    if not file_path.exists():
        return {"success": False, "error": f"Fichier introuvable: {file_path}"}

    if not GITHUB_TOKEN:
        return {"success": False, "error": "GITHUB_TOKEN manquant dans .env"}

    ext = file_path.suffix.lower() or ".jpg"
    uid = uuid.uuid4().hex[:8]
    fn = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uid}{ext}"

    try:
        img_data = file_path.read_bytes()
        if len(img_data) < MIN_IMAGE_SIZE:
            return {"success": False, "error": "Fichier trop petit, probablement invalide"}
        if len(img_data) > MAX_UPLOAD_SIZE:
            return {"success": False, "error": f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE // (1024*1024)}MB)"}

        b64 = base64.b64encode(img_data).decode("utf-8")
        headers = _get_headers()

        for attempt in range(1, GITHUB_MAX_RETRIES + 1):
            try:
                r = __import__("requests").put(
                    f"{GITHUB_API_URL}/{fn}",
                    headers=headers,
                    json={
                        "message": f"Upload {fn}",
                        "content": b64,
                        "branch": GITHUB_BRANCH
                    },
                    timeout=GITHUB_UPLOAD_TIMEOUT
                )
                if r.status_code in (200, 201):
                    url = f"{RAW_BASE_URL}/{fn}"
                    logger.info(f"[github_upload] Uploadé: {fn} -> {url}")
                    return {"success": True, "url": url, "filename": fn}
                else:
                    logger.warning(f"[github_upload] Tentative {attempt}/{GITHUB_MAX_RETRIES} échouée: HTTP {r.status_code}")
            except Exception as e:
                logger.warning(f"[github_upload] Tentative {attempt}/{GITHUB_MAX_RETRIES} erreur: {e}")

            if attempt < GITHUB_MAX_RETRIES:
                time.sleep(GITHUB_RETRY_DELAY)

        return {"success": False, "error": f"Échec après {GITHUB_MAX_RETRIES} tentatives"}

    except Exception as e:
        logger.error(f"[github_upload] Exception: {e}")
        return {"success": False, "error": str(e)}


def resolve_image_url(local_path: Path, current_meta: dict = None, prefix: str = "post") -> str:
    """
    Résout l'URL publique d'une image pour la publication.
    1. Upload le fichier local vers GitHub si disponible
    2. Sinon, retourne l'URL existante si elle est valide
    3. Si échec, retourne None

    Args:
        local_path: chemin du fichier image local
        current_meta: dict meta.json du post (optionnel)
        prefix: préfixe pour le nom de fichier GitHub

    Returns:
        URL string ou None
    """
    meta = current_meta or {}

    existing_url = meta.get("image_url", "")

    # 1. Upload le fichier local si disponible (prioritaire sur le cache)
    if local_path and local_path.exists():
        result = upload_image_to_github(local_path, prefix=prefix)
        if result["success"]:
            return result["url"]

    # 2. Fallback : ancienne URL non-GitHub valide
    if existing_url and existing_url.startswith("http"):
        logger.warning(f"[github_upload] Fallback sur ancienne URL: {existing_url}")
        return existing_url

    return None
