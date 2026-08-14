# agent.py — Publication sur Facebook via Graph API ou Make.com
import sys
import os
import time
import requests
import json
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger
from core.github_upload import resolve_image_url
from core.paths import (
    FB_GRAPH_API_URL, LINKEDIN_API_URL, LI_MACHINE,
    API_TIMEOUT_SHORT, API_TIMEOUT_LONG,
    REEL_DESCRIPTION_MAX_CHARS, REEL_RETRY_DELAY,
    COMMENT_INITIAL_DELAY, COMMENT_DELAY, LINKEDIN_MAX_CHARS,
)

logger = get_node_logger("publisher")

GRAPH_API_URL = FB_GRAPH_API_URL

def load_post_resources():
    res_file = Config.DATA_DIR / "post_resources.json"
    if res_file.exists():
        return json.loads(res_file.read_text(encoding="utf-8"))
    return {}

def save_post_resources(data):
    res_file = Config.DATA_DIR / "post_resources.json"
    res_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def get_account_credentials(folder_name: str, account_id: int = None):
    db = None
    try:
        from core.db import SessionLocal, Post, Account
        db = SessionLocal()

        if account_id is not None:
            account = db.query(Account).filter(Account.id == account_id).first()
            if account and account.credentials:
                return account.platform, account.credentials

        post = db.query(Post).filter(Post.folder_name == folder_name).first()
        if post:
            account = db.query(Account).filter(Account.id == post.account_id).first()
            if account and account.credentials:
                return account.platform, account.credentials
    except Exception as e:
        logger.error(f"Erreur get_account_credentials: {e}")
    finally:
        if db:
            db.close()
    return "facebook", {"page_id": Config.FB_PAGE_ID, "access_token": Config.FB_PAGE_ACCESS_TOKEN}


def _post_with_retry(url, params=None, json_data=None, headers=None, max_retries=2):
    """POST with retry for transient errors (5xx, 429)."""
    for attempt in range(max_retries):
        try:
            response = requests.post(url, params=params, json=json_data, headers=headers, timeout=API_TIMEOUT_SHORT)
            if response.status_code in (429, 500, 502, 503):
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning(f"HTTP {response.status_code}, retry in {retry_after}s (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_after)
                continue
            return response
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                logger.warning(f"Request error: {e}, retrying...")
                time.sleep(3)
            else:
                raise
    return None


def publish_reel_video(reel_path, post_text, credentials=None):
    page_id = credentials.get("page_id") if credentials else Config.FB_PAGE_ID
    access_token = credentials.get("access_token") if credentials else Config.FB_PAGE_ACCESS_TOKEN
    if not page_id or not access_token:
        logger.error("PAGE_ID ou PAGE_ACCESS_TOKEN manquant pour reel")
        return None

    file_size = os.path.getsize(reel_path)
    description = post_text[:REEL_DESCRIPTION_MAX_CHARS] if post_text else "Reel"

    try:
        init_url = f"{GRAPH_API_URL}/{page_id}/video_reels"
        init_params = {"upload_phase": "start", "access_token": access_token}
        init_result = requests.post(init_url, params=init_params, timeout=API_TIMEOUT_SHORT).json()

        if "video_id" not in init_result:
            logger.error(f"Reel init failed - no video_id: {init_result}")
            return None

        video_id = init_result["video_id"]
        upload_url = init_result["upload_url"]

        headers = {"Authorization": f"OAuth {access_token}", "Content-Type": "video/mp4", "offset": "0", "file_size": str(file_size)}
        with open(reel_path, "rb") as f:
            upload_result = requests.post(upload_url, headers=headers, data=f.read(), timeout=API_TIMEOUT_LONG).json()

        if upload_result.get("success") != True:
            logger.error(f"Reel upload failed: {upload_result}")
            return None

        finish_params = {"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": description, "access_token": access_token}
        finish_result = requests.post(init_url, params=finish_params, timeout=API_TIMEOUT_SHORT).json()

        if finish_result.get("success") == True:
            return video_id
        else:
            logger.warning(f"Reel finish failed, retrying in {REEL_RETRY_DELAY}s...")
            time.sleep(REEL_RETRY_DELAY)
            retry_result = requests.post(init_url, params=finish_params, timeout=API_TIMEOUT_SHORT).json()
            if retry_result.get("success") == True:
                return video_id
            logger.error(f"Reel retry also failed: {retry_result}")
            return None

    except Exception as e:
        logger.error(f"Erreur publish_reel: {e}")
        return None

def post_via_graph_api(post_text, image_url=None, credentials=None):
    page_id = credentials.get("page_id") if credentials else Config.FB_PAGE_ID
    access_token = credentials.get("access_token") if credentials else Config.FB_PAGE_ACCESS_TOKEN
    if not page_id or not access_token:
        logger.error("PAGE_ID ou PAGE_ACCESS_TOKEN manquant")
        return None

    if image_url:
        url = f"{GRAPH_API_URL}/{page_id}/photos"
        params = {"access_token": access_token, "url": image_url, "message": post_text}
    else:
        url = f"{GRAPH_API_URL}/{page_id}/feed"
        params = {"access_token": access_token, "message": post_text}

    try:
        result = _post_with_retry(url, params=params)
        if result is None:
            logger.error("Graph API: all retries failed")
            return None
        data = result.json()
        if "id" in data:
            return data["id"]
        try:
            logger.error(f"Erreur Graph API: {data}")
        except Exception:
            pass
    except Exception as e:
        try:
            logger.error(f"Exception Graph API: {e}")
        except Exception:
            pass
    return None

def post_via_linkedin_api(post_text, image_url=None, credentials=None):
    """Publication LinkedIn via API v2 avec fallback sur .env"""
    logger.info("Tentative de publication via LinkedIn API")

    token = credentials.get("access_token") if credentials else None
    user_id = credentials.get("user_id") if credentials else None

    if not token or not user_id:
        logger.info("Credentials DB LinkedIn incomplètes, fallback sur .env")
        from dotenv import load_dotenv
        env_file = LI_MACHINE / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            import os
            token = os.getenv("LINKEDIN_TOKEN", "")
            user_id = os.getenv("LINKEDIN_USER_ID", "")
            logger.info(f"Token .env chargé: {bool(token)}, User ID: {user_id}")

    if not token or not user_id:
        logger.error("Aucun credentials LinkedIn disponible (DB + .env)")
        return None

    url = LINKEDIN_API_URL
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "author": f"urn:li:person:{user_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text[:LINKEDIN_MAX_CHARS]},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        response = _post_with_retry(url, json_data=payload, headers=headers)
        if response is None:
            logger.error("LinkedIn API: all retries failed")
            return None
        if response.status_code in [200, 201]:
            post_id = response.json().get("id", "")
            logger.info(f"Post LinkedIn publié: {post_id}")
            return post_id
        else:
            logger.error(f"Erreur LinkedIn API {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Exception LinkedIn API: {e}")
        return None

def post_via_twitter_api(post_text, image_url=None, credentials=None):
    logger.info("Tentative de publication via Twitter API")
    if not credentials or not credentials.get("bearer_token"):
        logger.error("Credentials Twitter manquants (bearer_token / api keys)")
        return None
    logger.error("Twitter API non implémenté - publication échouée")
    return None

def save_resource_for_post(post_id, trigger_word, resource_content):
    resources = load_post_resources()
    resources[post_id] = {
        "trigger_word": trigger_word,
        "resource_content": resource_content,
        "created_at": datetime.now().isoformat()
    }
    save_post_resources(resources)

def post_astuce_comments(folder, post_id, credentials=None):
    path = Path(folder)
    meta_file = path / "meta.json"
    if not meta_file.exists(): return
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    items = meta.get("astuce_items", [])
    if not items: return

    access_token = credentials.get("access_token") if credentials else Config.FB_PAGE_ACCESS_TOKEN
    time.sleep(COMMENT_INITIAL_DELAY)

    for i, item in enumerate(items):
        name = item.get('name', '')
        comment_text = f"{i+1}. **{name}**"
        url = f"{GRAPH_API_URL}/{post_id}/comments"
        params = {"access_token": access_token, "message": comment_text}
        try:
            _post_with_retry(url, params=params)
        except Exception as e:
            logger.error(f"Erreur commentaire astuce: {e}")
        if i < len(items) - 1:
            time.sleep(COMMENT_DELAY)

def post_trigger_comments(folder, post_id, credentials=None):
    path = Path(folder)
    trigger_file = path / "trigger_comments.json"
    if not trigger_file.exists(): return

    trigger_data = json.loads(trigger_file.read_text(encoding="utf-8"))
    comments = trigger_data.get("comments", [])
    if not comments: return

    access_token = credentials.get("access_token") if credentials else Config.FB_PAGE_ACCESS_TOKEN
    time.sleep(COMMENT_INITIAL_DELAY)

    for i, comment_text in enumerate(comments):
        url = f"{GRAPH_API_URL}/{post_id}/comments"
        params = {"access_token": access_token, "message": comment_text}
        try:
            _post_with_retry(url, params=params)
        except Exception as e:
            logger.error(f"Erreur trigger comment: {e}")
        if i < len(comments) - 1:
            time.sleep(COMMENT_DELAY)


def run_publisher(folder_path: str, use_graph_api=True, account_id: int = None, credentials: dict = None) -> AgentResult:
    try:
        path = Path(folder_path)
        meta_file = path / "meta.json"
        resource_file = path / "resource.json"

        if credentials is None:
            platform, credentials = get_account_credentials(path.name, account_id)
        else:
            platform = "facebook"
        logger.info(f"[PUBLISHER] run_publisher folder={path.name} account_id={account_id} platform={platform}, credentials_provided={credentials is not None}")

        if not platform:
            folder_lower = str(path).lower()
            if "linkedin" in folder_lower:
                platform = "linkedin"
            elif "twitter" in folder_lower or "x.com" in folder_lower:
                platform = "twitter"
            elif "facebook" in folder_lower or "instagram" in folder_lower:
                platform = "facebook"

        if platform == "linkedin":
            post_file = path / "linkedin_post.txt"
            if not post_file.exists():
                post_file = path / "post.txt"
        elif platform == "twitter":
            post_file = path / "tweet.txt"
            if not post_file.exists():
                post_file = path / "twitter_post.txt"
        else:
            post_file = path / "facebook_post.txt"

        if not post_file.exists():
            for alt_file in ["post.txt", "content.txt"]:
                alt_path = path / alt_file
                if alt_path.exists():
                    post_file = alt_path
                    break

        if not post_file.exists():
            return AgentResult.fail(f"Fichier post introuvable ({platform})")

        meta = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error reading meta.json: {e}")
            if meta.get("published", False):
                return AgentResult.ok({"status": "already_published"})

        post_text = post_file.read_text(encoding="utf-8")

        local_image = None
        for img_name in ["post_image.jpg", "post_image.jpeg", "post_image.png", "post_image.webp", "image.jpg", "image.jpeg", "image.png"]:
            if (path / img_name).exists():
                local_image = path / img_name
                break
        if not local_image:
            for subdir in ["images", "reel", "_cinema_work"]:
                for img_name in ["post_image.jpg", "post_image.jpeg", "post_image.png", "post_image.webp"]:
                    sub_path = path / subdir / img_name
                    if sub_path.exists():
                        local_image = sub_path
                        break
                if local_image:
                    break

        image_url = resolve_image_url(local_image, meta, prefix=f"post_{path.name[:30]}")
        if image_url:
            meta["image_url"] = image_url

        trigger_word, resource_content = "", ""
        if resource_file.exists():
            try:
                resource_data = json.loads(resource_file.read_text(encoding="utf-8"))
                trigger_word = resource_data.get("trigger_word", "")
                resource_content = resource_data.get("content", "")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error reading resource.json: {e}")

        reel_file = path / "reel.mp4"
        if not reel_file.exists():
            reel_file = path / "reel" / "reel.mp4"
        has_reel = reel_file.exists()

        persona = meta.get("persona", "")
        is_reel_only = (persona == "reel") or post_text.strip().lower().startswith("reel:")

        if not credentials:
            if platform == "linkedin":
                pass
            elif platform == "twitter":
                pass
            else:
                platform = "facebook"
                credentials = {
                    "page_id": Config.FB_PAGE_ID,
                    "access_token": Config.FB_PAGE_ACCESS_TOKEN
                }

        post_id = None
        reel_id = None

        if platform == "linkedin":
            post_id = post_via_linkedin_api(post_text, image_url, credentials)
            if not post_id:
                return AgentResult.fail("Echec LinkedIn API")
        elif platform == "twitter":
            post_id = post_via_twitter_api(post_text, image_url, credentials)
            if not post_id:
                return AgentResult.fail("Echec Twitter API")
        else:
            use_graph = use_graph_api and bool(credentials.get("access_token"))

            if use_graph:
                logger.info("Publication via Facebook Graph API")

                if is_reel_only and has_reel:
                    reel_brief_file = path / "reel_brief.txt"
                    description = None
                    if reel_brief_file.exists():
                        for line in reel_brief_file.read_text(encoding="utf-8").split("\n"):
                            if line.startswith("SUJET:"):
                                description = line[6:].strip()
                                break
                    if not description:
                        description = post_text.strip()
                        for prefix in ("reel:", "Reel:", "REEL:"):
                            if description.lower().startswith(prefix.lower()):
                                description = description[len(prefix):].strip()
                                break

                    logger.info(f"Reel-only — publication vidéo uniquement: {description[:60]}")
                    reel_id = publish_reel_video(str(reel_file), description, credentials)
                    if not reel_id:
                        return AgentResult.fail("Echec publication reel vidéo")
                    post_id = f"reel_{reel_id}"
                else:
                    post_id = post_via_graph_api(post_text, image_url, credentials)
                    if not post_id:
                        return AgentResult.fail("Echec Graph API")

                    if trigger_word and resource_content:
                        save_resource_for_post(post_id, trigger_word, resource_content)

                    if has_reel:
                        reel_id = publish_reel_video(str(reel_file), post_text, credentials)

        meta["published"] = True
        meta["published_at"] = datetime.now().isoformat()
        if post_id: meta["post_id"] = post_id
        if reel_id: meta["reel_id"] = reel_id
        # Backward compat: also write platform-specific keys
        if post_id and platform == "facebook": meta["facebook_post_id"] = post_id
        if reel_id and platform == "facebook": meta["facebook_reel_id"] = reel_id

        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        if meta.get("post_type") == "astuce" and post_id and not str(post_id).startswith("make_"):
            post_astuce_comments(path, post_id, credentials)

        if post_id and not str(post_id).startswith("make_") and (path / "trigger_comments.json").exists():
            post_trigger_comments(path, post_id, credentials)

        return AgentResult.ok({"post_id": post_id, "reel_id": reel_id})

    except Exception as e:
        try:
            logger.exception("Erreur Agent Publisher")
        except Exception:
            pass
        return AgentResult.fail(str(e))
