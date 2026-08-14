# agent_publisher.py — Publication sur LinkedIn via API v2
import sys
import os
import sqlite3 as _sqlite3
import json
import logging
import requests
from pathlib import Path

logger = logging.getLogger("linkedin_publisher")

# Derniere erreur publique (pour dashboard)
LAST_ERROR = ""

# Nombre max d'images supporté par LinkedIn
LI_MAX_IMAGES = 9
# Extensions d'image acceptées par LinkedIn
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def get_linkedin_credentials(account_id: int = None):
    """
    Recupere les credentials LinkedIn dynamiquement depuis la DB.
    Essaie d'abord la DB LinkedIn, puis la DB Facebook, puis fallback .env.
    """
    # 1. Essayer la DB LinkedIn machine
    try:
        try:
            from core.paths import PLATFORM_DB
            db_path = PLATFORM_DB.get("linkedin")
        except ImportError:
            db_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "leads_station.db")
        conn = _sqlite3.connect(db_path)
        conn.row_factory = _sqlite3.Row
        if account_id:
            row = conn.execute("SELECT id,name,credentials FROM accounts WHERE id=? AND platform='linkedin' AND status='active'", (account_id,)).fetchone()
        else:
            row = conn.execute("SELECT id,name,credentials FROM accounts WHERE platform='linkedin' AND status='active'").fetchone()
        conn.close()

        if row and row["credentials"]:
            creds = json.loads(row["credentials"])
            token = creds.get("linkedin_token") or creds.get("access_token")
            user_id = creds.get("linkedin_user_id") or creds.get("user_id")
            if token and user_id:
                logger.info(f"[linkedin] Token from DB LinkedIn id={row['id']} name={row['name']}")
                return token, user_id
    except Exception as e:
        logger.warning(f"[linkedin] DB LinkedIn error: {e}")

    # 2. Essayer la DB Facebook machine (fallback)
    try:
        _fb_machine = str(Path(__file__).resolve().parent.parent.parent.parent / "machines" / "facebook_machine")
        if _fb_machine not in sys.path:
            sys.path.insert(0, _fb_machine)
        from core.db import SessionLocal, Account

        db = SessionLocal()
        try:
            if account_id:
                account = db.query(Account).filter(
                    Account.id == account_id,
                    Account.platform == "linkedin",
                    Account.status == "active"
                ).first()
            else:
                account = db.query(Account).filter(
                    Account.platform == "linkedin",
                    Account.status == "active"
                ).first()

            if account:
                creds = account.credentials or {}
                token = creds.get("linkedin_token") or creds.get("access_token")
                user_id = creds.get("linkedin_user_id") or creds.get("user_id")

                if token and user_id:
                    logger.info(f"[linkedin] Token from core DB id={account.id} name={account.name}")
                    return token, user_id

            logger.warning("[linkedin] DB credentials incomplete, falling back to .env")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[linkedin] Core DB error: {e}, falling back to .env")

    # 3. Fallback: variables d'environnement .env
    try:
        from dotenv import load_dotenv
        li_env = Path(__file__).resolve().parent.parent / ".env"
        if li_env.exists():
            load_dotenv(li_env)
        token = os.getenv("LINKEDIN_TOKEN", "")
        user_id = os.getenv("LINKEDIN_USER_ID", "")
        if token and user_id:
            logger.info("[linkedin] Token loaded from .env")
            return token, user_id
    except Exception as e:
        logger.warning(f"[linkedin] .env fallback error: {e}")

    logger.error("[linkedin] No credentials found (DB + .env)")
    return None, None


def _resolve_image_files(path: Path) -> list:
    """Retourne la liste des images du dossier sous forme de dicts:
    {"path": Path|None, "url": str|None, "name": str}.
    Sources : 1. meta['images'] (multi), 2. post_image.*/image.*, 3. sous-dossier
    images/, 4. meta['image_url'] distant (fallback)."""
    images = []
    meta = {}
    try:
        meta_path = path / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[linkedin] meta.json parse error: {e}")

    # 1. meta.json -> images array (multi-image)
    arr = meta.get("images")
    if isinstance(arr, list) and arr:
        for item in arr:
            filename = item.get("filename") if isinstance(item, dict) else None
            url = item.get("url") if isinstance(item, dict) else None
            name = filename or ""
            f = path / filename if filename else None
            if f and f.exists() and f.suffix.lower() in _IMAGE_EXTS:
                images.append({"path": f, "url": None, "name": name})
            elif url:
                images.append({"path": None, "url": url, "name": name})
        if images:
            return images[:LI_MAX_IMAGES]

    # 2. Fichiers post_image.* / image.*
    for name in ["post_image.jpg", "post_image.jpeg", "post_image.png",
                 "image.jpg", "image.jpeg", "image.png"]:
        f = path / name
        if f.exists():
            images.append({"path": f, "url": None, "name": name})
            break

    # 3. Sous-dossier images/
    if not images:
        sub = path / "images"
        if sub.is_dir():
            for f in sorted(sub.iterdir()):
                if f.suffix.lower() in _IMAGE_EXTS:
                    images.append({"path": f, "url": None, "name": f.name})
                    if len(images) >= LI_MAX_IMAGES:
                        break

    # 4. Fallback distant image_url
    if not images and meta.get("image_url"):
        images.append({"path": None, "url": meta.get("image_url"), "name": "remote_image"})

    return images[:LI_MAX_IMAGES]


def _read_image_bytes(item: dict) -> bytes:
    """Retourne le binaire d'une image : fichier local, sinon téléchargé (url)."""
    p = item.get("path")
    if p and p.is_file():
        b = p.read_bytes()
        if b:
            return b
    url = item.get("url")
    if url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content
    return b""


def _register_and_upload(token: str, user_id: str, image_bytes: bytes):
    """registerUpload + upload binaire. Retourne l'asset URN LinkedIn."""
    url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": f"urn:li:person:{user_id}",
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise Exception(f"registerUpload HTTP {r.status_code}: {r.text[:200]}")

    upload_data = r.json()
    upload_url = upload_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset_urn = upload_data["value"]["asset"]

    up_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }
    ur = requests.put(upload_url, headers=up_headers, data=image_bytes, timeout=60)
    if ur.status_code not in (200, 201, 204):
        raise Exception(f"Upload image HTTP {ur.status_code}: {ur.text[:200]}")

    return asset_urn


def _publish_text(token: str, user_id: str, post_text: str) -> bool:
    """Publie un post texte seul (shareMediaCategory NONE)."""
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "author": f"urn:li:person:{user_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code in [200, 201]:
        logger.info("[linkedin] Publication texte-only successful")
        return True

    error_text = response.text
    logger.error(f"LinkedIn error {response.status_code}: {error_text}")
    if response.status_code == 401:
        if "EXPIRED_ACCESS_TOKEN" in error_text:
            LAST_ERROR = "TOKEN EXPIRED - Regenerez votre token LinkedIn"
        elif "INVALID_ACCESS_TOKEN" in error_text:
            LAST_ERROR = "TOKEN INVALIDE - Verifiez le token LinkedIn"
        else:
            LAST_ERROR = f"AUTH FAILED (401) - {error_text[:200]}"
    elif response.status_code == 422:
        if "DUPLICATE_POST" in error_text:
            LAST_ERROR = "POST DUPLIQUE - Ce contenu a deja ete publie"
        else:
            LAST_ERROR = f"VALIDATION (422) - {error_text[:200]}"
    elif response.status_code == 403:
        LAST_ERROR = "ACCES REFUSE (403) - Verifiez les permissions LinkedIn"
    else:
        LAST_ERROR = f"ERREUR {response.status_code} - {error_text[:200]}"
    return False


def _publish_with_images(token: str, user_id: str, post_text: str, image_files: list) -> bool:
    """Publie un post LinkedIn avec N images (shareMediaCategory IMAGE)."""
    media_uris = []
    for item in image_files:
        image_bytes = _read_image_bytes(item)
        if not image_bytes:
            raise Exception(f"Image vide ou introuvable: {item['name']}")
        asset_urn = _register_and_upload(token, user_id, image_bytes)
        media_uris.append(asset_urn)

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    media = [{"status": "READY", "media": urn} for urn in media_uris]
    payload = {
        "author": f"urn:li:person:{user_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "IMAGE",
                "media": media,
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code in [200, 201]:
        logger.info(f"[linkedin] {len(media_uris)} image(s) published successfully")
        return True

    error_text = response.text
    logger.error(f"LinkedIn error {response.status_code}: {error_text}")
    return False


def post_linkedin(folder, account_id: int = None, credentials: dict = None, force_text_only: bool = False):
    """
    Publie le contenu du dossier specifie sur LinkedIn.
    Gère les images (multi) via registerUpload + upload binaire.

    Retourne:
      - True                        : publié avec succès (texte avec ou sans image)
      - False                       : échec, texte non publié
      - {"needs_confirmation": True,
         "reason": str}             : images non attachées, demande confirmation
    """
    global LAST_ERROR
    LAST_ERROR = ""
    try:
        path = Path(folder)
        possible_files = ["linkedin_post.txt", "facebook_post.txt", "post.txt", "content.txt"]
        post_file = None

        for name in possible_files:
            if (path / name).exists():
                post_file = path / name
                break

        if not post_file:
            LAST_ERROR = f"No post file in {folder}"
            logger.error(f"No post file in {folder}")
            return False

        post_text = post_file.read_text(encoding="utf-8")
        logger.info(f"[linkedin] Post length: {len(post_text)} chars")

        # Credentials fournis ou récupérés depuis DB/.env
        token, user_id = None, None
        if credentials:
            token = credentials.get("linkedin_token") or credentials.get("access_token")
            user_id = credentials.get("linkedin_user_id") or credentials.get("user_id")

        if not token or not user_id:
            logger.info("[linkedin] Credentials incomplete, trying DB then .env...")
            token, user_id = get_linkedin_credentials(account_id)

        if not token or not user_id:
            LAST_ERROR = "No LinkedIn credentials found (DB + .env)"
            logger.error(f"Missing credentials for account_id={account_id}")
            return False

        logger.info(f"[linkedin] Using user_id={user_id}, token_len={len(token)}")

        # Détection des images
        image_files = _resolve_image_files(path)

        if force_text_only:
            logger.info("[linkedin] force_text_only => publication texte seule")
            return _publish_text(token, user_id, post_text)

        if not image_files:
            logger.info("[linkedin] Aucune image trouvée => publication texte seule")
            return _publish_text(token, user_id, post_text)

        # Tentative de publication avec images
        try:
            return _publish_with_images(token, user_id, post_text, image_files)
        except Exception as e:
            reason = str(e)
            logger.warning(f"[linkedin] Publication image échouée: {reason}")
            LAST_ERROR = reason
            return {"needs_confirmation": True, "reason": reason}

    except Exception as e:
        LAST_ERROR = str(e)
        logger.exception(f"Fatal error in LinkedIn publisher: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        aid = int(sys.argv[2]) if len(sys.argv) > 2 else None
        post_linkedin(sys.argv[1], account_id=aid)
    else:
        print("Usage: python agent_publisher.py <folder_path> [account_id]")