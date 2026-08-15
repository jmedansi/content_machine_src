# agent_publisher.py — Publication Instagram via Graph API (container → media_publish)
"""Publie un post Instagram (image ou reel) via l'API Graph de Meta.

Flux :
1. Création d'un container : POST /{ig_user_id}/media  (image_url ou media_type=REELS + video_url)
2. Publication : POST /{ig_user_id}/media_publish (creation_id=...)

Credentials attendus dans la DB compte Instagram (dict) :
  - ig_user_id  : ID du compte Instagram Business (obligatoire)
  - access_token: token de page Meta avec permission instagram_basic + pages_read_engagement
  - (optionnel) page_id : page FB liée (audit/log)

Un fallback .env est utilisé (IG_ACCOUNT_ID / FB_PAGE_ACCESS_TOKEN) si la DB est vide.
"""
import sys
import json
import logging
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Config
from core.logger import get_node_logger
from core.paths import FB_GRAPH_API_URL

logger = get_node_logger("instagram_publisher")

GRAPH_URL = FB_GRAPH_API_URL  # https://graph.facebook.com/v18.0
DEFAULT_IG_USER_ID = getattr(Config, "IG_ACCOUNT_ID", "") or ""
DEFAULT_TOKEN = getattr(Config, "FB_PAGE_ACCESS_TOKEN", "") or ""
API_TIMEOUT_SHORT = int(getattr(Config, "API_TIMEOUT_SHORT", 30))
API_TIMEOUT_LONG = int(getattr(Config, "API_TIMEOUT_LONG", 300))
MAX_CAPTION_CHARS = int(getattr(Config, "INSTAGRAM_MAX_CAPTION_CHARS", 2200))


def get_instagram_credentials(account_id=None):
    """Credentials Instagram depuis la DB plateforme (leads_station.db).
    Retourne (ig_user_id, access_token) ou (None, None)."""
    try:
        import sqlite3
        db_path = Path("d:/Content_Machine/machines/instagram_machine/data/leads_station.db")
        if not db_path.exists():
            return DEFAULT_IG_USER_ID, DEFAULT_TOKEN
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        if account_id:
            row = conn.execute(
                "SELECT credentials FROM accounts WHERE id=? AND platform='instagram'",
                (account_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT credentials FROM accounts WHERE platform='instagram' AND status='active' ORDER BY id LIMIT 1"
            ).fetchone()
        conn.close()
        if row and row["credentials"]:
            creds = json.loads(row["credentials"]) if isinstance(row["credentials"], str) else row["credentials"]
            ig = creds.get("ig_user_id") or creds.get("instagram_user_id") or creds.get("user_id") or DEFAULT_IG_USER_ID
            tok = creds.get("access_token") or creds.get("token") or DEFAULT_TOKEN
            return ig, tok
    except Exception as e:
        logger.warning(f"[IG] Erreur credentials DB: {e}")
    return DEFAULT_IG_USER_ID, DEFAULT_TOKEN


def _post_graph(url, params, timeout=API_TIMEOUT_SHORT, max_retries=2):
    """POST Graph API avec retry sur 429/5xx."""
    import requests
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503):
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(f"[IG] HTTP {resp.status_code}, retry dans {retry_after}s (tentative {attempt+1})")
                time.sleep(retry_after)
                continue
            return resp
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                raise
    return None


def _resolve_image_url(folder: Path):
    """Retourne une URL publique de l'image du post (via le endpoint image du dashboard) ou le fichier local."""
    for name in ["post_image.jpg", "post_image.jpeg", "post_image.png", "post_image.webp",
                 "image.jpg", "image.jpeg", "image.png"]:
        f = folder / name
        if f.exists():
            return f
    for sub in ["images", "_cinema_work"]:
        for name in ["post_image.jpg", "post_image.jpeg", "post_image.png", "post_image.webp"]:
            f = folder / sub / name
            if f.exists():
                return f
    return None


def _read_caption(folder: Path) -> str:
    """Lecture du texte du post (priorité au fichier platforme Instagram, fallback facebook_post.txt)."""
    for name in ["instagram_post.txt", "facebook_post.txt", "post.txt", "content.txt"]:
        f = folder / name
        if f.exists():
            txt = f.read_text(encoding="utf-8").strip()
            # Retirer le bloc IMAGE PROMPT éventuel
            if "---IMAGE PROMPT---" in txt:
                txt = txt.split("---IMAGE PROMPT---")[0].strip()
            return txt[:MAX_CAPTION_CHARS]
    return ""


def _read_reel(folder: Path) -> Path:
    for name in ["reel.mp4", "final_video.mp4"]:
        f = folder / name
        if f.exists():
            return f
    f = folder / "reel" / "reel.mp4"
    if f.exists():
        return f
    return None


def _mark_meta(folder: Path, **fields):
    """Met à jour meta.json avec les champs fournis."""
    meta_file = folder / "meta.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta.update(fields)
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def publish_instagram(folder: str, account_id=None, credentials=None, publish=True) -> bool:
    """Publie le post du dossier sur Instagram.

    Returns: True si publié, False sinon (ou si pas de token → on prépare le container seulement si publish=False).
    """
    path = Path(folder)
    if not path.exists():
        logger.error(f"[IG] Dossier introuvable: {folder}")
        return False

    if credentials:
        ig = credentials.get("ig_user_id") or credentials.get("instagram_user_id") or DEFAULT_IG_USER_ID
        tok = credentials.get("access_token") or credentials.get("token") or DEFAULT_TOKEN
    else:
        ig, tok = get_instagram_credentials(account_id)

    caption = _read_caption(path)
    image = _resolve_image_url(path)
    reel = _read_reel(path)

    has_reel = reel is not None
    has_image = image is not None

    if not publish:
        # Mode préparation : on note seulement les capacités détectées
        logger.info(f"[IG] Préparation (no publish) — caption={len(caption)} car, image={has_image}, reel={has_reel}")
        return True

    if not ig or not tok:
        logger.error("[IG] Credentials Instagram manquants (ig_user_id + access_token). Publication ignorée.")
        return False

    import requests
    # ── REEL : upload 2 phases (container REELS + publish) ──
    if has_reel:
        try:
            create_url = f"{GRAPH_URL}/{ig}/media"
            create_params = {
                "media_type": "REELS",
                "video_url": None,  # rempli ci-dessous
                "caption": caption,
                "access_token": tok,
            }
            # Le Graph API IG accepte un upload direct via video_url, mais pour un fichier local
            # on passe par l'upload resumable puis media_publish. On tente d'abord video_url public.
            # Pour un fichier local, on tente l'upload de session.
            reel_local = reel
            session_url = f"{GRAPH_URL}/{ig}/media"
            session_resp = _post_graph(
                session_url,
                {"media_type": "REELS", "upload_type": "resumable", "access_token": tok},
            )
            if session_resp and session_resp.status_code == 200:
                sess = session_resp.json()
                upload_url = sess.get("url") or sess.get("upload_url")
                video_id = sess.get("video_id")
                if upload_url:
                    file_size = reel_local.stat().st_size
                    headers = {
                        "Authorization": f"OAuth {tok}",
                        "Content-Type": "video/mp4",
                        "file_size": str(file_size),
                    }
                    with open(str(reel_local), "rb") as f:
                        up = requests.post(upload_url, headers=headers, data=f.read(), timeout=API_TIMEOUT_LONG)
                    if up.status_code == 200:
                        creation = _post_graph(
                            session_url,
                            {
                                "media_type": "REELS",
                                "video_id": video_id or sess.get("id", ""),
                                "caption": caption,
                                "access_token": tok,
                            },
                        )
                        if creation and creation.status_code == 200:
                            container_id = creation.json().get("id")
                        else:
                            logger.error(f"[IG] Création container REELS échouée: {creation.text if creation else 'None'}")
                            return False
                    else:
                        logger.error(f"[IG] Upload vidéo échoué: {up.status_code}")
                        return False
                else:
                    logger.error(f"[IG] Pas d'URL d'upload retournée: {sess}")
                    return False
            else:
                logger.error(f"[IG] Init upload REELS échoué: {session_resp.text if session_resp else 'None'}")
                return False
        except Exception as e:
            logger.exception(f"[IG] Erreur reel: {e}")
            return False
    # ── IMAGE / PHOTO : container IMAGE ──
    elif has_image:
        # L'API IG nécessite une URL publique pour l'image du container.
        # Le dashboard expose les images locales via /api/image/{folder}; on préfère l'URL publique
        # du dashboard. Sinon on tente un upload local via le même endpoint média (non supporté pour IMAGE).
        image_url = None
        # 1) URL déjà résolue dans meta.json (image_url publiée sur FB)
        meta_file = path / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("image_url"):
                    image_url = meta["image_url"]
            except Exception:
                pass
        if not image_url:
            # 2) Upload local : l'API IG ne supporte pas le multipart classique pour IMAGE.
            # On tente néanmoins via le format "media_type=IMAGE&image_url=" uniquement si l'image
            # est déjà servie publiquement. Sinon on signale qu'il faut servir l'image.
            logger.warning("[IG] Pas d'URL publique pour l'image — tentative via URL du dashboard.")
            # Serveur local sur 127.0.0.1:8000 — non accessible à Meta. On arrête proprement.
            # Le pipeline continuera sans publication, l'erreur est loggée dans meta.json.
            logger.error("[IG] Image locale non accessible par Meta (nécessite une URL publique).")
            _mark_meta(path, instagram_status="image_requires_public_url")
            return False

        create_params = {
            "image_url": image_url,
            "caption": caption,
            "access_token": tok,
        }
        create_url = f"{GRAPH_URL}/{ig}/media"
        creation = _post_graph(create_url, create_params)
        if not creation or creation.status_code != 200:
            logger.error(f"[IG] Création container IMAGE échouée: {creation.text if creation else 'None'}")
            return False
        container_id = creation.json().get("id")
    else:
        # Texte seul — Instagram n'autorise pas un post texte pur via l'API.
        logger.error("[IG] Aucun média (image/reel) trouvé — Instagram exige un visuel.")
        return False

    # ── PUBLICATION FINALE ──
    if not container_id:
        return False
    publish_resp = _post_graph(
        f"{GRAPH_URL}/{ig}/media_publish",
        {"creation_id": container_id, "access_token": tok},
    )
    if not publish_resp or publish_resp.status_code != 200:
        logger.error(f"[IG] media_publish échoué: {publish_resp.text if publish_resp else 'None'}")
        return False

    data = publish_resp.json()
    media_id = data.get("id")
    _mark_meta(
        path,
        published=True,
        published_at=datetime.now().isoformat(),
        instagram_media_id=media_id,
        instagram_status="published",
        instagram_container_id=container_id,
    )
    logger.info(f"[IG] Publié sur Instagram: media_id={media_id}")
    return True


def post_instagram(folder: str, account_id=None) -> bool:
    """Wrapper compatible scheduler."""
    return publish_instagram(folder, account_id=account_id, publish=True)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    if folder:
        print("OK" if post_instagram(folder) else "FAIL")
    else:
        print("Usage: python agent_publisher.py <folder_path>")