"""
dashboard_api_v2.py — API FastAPI complète et fonctionnelle pour le Dashboard IncidenX

Routes:
  GET  /api/status              → Statut des services
  GET  /api/pending             → Posts en attente
  POST /api/approve             → Approuver un post
  POST /api/reject              → Rejeter un post
  POST /api/publish_now         → Publier immédiatement
  
  GET  /api/content             → Liste du contenu
  GET  /api/content/{folder}    → Détail d'un post
  POST /api/update_post         → Mettre à jour le texte
  
  GET  /api/generate            → Générer un post (texte)
  GET  /api/generate_reel       → Générer un réel (vidéo séparée)
  POST /api/generate_batch      → Générer le batch du jour
  
  POST /api/regenerate_post     → Régénérer le texte
  POST /api/regenerate_image    → Régénérer l'image
  POST /api/regenerate_reel     → Régénérer le reel
  
  GET  /api/image/{folder}      → Servir une image
  GET  /api/reel/{folder}       → Servir un reel
  
  GET  /api/personas            → Liste dynamique des personas
"""

import sys
# if sys.platform == "win32":
#     import io
#     try:
#         if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
#             sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
#         if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
#             sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
#     except (ValueError, AttributeError):
#         pass

import os
import json
import shutil
import asyncio
import subprocess
import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import csv
import io
from datetime import datetime, date

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
LIBRARY_IMAGES_DIR = BASE_DIR / "image_library"
LIBRARY_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Import centralized paths
sys.path.insert(0, str(ROOT_DIR))
from core.paths import (
    PLATFORM_BASE, PLATFORM_DB, VALID_PLATFORMS,
    FB_GRAPH_API_URL, LINKEDIN_API_URL,
    SUPPORTED_IMAGE_FILES, SUPPORTED_REEL_FILES, SUPPORTED_TEXT_FILES,
    API_TIMEOUT_SHORT, MAX_OUTPUT_CHARS, MAX_LOG_ENTRIES,
    BATCH_HOUR, BATCH_MINUTE, AUTO_POLL_INTERVAL, MAX_PLANNING_DAYS,
    CHROME_DEBUG_PORT, GEMINI_MAX_WAIT, GITHUB_MAX_RETRIES, MAX_UPLOAD_SIZE,
    API_PORT,
)

# Chemins vers les machines
FB_MACHINE = PLATFORM_BASE["facebook"]
LI_MACHINE = PLATFORM_BASE["linkedin"]
TW_MACHINE = PLATFORM_BASE["twitter"]

# IMPORTANT: FB_MACHINE doit être accessible pour les imports d'agents
sys.path.insert(0, str(FB_MACHINE))  # Facebook accessible
sys.path.insert(0, str(BASE_DIR))    # Dashboard en premier
sys.path.insert(0, str(ROOT_DIR))    # ROOT_DIR en premier pour core.config, core.task_tracker, etc.

try:
    import dashboard.api.topics_store as topics_store
except ModuleNotFoundError:
    import api.topics_store as topics_store

from fastapi import FastAPI, APIRouter, Request, HTTPException, BackgroundTasks, Form, UploadFile, File, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import Config
from core.task_tracker import create_task, update_task
from core.db import init_db
import threading
from core.logger import get_node_logger

logger = get_node_logger("dashboard_api")
logger.info(f"[STARTUP] sys.path[0:3]: {sys.path[:3]}")
logger.info(f"[STARTUP] FB_MACHINE: {FB_MACHINE}")

app = FastAPI(title="IncidenX Dashboard API")

# Servir les templates HTML
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Route principale - servir le dashboard
@app.get("/")
async def root(request: Request):
    template = templates.env.get_template("views/dashboard_v5.html")
    return HTMLResponse(content=template.render(request=request), status_code=200)

@app.get("/login")
async def login_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=302)

@app.get("/api/auth/me")
async def api_auth_me():
    return {"authenticated": True, "is_admin": True, "user_id": 1, "name": "Admin"}

@app.post("/api/auth/logout")
async def api_auth_logout():
    return {"success": True}

@app.get("/dashboard")
async def dashboard(request: Request):
    template = templates.env.get_template("views/dashboard_v5.html")
    return HTMLResponse(content=template.render(request=request), status_code=200)

@app.get("/manifest.json")
async def manifest():
    """Sert le fichier manifest.json pour PWA"""
    manifest_path = BASE_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path, media_type="application/manifest+json")
    else:
        raise HTTPException(status_code=404, detail="Manifest not found")

# Servir les fichiers statiques (CSS, JS, icons)
css_path = BASE_DIR / "css"
js_path = BASE_DIR / "js"
icons_path = BASE_DIR / "icons"

logger.info(f"CSS path: {css_path}, exists: {css_path.exists()}")
logger.info(f"JS path: {js_path}, exists: {js_path.exists()}")
logger.info(f"Icons path: {icons_path}, exists: {icons_path.exists()}")

if css_path.exists():
    app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
if js_path.exists():
    app.mount("/js", StaticFiles(directory=str(js_path)), name="js")
if icons_path.exists():
    app.mount("/icons", StaticFiles(directory=str(icons_path)), name="icons")

router = APIRouter(prefix="/api", tags=["dashboard"])

DATA_DIR    = Config.DATA_DIR
CONTENT_DIR = Config.CONTENT_DIR


DEFAULT_SCHEDULE = [
    {"time": "08:00", "persona": "ia_design",          "type": "post"},
    {"time": "10:30", "persona": "post_court",         "type": "post"},
    {"time": "12:30", "persona": "mini_formation",     "type": "post"},
    {"time": "14:00", "persona": "storytelling_pro",   "type": "post"},
    {"time": "16:30", "persona": "ia_integration",    "type": "post"},
    {"time": "19:00", "persona": "business_auto",     "type": "post"},
    {"time": "20:30", "persona": "cta",                "type": "post"}
]

def _get_schedule_file(platform: str, account_id: int) -> Path:
    base = PLATFORM_BASE.get(platform)
    if not base:
        return DATA_DIR / "schedule.json"
    
    new_path = base / "accounts" / str(account_id) / "schedule.json"
    new_path.parent.mkdir(parents=True, exist_ok=True)
    return new_path

def _load_schedule(platform: str = "facebook", account_id: int = 1):
    schedule_file = _get_schedule_file(platform, account_id)
    if schedule_file.exists():
        try:
            data = json.loads(schedule_file.read_text(encoding="utf-8"))
            # Support both format: list or {"schedule": [...]}
            if isinstance(data, dict):
                s = data.get("schedule", [])
                if s: return s
            elif data:
                return data
        except Exception:
            pass
            
    # Fallback: create a dynamic schedule using actual platform personas
    try:
        personas_dir = _get_personas_dir_for_account(account_id, platform)
        if personas_dir.exists():
            valid_personas = [p.name for p in sorted(personas_dir.iterdir()) if p.is_dir() and not p.name.startswith("_") and not p.name.startswith(".")]
            if valid_personas:
                times = ["08:00", "10:30", "12:30", "14:00", "16:30", "19:00", "20:30"]
                dynamic_schedule = []
                for i, persona in enumerate(valid_personas):
                    t = times[i % len(times)]
                    # Distribute evenly if there are more personas than timeslots
                    if i >= len(times): t = f"{min(23, 8 + i)}:00" 
                    dynamic_schedule.append({"time": t, "persona": persona, "type": "post"})
                return dynamic_schedule
    except Exception as e:
        logger.error(f"Error generating dynamic schedule: {e}")

    return DEFAULT_SCHEDULE.copy()

def _save_schedule(schedule: list, platform: str = "facebook", account_id: int = 1):
    schedule_file = _get_schedule_file(platform, account_id)
    schedule_file.write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding="utf-8")

def _get_planned_topics_file(platform: str, account_id: int) -> Path:
    base = PLATFORM_BASE.get(platform)
    if not base:
        return DATA_DIR / "planned_topics.json"
    acc_dir = base / "accounts" / str(account_id)
    acc_dir.mkdir(parents=True, exist_ok=True)
    return acc_dir / "planned_topics.json"

def _load_planned_topics(platform: str = "facebook", account_id: int = 1):
    f = _get_planned_topics_file(platform, account_id)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_planned_topics(topics: dict, platform: str = "facebook", account_id: int = 1):
    f = _get_planned_topics_file(platform, account_id)
    f.write_text(json.dumps(topics, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_daily_plan_file(date: str, account_id: int = None, platform: str = "facebook") -> Path:
    # Unifié avec shared_agents/topic_finder : machines/{platform}_machine/accounts/{id}/content/plans/
    base = PLATFORM_BASE.get(platform, Path("d:/Content_Machine/machines/facebook_machine"))
    if account_id:
        plans_dir = base / "accounts" / str(account_id) / "content" / "plans"
    else:
        plans_dir = base / "content" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{account_id}_" if account_id else ''
    return plans_dir / f"{date}_{prefix}plan.json"


def _get_content_dir(platform, account_id: int = None):
    """Helper pour récupérer le dossier content selon plateforme et account."""
    if platform and platform not in VALID_PLATFORMS:
        logger.warning(f"Unknown platform '{platform}', falling back to default")
    base = PLATFORM_BASE.get(platform)
    if not base:
        return Config.CONTENT_DIR

    # Si account_id fourni, retourner le dossier account-spécifique directement
    # (sera créé si nécessaire par le code qui appelle cette fonction)
    if account_id:
        acc_dir = base / "accounts" / str(account_id)
        content_dir = acc_dir / "content"
        return content_dir

    # Fallback: utiliser le content principal de la plateforme
    return base / "content"


# ══════════════════════════════════════════════════════════════════
# HELPERS - LECTURE/ÉCRITURE POSTS
# ══════════════════════════════════════════════════════════════════

_IMAGE_FILES = SUPPORTED_IMAGE_FILES
_REEL_FILES  = SUPPORTED_REEL_FILES
_TEXT_FILES  = SUPPORTED_TEXT_FILES


def _safe_folder(base: Path, user_folder: str) -> Path:
    """Valide que le chemin résultant reste dans base (protection path traversal)."""
    if not user_folder:
        raise HTTPException(status_code=400, detail="folder parameter required")
    resolved = (base / user_folder).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Access denied: invalid path")
    return resolved

def _find_file(folder: Path, names: list, subdir: str = None) -> Optional[Path]:
    """Trouve un fichier dans le dossier ou sous-dossier optionnel."""
    search_dir = folder / subdir if subdir else folder
    for name in names:
        f = search_dir / name
        if f.exists(): return f
    return None

def _find_file_recursive(folder: Path, names: list) -> Optional[Path]:
    """Trouve un fichier dans le dossier ET ses sous-dossiers (pour reels/images dans reel/)."""
    # Chercher à la racine
    result = _find_file(folder, names)
    if result:
        return result
    
    # Chercher dans les sous-dossiers potentiels
    for subdir in ["reel", "images", "_cinema_work"]:
        result = _find_file(folder, names, subdir)
        if result:
            return result

    # Chercher n'importe quel fichier image dans les sous-dossiers pour les noms de fichiers non standards
    if folder.exists() and folder.is_dir():
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
                if path.name in names or path.parent.name in ['images', 'reel', '_cinema_work']:
                    return path
    return None

def _read_post(folder: Path) -> dict:
    # Migration: si metadata.json existe mais pas meta.json, renommer
    meta_file = folder / "meta.json"
    legacy_file = folder / "metadata.json"
    if not meta_file.exists() and legacy_file.exists():
        try:
            legacy_file.rename(meta_file)
        except Exception:
            pass

    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Error reading meta.json: {e}")
    
    # Détection automatique si champs manquants (avec recherche recursive pour les sous-dossiers)
    if "has_image" not in meta:
        meta["has_image"] = _find_file_recursive(folder, _IMAGE_FILES) is not None
    if "has_reel" not in meta:
        meta["has_reel"] = _find_file_recursive(folder, _REEL_FILES) is not None
        
    return meta

def _save_meta(folder: Path, updates: dict):
    meta = _read_post(folder)
    meta.update(updates)
    meta_file = folder / "meta.json"
    tmp_file = folder / "meta.json.tmp"
    tmp_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_file, meta_file)  # Cross-platform atomic overwrite

def _sync_folders_to_db(platform: str, account_id: int):
    """Synchronise les dossiers physiques vers la base de données (Post)."""
    if not account_id: return
    
    target_dir = _get_content_dir(platform, account_id)
    if not target_dir or not target_dir.exists(): return
    
    conn = _get_platform_db(platform)
    if not conn:
        logger.warning(f"No DB found for platform: {platform}")
        return
    
    try:
        for folder in target_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("_"): continue
            
            meta = _read_post(folder)
            # Posts "generating" orphelins (génération interrompue) → draft après 24h
            if meta.get("status") == "generating":
                created = meta.get("created_at") or ""
                try:
                    created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if created_dt.tzinfo is not None:
                        created_dt = created_dt.replace(tzinfo=None)
                except Exception:
                    created_dt = None
                if created_dt is None or (datetime.now() - created_dt).total_seconds() > 86400:
                    meta["status"] = "draft"
                    _save_meta(folder, {"status": "draft"})
            cursor = conn.execute("SELECT id FROM posts WHERE account_id=? AND folder_name=?", (account_id, folder.name))
            post = cursor.fetchone()
            
            if not post:
                # Vérifier si le dossier existe déjà sous un autre compte
                cursor = conn.execute("SELECT id FROM posts WHERE folder_name=?", (folder.name,))
                existing = cursor.fetchone()
                if existing:
                    conn.execute("UPDATE posts SET account_id=? WHERE folder_name=?", (account_id, folder.name))
                    logger.info(f"Reassigned post {folder.name} to account {account_id}")
                else:
                    text_file = _find_file(folder, _TEXT_FILES)
                    content = text_file.read_text(encoding="utf-8") if text_file else ""
                    created_at = meta.get("created_at") or datetime.now().isoformat()
                    conn.execute("""
                        INSERT INTO posts (account_id, folder_name, persona, topic, status, published, has_image, has_reel, content_text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        account_id,
                        folder.name,
                        meta.get("persona", "expert_ia"),
                        meta.get("topic", ""),
                        meta.get("status", "draft"),
                        1 if meta.get("published", False) else 0,
                        1 if meta.get("has_image", False) else 0,
                        1 if meta.get("has_reel", False) else 0,
                        content,
                        created_at
                    ))
            else:
                current_status = None
                cur_status = conn.execute("SELECT status FROM posts WHERE account_id=? AND folder_name=?", (account_id, folder.name)).fetchone()
                if cur_status:
                    current_status = cur_status[0]
                status = meta.get("status") if "status" in meta else (current_status or "draft")
                conn.execute("""
                    UPDATE posts SET status=?, published=?, has_image=?, has_reel=?
                    WHERE account_id=? AND folder_name=?
                """, (
                    status,
                    1 if meta.get("published", False) else 0,
                    1 if meta.get("has_image", False) else 0,
                    1 if meta.get("has_reel", False) else 0,
                    account_id,
                    folder.name
                ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error syncing folders to DB: {e}")
    finally:
        conn.close()

def _list_post_folders(platform: str = "facebook", account_id=None):
    """Liste tous les dossiers de contenu (triés par date décroissante)."""
    target_dir = _get_content_dir(platform, account_id)
    if not target_dir.exists(): return []
    folders = [d for d in target_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
    return sorted(folders, key=lambda x: x.name, reverse=True)


# ══════════════════════════════════════════════════════════════════
# ROUTES API - STATUT ET PENDING
# ══════════════════════════════════════════════════════════════════

@router.get("/status")
async def api_status(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
        _sync_folders_to_db(platform, account_id)
    
    conn = _get_platform_db(platform)
    pending = 0
    published = 0
    try:
        if conn and account_id:
            cursor = conn.execute("SELECT status, published FROM posts WHERE account_id=?", (account_id,))
            for row in cursor:
                if row["status"] == "pending": pending += 1
                if row["status"] == "published" or row["published"]: published += 1
    finally:
        if conn:
            conn.close()
            
    return {
        "platform": platform,
        "account_id": account_id,
        "pending_count": pending,
        "published_count": published,
        "last_update": datetime.now().isoformat(),
        "ai_responses": _load_ai_responses_config(),
        "reel_mode": "music",
        "webhook":          {"status": True},
        "tunnel":           {"status": False},
        "scheduler":        {"status": True},
        "ollama":           {"status": False},
        "token_valid":      bool(Config.FB_PAGE_ACCESS_TOKEN),
        "next_slot":        _compute_next_slot(platform, account_id),
        "next_publication": _compute_next_slot(platform, account_id),
    }

@router.get("/pending")
async def api_pending(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
        # ── Vérifier que l'utilisateur a accès à ce compte ──
        allowed = _get_user_account_ids(request)
        if allowed is not None and account_id not in allowed:
            return {"posts": [], "count": 0, "error": "Accès non autorisé à ce compte"}
        try:
            _sync_folders_to_db(platform, account_id)
        except Exception as e:
            logger.warning(f"Sync folders error for account {account_id}: {e}")
    
    target_dir = _get_content_dir(platform, account_id)
    db_path = PLATFORM_DB.get(platform)
    results = []
    if not db_path or not Path(db_path).exists():
        return {"posts": results, "count": 0}
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if account_id:
            cursor.execute(
                "SELECT id, folder_name, persona, content_text, status, published, has_image, image_filename, image_failed, has_reel, reel_filename, created_at FROM posts WHERE account_id=? AND status='pending' AND published=0 ORDER BY id DESC",
                (account_id,)
            )
            posts = cursor.fetchall()
            for p in posts:
                params = f"?platform={platform}&account_id={account_id}"
                folder_path = target_dir / p["folder_name"]
                
                # Detect images: prefer explicit metadata (supports multi-image), fallback to legacy filename search
                meta = _read_post(folder_path) if folder_path.exists() else {}
                has_image_meta = bool(meta.get("has_image"))
                has_image_physically = has_image_meta or (_find_file_recursive(folder_path, _IMAGE_FILES) is not None if folder_path.exists() else False)
                has_reel_physically = _find_file_recursive(folder_path, _REEL_FILES) is not None if folder_path.exists() else False

                image_urls = []
                # If metadata contains an images array, expose each image via /api/image with index
                images_meta = meta.get("images") if isinstance(meta.get("images"), list) else []
                if images_meta:
                    for item in images_meta:
                        try:
                            index = int(item.get("index", len(image_urls) + 1))
                        except Exception:
                            index = len(image_urls) + 1
                        image_urls.append(f"/api/image/{p['folder_name']}{params}&index={index}")
                elif has_image_physically:
                    image_urls = [f"/api/image/{p['folder_name']}{params}"]

                results.append({
                    "folder": p["folder_name"],
                    "content": p["content_text"] or "",
                    "persona": p["persona"],
                    "created_at": p["created_at"],
                    "date": p["created_at"][:10] if p["created_at"] else p["folder_name"][:10],
                    "word_count": meta.get("word_count"),
                    "ai_responses": meta.get("ai_responses"),
                    "has_image": has_image_physically,
                    "image_url": image_urls[0] if image_urls else None,
                    "image_urls": image_urls,
                    "image_count": len(image_urls),
                    "image_failed": bool(p["image_failed"]),
                    "has_reel": has_reel_physically,
                    "reel_url": f"/api/reel/{p['folder_name']}{params}" if has_reel_physically else None,
                    "published": bool(p["published"])
                })
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching pending posts: {e}")
        results = []
            
    return {"posts": results, "count": len(results)}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - ACTIONS POST (APPROVE, REJECT, PUBLISH)
# ══════════════════════════════════════════════════════════════════

@router.post("/approve")
async def api_approve(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    # ── Vérifier accès au compte ──
    if account_id and account_id.isdigit():
        allowed = _get_user_account_ids(req)
        if allowed is not None and int(account_id) not in allowed:
            return {"success": False, "error": "Accès non autorisé à ce compte"}
    body = await req.json()
    folder_name = body.get("folder")
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    
    if folder.exists():
        _save_meta(folder, {"status": "approved"})
        if account_id and account_id.isdigit():
            conn = _get_platform_db(platform)
            if conn:
                try:
                    conn.execute("UPDATE posts SET status='approved' WHERE account_id=? AND folder_name=?", (int(account_id), folder_name))
                    conn.commit()
                finally:
                    conn.close()
        return {"success": True}
    return {"success": False, "error": "Dossier introuvable"}

@router.post("/approve_all")
async def api_approve_all(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    # ── Vérifier accès au compte ──
    if account_id and account_id.isdigit():
        allowed = _get_user_account_ids(req)
        if allowed is not None and int(account_id) not in allowed:
            return {"success": False, "error": "Accès non autorisé à ce compte"}
    target_dir = _get_content_dir(platform, account_id)
    
    approved = 0
    for folder in target_dir.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        meta = _read_post(folder)
        if meta.get("status") == "pending":
            _save_meta(folder, {"status": "approved"})
            approved += 1
    
    if account_id and account_id.isdigit():
        conn = _get_platform_db(platform)
        if conn:
            try:
                conn.execute("UPDATE posts SET status='approved' WHERE account_id=? AND status='pending' AND published=0", (int(account_id),))
                conn.commit()
            finally:
                conn.close()
    
    return {"success": True, "approved": approved}

@router.post("/reject")
async def api_reject(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    # ── Vérifier accès au compte ──
    if account_id and account_id.isdigit():
        allowed = _get_user_account_ids(req)
        if allowed is not None and int(account_id) not in allowed:
            return {"success": False, "error": "Accès non autorisé à ce compte"}
    body = await req.json()
    folder_name = body.get("folder")
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    
    if folder.exists():
        _save_meta(folder, {"status": "rejected"})
        if account_id and account_id.isdigit():
            conn = _get_platform_db(platform)
            if conn:
                try:
                    conn.execute("UPDATE posts SET status='rejected' WHERE account_id=? AND folder_name=?", (int(account_id), folder_name))
                    conn.commit()
                finally:
                    conn.close()
        return {"success": True}
    return {"success": False, "error": "Dossier introuvable"}

@router.post("/publish_now")
async def api_publish_now(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id_param = req.query_params.get("account_id")
    # ── Vérifier accès au compte ──
    if account_id_param and account_id_param.isdigit():
        allowed = _get_user_account_ids(req)
        if allowed is not None and int(account_id_param) not in allowed:
            return {"success": False, "error": "Accès non autorisé à ce compte"}
    body = await req.json()
    folder_name = body.get("folder")
    
    # Parse account_id to int if provided
    account_id = int(account_id_param) if account_id_param and account_id_param.isdigit() else None
    
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    
    if not folder.exists():
        return {"success": False, "error": f"Dossier introuvable: {folder}"}
        
    try:
        # Récupérer les credentials du compte depuis la DB de la plateforme
        credentials = None
        if account_id:
            conn = _get_platform_db(platform)
            if conn:
                try:
                    cursor = conn.execute("SELECT credentials FROM accounts WHERE id=?", (account_id,))
                    row = cursor.fetchone()
                    if row and row["credentials"]:
                        import json
                        credentials = json.loads(row["credentials"]) if isinstance(row["credentials"], str) else row["credentials"]
                        logger.info(f"Credentials récupérées pour {platform} account_id={account_id}")
                    else:
                        logger.warning(f"Pas de credentials trouvées pour {platform} account_id={account_id}")
                finally:
                    conn.close()
        
        run_publisher = _get_publisher(platform)
        if not run_publisher:
            return {"success": False, "error": f"Publisher non trouvé pour {platform}"}
        
        logger.info(f"Publishing {platform} folder={folder} account_id={account_id}")
        # Passer les credentials au publisher
        res = run_publisher(str(folder), account_id=account_id, credentials=credentials, force_text_only=force_without_image)
        
        # Debug logging
        logger.info(f"[_publish_now] Raw result type: {type(res)}, value: {repr(res)}")
        logger.info(f"[_publish_now] Has success attr: {hasattr(res, 'success')}")
        
        if hasattr(res, 'success') and res.success:
            logger.info(f"[_publish_now] SUCCESS branch taken")
            _save_meta(folder, {"status": "published", "published": True, "published_at": datetime.now().isoformat()})
            if account_id:
                conn = _get_platform_db(platform)
                if conn:
                    try:
                        conn.execute("UPDATE posts SET status='published', published=1 WHERE account_id=? AND folder_name=?", (account_id, folder_name))
                        conn.commit()
                    finally:
                        conn.close()
            return {"success": True}

        # Confirmation demandée : l'image n'a pas pu être attachée
        if isinstance(res, dict) and res.get("needs_confirmation"):
            reason = res.get("reason", "image non attachée")
            logger.warning(f"[_publish_now] Image attachment failed for {platform} folder={folder_name}: {reason}")
            return {"success": False, "needs_confirmation": True, "error": reason}
        
        # Diagnostic plus fin pour les échecs
        logger.info(f"[_publish_now] FAIL branch taken")
        if hasattr(res, 'success') and not res.success:
            err_msg = getattr(res, 'error_cause', None) or "Publication échouée"
        elif res == False:
            err_msg = "Publication retourné False - vérifiez credentials et le fichier content"
        else:
            err_msg = str(res) if res else "Résultat invalide"
        
        logger.error(f"publish_now FAILED platform={platform} account_id={account_id} folder={folder_name} error={err_msg}")
        return {"success": False, "error": err_msg}
    except Exception as e:
        try:
            logger.exception(f"Erreur publish_now: {e}")
        except Exception:
            pass
        return {"success": False, "error": str(e)}


@router.get("/publish")
async def api_publish_from_query(req: Request):
    """Publication rapide via query param (compatible content.js)."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    folder_name = req.query_params.get("folder")
    if not folder_name:
        return {"success": False, "error": "Paramètre folder manquant"}

    class _FakeBody:
        async def json(self):
            return {"folder": folder_name}

    return await api_publish_now(_FakeBody())


@router.get("/delete")
async def api_delete_content(req: Request):
    """Supprime un post (dossier + entrée DB)."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    folder_name = req.query_params.get("folder")
    if not folder_name:
        return {"success": False, "error": "Paramètre folder manquant"}

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id and account_id.isdigit() and int(account_id) not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}

    try:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        if account_id and account_id.isdigit():
            conn = _get_platform_db(platform)
            if conn:
                try:
                    conn.execute("DELETE FROM posts WHERE account_id=? AND folder_name=?", (int(account_id), folder_name))
                    conn.commit()
                finally:
                    conn.close()
        logger.info(f"Post supprimé: {platform}/{folder_name}")
        return {"success": True}
    except Exception as e:
        logger.exception(f"Erreur suppression post: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - GESTION CONTENU
# ══════════════════════════════════════════════════════════════════

@router.get("/content")
async def api_content_list(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
        # ── Vérifier que l'utilisateur a accès à ce compte ──
        allowed = _get_user_account_ids(request)
        if allowed is not None and account_id not in allowed:
            return {"posts": [], "count": 0, "error": "Accès non autorisé à ce compte"}
        _sync_folders_to_db(platform, account_id)
    
    target_dir = _get_content_dir(platform, account_id)
    db_path = PLATFORM_DB.get(platform)
    results = []
    if not db_path or not Path(db_path).exists():
        return {"posts": results, "count": 0}
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if account_id:
            cursor.execute(
                "SELECT id, folder_name, persona, status, published, has_image, has_reel, created_at FROM posts WHERE account_id=? ORDER BY id DESC",
                (account_id,)
            )
            posts = cursor.fetchall()
            for p in posts:
                params = f"?platform={platform}&account_id={account_id}"
                folder_path = target_dir / p["folder_name"]
                
                # Cleanup: Ignorer et supprimer les posts "fantômes" (dossier supprimé physiquement)
                if not folder_path.exists():
                    try:
                        # Exécuter la suppression dans une transaction silencieuse
                        conn.execute("DELETE FROM posts WHERE id=?", (p["id"],))
                        conn.commit()
                    except Exception:
                        pass
                    continue
                
                # Prefer metadata (multi-image) detection, fallback to legacy filename search
                meta = _read_post(folder_path) if folder_path.exists() else {}
                has_image_meta = bool(meta.get("has_image"))
                has_image_physically = has_image_meta or (_find_file_recursive(folder_path, _IMAGE_FILES) is not None if folder_path.exists() else False)
                has_reel_physically = _find_file_recursive(folder_path, _REEL_FILES) is not None if folder_path.exists() else False
                
                results.append({
                    "folder": p["folder_name"],
                    "persona": p["persona"],
                    "status": p["status"],
                    "date": p["created_at"][:10] if p["created_at"] else p["folder_name"][:10],
                    "ai_responses": meta.get("ai_responses"),
                    "published": bool(p["published"]),
                    "image_url": f"/api/image/{p['folder_name']}{params}" if has_image_physically else None,
                    "reel_url": f"/api/reel/{p['folder_name']}{params}" if has_reel_physically else None
                })
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching content: {e}")
        
    return {"posts": results, "count": len(results)}

@router.get("/content/{folder}")
async def api_content_detail(request: Request, folder: str):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    target_dir = _get_content_dir(platform, account_id)
    f = _safe_folder(target_dir, folder)
    if not f.exists():
        raise HTTPException(status_code=404, detail="Post introuvable")
        
    meta = _read_post(f)
    text_file = _find_file(f, _TEXT_FILES)
    content = text_file.read_text(encoding="utf-8") if text_file else ""
    
    # Prefer metadata (multi-image) detection, fallback to legacy filename search
    has_image_meta = bool(meta.get("has_image"))
    has_image_physically = has_image_meta or (_find_file_recursive(f, _IMAGE_FILES) is not None)
    has_reel_physically = _find_file_recursive(f, _REEL_FILES) is not None
    
    params = f"?platform={platform}"
    if account_id:
        params += f"&account_id={account_id}"
        
    return {
        "folder": folder,
        "content": content,
        "metadata": meta,
        "ai_responses": meta.get("ai_responses"),
        "image_url": f"/api/image/{folder}{params}" if has_image_physically else None,
        "reel_url": f"/api/reel/{folder}{params}" if has_reel_physically else None
    }

@router.post("/update_post")
async def api_update_post(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    body = await req.json()
    folder_name = body.get("folder")
    content = body.get("content")
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)

    if not folder.exists():
        # Fallback : résoudre l'account via la table posts (folder_name) puis re-tenter
        resolved = _resolve_folder_account(platform, folder_name)
        if resolved:
            account_id = resolved.get("account_id")
            target_dir = _get_content_dir(platform, account_id)
            folder = _safe_folder(target_dir, folder_name)

    if folder.exists():
        if content is not None:
            text_file = _find_file(folder, _TEXT_FILES) or (folder / "post_text.txt")
            text_file.write_text(content, encoding="utf-8")
            if account_id and account_id.isdigit():
                conn = _get_platform_db(platform)
                if conn:
                    try:
                        conn.execute("UPDATE posts SET content_text=? WHERE account_id=? AND folder_name=?", (content, int(account_id), folder_name))
                        conn.commit()
                    finally:
                        conn.close()
        if "ai_responses" in body:
            _save_meta(folder, {"ai_responses": body.get("ai_responses")})
        return {"success": True}
    return {"success": False, "error": "Dossier introuvable"}


@router.post("/reset_published")
async def api_reset_published(req: Request):
    """Remet un post publié en pending pour le republier."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        allowed = _get_user_account_ids(req)
        if allowed is not None and int(account_id) not in allowed:
            return {"success": False, "error": "Accès non autorisé à ce compte"}
    body = await req.json()
    folder_name = body.get("folder")
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)

    if folder.exists():
        _save_meta(folder, {"published": False, "status": "pending"})
        if account_id and account_id.isdigit():
            conn = _get_platform_db(platform)
            if conn:
                try:
                    conn.execute("UPDATE posts SET status='pending', published=0 WHERE account_id=? AND folder_name=?", (int(account_id), folder_name))
                    conn.commit()
                finally:
                    conn.close()
        return {"success": True}
    return {"success": False, "error": "Dossier introuvable"}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - MÉDIA (IMAGES ET REELS)
# ══════════════════════════════════════════════════════════════════

# Cache navigateur pour les médias : ETag/Last-Modified déjà envoyés par
# FileResponse ; le navigateur réutilise le cache 1h (304 si inchangé),
# et une régénération change le fichier → nouvel ETag → 200 nouvelle image.
_MEDIA_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600, must-revalidate"}

def _media_response(request: Request, file_path: Path):
    """FileResponse avec validation conditionnelle (304 si If-None-Match correspond).

    L'ETag reprend le calcul de Starlette (md5 de mtime+size) pour rester cohérent.
    Une régénération change mtime → nouvel ETag → 200 avec la nouvelle image.
    """
    st = file_path.stat()
    etag = '"%s"' % hashlib.md5(f"{int(st.st_mtime)}-{st.st_size}".encode(), usedforsecurity=False).hexdigest()
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        return Response(status_code=304, headers=_MEDIA_CACHE_HEADERS)
    return FileResponse(str(file_path), headers={**_MEDIA_CACHE_HEADERS, "ETag": etag})

@router.get("/image/{folder}")
async def api_get_image(request: Request, folder: str):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    target_dir = _get_content_dir(platform, account_id)
    f = _safe_folder(target_dir, folder)

    index = request.query_params.get("index")
    if index:
        meta = _read_post(f)
        images_meta = meta.get("images") if isinstance(meta.get("images"), list) else []
        try:
            idx = int(index) - 1
        except Exception:
            idx = None
        if idx is not None and 0 <= idx < len(images_meta):
            selected = images_meta[idx]
            image_file = Path(selected.get("filename", ""))
            if not image_file.is_absolute():
                image_file = f / image_file
            # Security: verify resolved path stays within f
            if not str(image_file.resolve()).startswith(str(f.resolve())):
                raise HTTPException(status_code=403, detail="Access denied")
            if image_file.exists():
                return _media_response(request, image_file)

    # Recherche récursive pour trouver l'image dans les sous-dossiers
    img = _find_file_recursive(f, _IMAGE_FILES)
    if img:
        return _media_response(request, img)
    raise HTTPException(status_code=404)

@router.get("/reel/{folder}")
async def api_get_reel(request: Request, folder: str):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    target_dir = _get_content_dir(platform, account_id)
    f = _safe_folder(target_dir, folder)
    
    logger.info(f"[reel] platform={platform}, account_id={account_id}, target_dir={target_dir}, folder={folder}")
    logger.info(f"[reel] full_path={f}, exists={f.exists()}")
    
    # Recherche récursive pour trouver le reel dans les sous-dossiers
    reel = _find_file_recursive(f, _REEL_FILES)
    logger.info(f"[reel] found={reel}")

    if reel:
        return _media_response(request, reel)
    raise HTTPException(status_code=404)


# ══════════════════════════════════════════════════════════════════
# ROUTES API - GÉNÉRATION
# ══════════════════════════════════════════════════════════════════

@router.get("/generate")
async def api_generate(request: Request, background_tasks: BackgroundTasks):
    persona = request.query_params.get("persona", "expert_ia")
    topic = request.query_params.get("topic", "")
    account_id = request.query_params.get("account_id")
    platform = request.query_params.get("platform", "facebook")
    media = request.query_params.get("media", "none")
    selected_image = request.query_params.get("selected_image")
    image_mode = request.query_params.get("image_mode", "as_is")
    
    import uuid
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder_name = f"{date_str}_{persona}_{uuid.uuid4().hex[:6]}"
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    folder.mkdir(parents=True, exist_ok=True)
    
    # Création du meta.json pour que les sous-agents aient le contexte complet
    meta_data = {
        "content_id": folder_name,
        "account_id": account_id,
        "platform": platform,
        "persona": persona,
        "topic": topic,
        "status": "generating",
        "created_at": datetime.now().isoformat(),
        "folder_path": str(folder.absolute()),
        "has_reel": persona == "reel",
        "has_image": media == "image"
    }

    if media == "existing_image":
        if not selected_image:
            return {"success": False, "error": "Veuillez sélectionner une image existante."}
        library_file = LIBRARY_IMAGES_DIR / Path(selected_image).name
        if not library_file.exists():
            return {"success": False, "error": "Image existante introuvable dans la librairie."}
        ext = library_file.suffix.lower() or ".jpg"
        std_name = f"post_image{ext}"
        shutil.copy2(library_file, folder / std_name)
        meta_data["has_image"] = True
        meta_data["image_source"] = "library"
        meta_data["selected_image"] = std_name
        meta_data["image_mode"] = image_mode

    (folder / "meta.json").write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    if account_id and account_id.isdigit() and persona != "reel":
        conn = _get_platform_db(platform)
        if conn:
            try:
                conn.execute("""
                    INSERT INTO posts (account_id, folder_name, persona, topic, status)
                    VALUES (?, ?, ?, ?, 'generating')
                """, (int(account_id), folder_name, persona, topic))
                conn.commit()
            finally:
                conn.close()
                
    import uuid
    from core.task_tracker import create_task
    
    # Créer le task_id ici pour le retourner au frontend
    task_id = create_task(persona, f"gen_{uuid.uuid4().hex[:8]}", f"Génération {persona}: {topic[:30]}...")
            
    # Lancement en arrière-plan
    background_tasks.add_task(_background_generate, str(folder), persona, topic, account_id, platform, media, task_id, image_mode)
    
    return {"success": True, "message": "Génération démarrée en arrière-plan", "folder": folder_name, "task_id": task_id}

@router.get("/suggest_image")
async def api_suggest_image(request: Request):
    """Propose un concept d'image pour un topic/persona via LLM."""
    topic = request.query_params.get("topic", "")
    persona = request.query_params.get("persona", "")
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if not topic:
        return {"success": False, "error": "Sujet manquant"}
    try:
        from core.llm_router import call_llm
        system = (
            "Tu es un directeur artistique pour les réseaux sociaux. "
            "Propose une idée d'image/concept visuel pour un post. "
            "Réponds en français, en 1-2 phrases concises, sous forme de description utilisable comme prompt image."
        )
        prompt = f"Post {platform} sur : {topic}\nPersona: {persona}\nPropose le concept d'image idéal (style, composition, ambiance, texte éventuel) :"
        text, metadata = call_llm(system, prompt)
        concept = text if text else "Aucune suggestion générée"
        return {"success": True, "concept": concept, "provider": (metadata or {}).get("provider")}
    except Exception as e:
        logger.exception(f"Erreur suggest_image: {e}")
        return {"success": False, "error": str(e)}

@router.get("/library_images")
async def api_library_images():
    files = []
    for path in sorted(LIBRARY_IMAGES_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
            files.append({"name": path.name, "url": f"/api/library_image/{path.name}"})
    return {"success": True, "images": files}

@router.post("/upload_library_image")
async def api_upload_library_image(file: UploadFile = File(...)):
    if not file.filename:
        return {"success": False, "error": "Aucun fichier"}
    ext = Path(file.filename).suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return {"success": False, "error": "Format non supporté"}
    image_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
    upload_path = LIBRARY_IMAGES_DIR / image_name
    uploaded_size = 0
    with upload_path.open('wb') as out_file:
        while chunk := file.file.read(8192):
            uploaded_size += len(chunk)
            if uploaded_size > MAX_UPLOAD_SIZE:
                upload_path.unlink(missing_ok=True)
                return {"success": False, "error": f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE // (1024*1024)}MB)"}
            out_file.write(chunk)
    return {"success": True, "name": image_name, "url": f"/api/library_image/{image_name}"}

@router.get("/library_images/")
async def api_library_images_slash():
    return await api_library_images()

@router.get("/library_image/{filename}")
async def api_library_image(filename: str):
    safe_name = Path(filename).name
    file_path = LIBRARY_IMAGES_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image introuvable")
    return FileResponse(str(file_path))

@router.post("/replace_image")
async def api_replace_image(
    folder: str = Form(...),
    source: str = Form("library"),
    selected_image: Optional[str] = Form(None),
    file: UploadFile = File(None),
    platform: str = Query("facebook"),
    account_id: Optional[str] = Query(None),
):
    target_dir = _get_content_dir(platform, account_id)
    post_folder = _safe_folder(target_dir, folder)
    if not post_folder.exists() or not post_folder.is_dir():
        return {"success": False, "error": "Dossier introuvable"}

    # Supprimer les anciennes images dans le post
    for img_name in _IMAGE_FILES:
        if (post_folder / img_name).exists():
            (post_folder / img_name).unlink()
    if (post_folder / "images").exists():
        for existing in (post_folder / "images").iterdir():
            if existing.is_file():
                existing.unlink()

    image_name = None
    if source == "library":
        if not selected_image:
            return {"success": False, "error": "Aucune image sélectionnée"}
        library_file = LIBRARY_IMAGES_DIR / Path(selected_image).name
        if not library_file.exists():
            return {"success": False, "error": "Image introuvable dans la librairie"}
        ext = library_file.suffix.lower() or ".jpg"
        image_name = f"post_image{ext}"
        shutil.copy2(library_file, post_folder / image_name)
        source_type = "library"
    elif source == "upload":
        if not file:
            return {"success": False, "error": "Aucun fichier uploadé"}
        orig_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
        upload_path = LIBRARY_IMAGES_DIR / orig_name
        uploaded_size = 0
        with upload_path.open('wb') as out_file:
            while chunk := file.file.read(8192):
                uploaded_size += len(chunk)
                if uploaded_size > MAX_UPLOAD_SIZE:
                    upload_path.unlink(missing_ok=True)
                    return {"success": False, "error": f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE // (1024*1024)}MB)"}
                out_file.write(chunk)
        ext = Path(file.filename).suffix.lower() or ".jpg"
        image_name = f"post_image{ext}"
        shutil.copy2(upload_path, post_folder / image_name)
        source_type = "upload"
    else:
        return {"success": False, "error": "Source d'image inconnue"}

    _save_meta(post_folder, {
        "has_image": True,
        "image_source": source_type,
        "selected_image": image_name,
        "images": [],
        "image_url": "",
        "post_image": image_name,
        "published": False,
        "status": "pending"
    })
    if account_id and account_id.isdigit():
        _sync_folders_to_db(platform, int(account_id))

    params = f"?platform={platform}"
    if account_id:
        params += f"&account_id={account_id}"
    image_url = f"/api/image/{folder}{params}"
    return {"success": True, "message": "Image remplacée.", "image_url": image_url}


def _is_photography_persona(persona: str, account_id: str = None, platform: str = "facebook") -> bool:
    """
    Détermine si un persona est de type 'photography' (Visual-First).
    Cherche dans le dossier du compte spécifié, ou dans tous les comptes connus si non trouvé.
    """
    acc_str = str(account_id) if account_id else "2"
    # Cherche d'abord dans la plateforme courante
    platform_base = Path(f"d:/Content_Machine/machines/{platform}_machine")
    if not platform_base.exists():
        platform_base = Path("d:/Content_Machine/machines/facebook_machine")
    
    config_path = platform_base / "accounts" / acc_str / "persona" / persona / "config.md"
    
    # Fallback: cherche dans les autres comptes connus (photo personas dans compte 2)
    if not config_path.exists():
        for fallback_acc in ["2", "1", "3"]:
            fallback = platform_base / "accounts" / fallback_acc / "persona" / persona / "config.md"
            if fallback.exists():
                config_path = fallback
                break

    if not config_path.exists():
        logger.debug(f"[PHOTOGRAPHER DETECT] config not found for persona='{persona}' acc='{acc_str}'")
        return False
    
    try:
        content = config_path.read_text(encoding="utf-8")
        result = "Type: photography" in content
        logger.info(f"[PHOTOGRAPHER DETECT] persona='{persona}' -> is_photography={result} (path={config_path})")
        return result
    except Exception as e:
        logger.warning(f"[PHOTOGRAPHER DETECT] Error reading config: {e}")
        return False


async def _background_generate(folder_path: str, persona: str, topic: str, account_id: str, platform: str, media: str, task_id: str = None, image_mode: str = "as_is"):
    """Génération en arrière-plan. Si persona=='reel', délègue à process_reel (moteur vidéo)."""
    from core.task_tracker import update_task
    
    # ─── CAS REEL : router vers le moteur vidéo ──────────────────────────────
    if persona == "reel":
        if str(FB_MACHINE) not in sys.path:
            sys.path.insert(0, str(FB_MACHINE))
        from agents.scheduler.agent import process_reel

        if task_id:
            update_task(task_id, progress=10, status="running", log="Démarrage du générateur vidéo (3-5 min)...")

        plan_entry = {
            "persona": "reel",
            "sujet": topic or "Sujet de reel",
        }
        date_str = datetime.now().strftime("%Y-%m-%d")
        acc_int = int(account_id) if account_id and str(account_id).isdigit() else None

        try:
            # On passe le folder_path directement
            result = process_reel(plan_entry, date_str, False, task_id=task_id, current=1, total=1,
                                  account_id=acc_int, platform=platform, folder_path=folder_path)
            if result.success:
                if acc_int:
                    _sync_folders_to_db(platform, acc_int)
                update_task(task_id, progress=100, status="completed", message="Reel généré avec succès !")
                logger.info(f"[GENERATE/REEL] Reel généré : {result.data}")
            else:
                err = getattr(result, 'error_cause', 'Erreur inconnue')
                update_task(task_id, status="failed", message=err)
                logger.error(f"[GENERATE/REEL] Échec : {err}")
        except Exception as e:
            logger.exception(f"[GENERATE/REEL] Exception : {e}")
            try:
                update_task(task_id, status="failed", message=str(e))
            except Exception:
                pass
        return  # Ne pas continuer vers le copywriter

    # ─── CAS STANDARD : texte + image optionnelle ou VISUAL-FIRST (photographer) ───
    if str(FB_MACHINE) not in sys.path:
        sys.path.insert(0, str(FB_MACHINE))
    
    image_failed = False
    res = None
        
    try:
        # ROUTAGE VISUEL-FIRST : vérification prioritaire
        if _is_photography_persona(persona, account_id, platform):
            logger.info(f"[GENERATE] VISUAL-FIRST détecté pour '{persona}' → agent Photographer")
            if task_id:
                from core.task_tracker import update_task
                update_task(task_id, progress=30, status="running", log="📸 Shooting photo IA en cours...")
            
            from shared_agents.photographer.agent import run_photographer
            res = run_photographer(folder_path)
            
            # Texte de légende pour l'onglet validation
            post_path = Path(folder_path) / f"{platform}_post.txt"
            post_path.write_text(f"📸 Visuels générés (Style: {persona}). Prêt pour validation.", encoding="utf-8")
            
            # Sync DB pour que la photo apparaîsse dans l'onglet Validation
            if account_id and str(account_id).isdigit():
                _sync_folders_to_db(platform, int(account_id))
            
            if task_id:
                status = "completed" if res.success else "failed"
                msg = "Visuels générés avec succès !" if res.success else getattr(res, "error_cause", "Echec")
                update_task(task_id, progress=100, status=status, message=msg, log="Terminé!")
            return

        # ROUTAGE TEXTE-FIRST : copywriter + image optionnelle
        from agents.copywriter.agent import run_copywriter
        from core.llm_router import get_account_llm_config
        llm_cfg = get_account_llm_config(platform, account_id)
        res = run_copywriter(folder_path, {"persona": persona, "sujet": topic}, task_id=task_id, account_id=account_id, platform=platform, model=llm_cfg.get("model"), llm_config=llm_cfg)
        
        image_failed = False
        if res.success and media == "image":
            if task_id:
                from core.task_tracker import update_task
                update_task(task_id, progress=70, log="Génération de l'image (cela peut prendre 1 min)...")
            try:
                from agents.image_creator.agent import run_image_creator
                img_res = run_image_creator(folder_path, platform=platform, account_id=account_id)
                if not img_res.success:
                    image_failed = True
                    logger.warning(f"[BACKGROUND] Image_creator a échoué: {getattr(img_res, 'error_cause', 'inconnu')}")
            except Exception as img_err:
                image_failed = True
                logger.exception(f"[BACKGROUND] Exception image_creator: {img_err}")
            if task_id:
                status_msg = "Génération terminée avec image" if not image_failed else "Texte généré, image échouée"
                from core.task_tracker import update_task
                update_task(task_id, progress=100, status="completed", message=status_msg, log="Terminé!")
        elif res.success and media == "existing_image" and image_mode == "modify":
            if task_id:
                from core.task_tracker import update_task
                update_task(task_id, progress=70, log="Modification de l'image existante par l'IA...")
            meta_file = Path(folder_path) / "meta.json"
            existing_img_name = ""
            if meta_file.exists():
                try:
                    import json as _json
                    m = _json.loads(meta_file.read_text(encoding="utf-8"))
                    existing_img_name = m.get("selected_image", "")
                except Exception:
                    pass
            existing_img_path = str(Path(folder_path) / existing_img_name) if existing_img_name else None
            try:
                if existing_img_path and Path(existing_img_path).exists():
                    from agents.image_creator.agent import run_image_creator
                    img_res = run_image_creator(folder_path, platform=platform, account_id=account_id, existing_image_path=existing_img_path)
                    if not img_res.success:
                        image_failed = True
                        logger.warning(f"[BACKGROUND] Image modify a échoué: {getattr(img_res, 'error_cause', 'inconnu')}")
                else:
                    image_failed = True
                    logger.warning(f"[BACKGROUND] Image existante introuvable: {existing_img_path}")
            except Exception as img_err:
                image_failed = True
                logger.exception(f"[BACKGROUND] Exception modify image: {img_err}")
            if task_id:
                status_msg = "Génération terminée avec image modifiée" if not image_failed else "Texte généré, modification image échouée"
                from core.task_tracker import update_task
                update_task(task_id, progress=100, status="completed", message=status_msg, log="Terminé!")
        elif res.success and media == "existing_image":
            # mode as_is : image déjà copiée, pas de modification IA nécessaire
            image_failed = False
            if task_id:
                from core.task_tracker import update_task
                update_task(task_id, progress=100, status="completed", message="Génération terminée (image conservée telle quelle)", log="Terminé!")
    except Exception as e:
        logger.exception(f"Erreur lors de la génération standard: {e}")
        if task_id:
            from core.task_tracker import update_task
            update_task(task_id, status="failed", message=str(e))
        return
        
    # Mise à jour du statut final dans la DB
    if account_id and account_id.isdigit():
        conn = _get_platform_db(platform)
        if conn:
            try:
                folder_name = Path(folder_path).name
                if res and res.success:
                    text_file = _find_file(Path(folder_path), _TEXT_FILES)
                    content = text_file.read_text(encoding="utf-8") if text_file else ""
                    img_failed_val = 1 if image_failed else 0
                    conn.execute("UPDATE posts SET status='pending', content_text=?, image_failed=? WHERE account_id=? AND folder_name=?", (content, img_failed_val, int(account_id), folder_name))
                else:
                    conn.execute("UPDATE posts SET status='failed' WHERE account_id=? AND folder_name=?", (int(account_id), folder_name))
                conn.commit()
            finally:
                conn.close()

@router.get("/generate_reel")
async def api_generate_reel_endpoint(request: Request):
    """
    Endpoint pour lancer la génération d'un reel en arrière-plan.
    """
    topic = request.query_params.get("topic", "")
    context = request.query_params.get("context", "")
    script = request.query_params.get("script", "")
    objectif = request.query_params.get("objectif", "")
    audience = request.query_params.get("audience", "")
    publish = request.query_params.get("publish", "false")
    account_id_str = request.query_params.get("account_id")
    platform = request.query_params.get("platform", "facebook")
    
    account_id = None
    if account_id_str and account_id_str.isdigit():
        account_id = int(account_id_str)

    import threading
    import uuid
    from datetime import datetime
    from core.task_tracker import create_task, update_task

    publish_bool = publish.lower() == "true"
    logger.info(f"[GENERATE_REEL] Topic: {topic[:50]}...")
    
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder_name = f"{date_str}_reel_{uuid.uuid4().hex[:6]}"
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    folder.mkdir(parents=True, exist_ok=True)
    
    # Création du meta.json
    meta_data = {
        "content_id": folder_name,
        "account_id": account_id,
        "platform": platform,
        "persona": "reel",
        "topic": topic,
        "status": "generating",
        "created_at": datetime.now().isoformat(),
        "folder_path": str(folder.absolute()),
        "has_reel": True,
        "has_image": False
    }
    import json
    (folder / "meta.json").write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    if account_id:
        conn = _get_platform_db(platform)
        if conn:
            try:
                conn.execute("""
                    INSERT INTO posts (account_id, folder_name, persona, topic, status)
                    VALUES (?, ?, 'reel', ?, 'generating')
                """, (account_id, folder_name, topic))
                conn.commit()
            finally:
                conn.close()

    # Create task_id BEFORE launching thread so we can return it
    task_id = create_task("reel", f"reel_{uuid.uuid4().hex[:8]}", f"Reel: {topic[:30]}...")
    logger.info(f"[GENERATE_REEL] Task created: {task_id}")

    def run_reel(folder_path_str: str):
        try:
            update_task(task_id, progress=10, status="running", log="Starting (3-5 min)...")
            
            # Utiliser l'agent du facebook_machine qui gère correctement les UUIDs et meta.json
            import sys
            if str(FB_MACHINE) not in sys.path:
                sys.path.insert(0, str(FB_MACHINE))
            from agents.scheduler.agent import process_reel
            
            plan_entry = {
                "persona": "reel",
                "sujet": topic or "Sujet de reel",
                "context": context,
                "script": script,
                "objectif": objectif,
                "audience": audience
            }
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            update_task(task_id, progress=30, log="Generating reel...")
            
            logger.info(f"[GENERATE_REEL] Calling process_reel...")
            result = process_reel(plan_entry, date_str, publish_bool, task_id=task_id, current=1, total=1, account_id=account_id, platform=platform, folder_path=folder_path_str)
            logger.info(f"[GENERATE_REEL] Result: success={result.success}")
            
            if result.success:
                # Update status to pending
                if account_id:
                    conn = _get_platform_db(platform)
                    if conn:
                        try:
                            conn.execute("UPDATE posts SET status='pending' WHERE account_id=? AND folder_name=?", (account_id, folder_name))
                            conn.commit()
                        finally:
                            conn.close()
                    _sync_folders_to_db(platform, account_id)
                    logger.info(f"[GENERATE_REEL] Synced folders to DB for platform={platform}, account_id={account_id}")
                update_task(task_id, progress=100, status="completed", message="Reel generated!")
            else:
                if account_id:
                    conn = _get_platform_db(platform)
                    if conn:
                        try:
                            conn.execute("UPDATE posts SET status='failed' WHERE account_id=? AND folder_name=?", (account_id, folder_name))
                            conn.commit()
                        finally:
                            conn.close()
                error_msg = getattr(result, 'error_cause', 'Unknown error')
                logger.error(f"[GENERATE_REEL] Error: {error_msg}")
                update_task(task_id, status="failed", message=error_msg)
                
        except Exception as e:
            logger.exception(f"[GENERATE_REEL] Thread error: {e}")
            if task_id:
                try:
                    update_task(task_id, status="failed", message=str(e))
                except Exception:
                    logger.warning(f"Failed to update task {task_id}")

    thread = threading.Thread(target=run_reel, args=(str(folder.absolute()),), daemon=True)
    thread.start()

    return {
        "success": True,
        "task_id": task_id,
        "message": "Reel generation started in background (3-5 min). Track progress on Dashboard."
    }

@router.post("/run_command")
async def api_run_command(req: Request):
    body = await req.json()
    command = body.get("command", "")
    timeout = min(body.get("timeout", 120), 300)  # cap at 5min

    import re as _re
    import shlex

    # Whitelist of allowed command patterns (exact match after parsing)
    ALLOWED_COMMANDS = {
        ("python", "agents/topic_finder/agent.py"),
        ("python", "agents/scheduler/agent.py"),
    }

    try:
        parts = tuple(shlex.split(command))
    except ValueError:
        return {"success": False, "error": "Commande mal formatee"}

    # Verify command starts with an allowed prefix
    allowed = False
    for prefix in ALLOWED_COMMANDS:
        if parts[:len(prefix)] == prefix:
            allowed = True
            break

    if not allowed:
        return {"success": False, "error": f"Commande non autorisee"}

    # Reject shell metacharacters
    if _re.search(r'[;&|`$!<>]', command):
        return {"success": False, "error": "Caracteres interdits dans la commande"}

    try:
        result = subprocess.run(list(parts), shell=False, cwd=str(FB_MACHINE), capture_output=True, text=True, timeout=timeout)
        return {
            "success": result.returncode == 0,
            "output": result.stdout[-MAX_OUTPUT_CHARS:],
            "error": result.stderr[-300:],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)"}
    except Exception as e:
        logger.error(f"[run_command] {e}")
        return {"success": False, "error": "Erreur interne"}

@router.post("/generate_batch")
async def api_generate_batch(req: Request):
    body = await req.json()
    date = body.get("date", "today")
    account_id_param = body.get("account_id")
    platform = body.get("platform", "facebook")
    
    account_id = int(account_id_param) if account_id_param and str(account_id_param).isdigit() else None
    lock_file = DATA_DIR / f"batch_{date}.lock"
    
    def run_batch():
        import threading
        import uuid
        try:
            lock_file.touch()
            from core.task_tracker import create_task, update_task
            task_id = create_task("batch", f"batch_{uuid.uuid4().hex[:8]}", "Génération du batch complet")
            update_task(task_id, progress=5, status="running", log="Démarrage du pipeline")
            
            from agents.scheduler.agent import run_pipeline
            from machines.facebook_machine.agents.scheduler.agent import _run_pipeline_for_account
            
            # Si account_id et platform spécifiés, exécuter pour ce compte uniquement
            if account_id:
                res = _run_pipeline_for_account(account_id, platform, "all", False, date, task_id)
            else:
                res = run_pipeline("all", False, date=date, task_id=task_id)
            
            if res.success:
                total = res.data.get("total", 100)
                success = res.data.get("success", total)
                update_task(task_id, progress=100, status="completed", message=f"Terminé: {success}/{total} posts générés")
                # Sync folders to DB after batch generation
                if account_id:
                    _sync_folders_to_db(platform, account_id)
                    logger.info(f"[BATCH] Synced folders to DB for platform={platform}, account_id={account_id}")
            else:
                update_task(task_id, status="failed", message=getattr(res, 'error_cause', 'Erreur batch'))
        except Exception as e:
            logger.exception(f"Erreur batch fatale: {e}")
        finally:
            if lock_file.exists():
                lock_file.unlink()
    
    import threading
    threading.Thread(target=run_batch, daemon=True).start()
    return {"started": True, "message": "Batch démarré en arrière-plan"}


@router.get("/batch_status")
async def api_batch_status(date: str = "today"):
    lock_file = DATA_DIR / f"batch_{date}.lock"
    result = {"running": lock_file.exists(), "date": date}
    
    from core.task_tracker import get_active_tasks
    active = get_active_tasks()
    batch_tasks = [t for t in active if t.get("type") == "batch"]
    if batch_tasks:
        result["task"] = batch_tasks[0]
    
    return result


@router.get("/llm_status")
async def api_llm_status():
    """Retourne le statut des providers LLM : Groq et Ollama."""
    import os
    status = {}

    # ── Groq ──────────────────────────────────────────────────────────────────
    try:
        from core.groq_router import get_available_keys_status
        groq_keys = get_available_keys_status()
        available_count = sum(1 for k in groq_keys if k["available"])
        status["groq"] = {
            "configured": len(groq_keys) > 0,
            "keys_total": len(groq_keys),
            "keys_available": available_count,
            "keys": groq_keys,
            "active": True,
        }
    except Exception as e:
        status["groq"] = {"configured": False, "error": str(e)}

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        import requests as req_lib
        r = req_lib.get(f"{ollama_url}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        status["ollama"] = {"running": True, "url": ollama_url, "models": models[:5]}
    except Exception:
        status["ollama"] = {"running": False, "url": ollama_url}

    # Provider actif
    if status.get("groq", {}).get("keys_available", 0) > 0:
        status["primary"] = "groq"
    elif status.get("ollama", {}).get("running"):
        status["primary"] = "ollama"
    else:
        status["primary"] = "none"

    # ── Catalogue providers (multi-fournisseurs) ────────────────────────────
    try:
        from core.llm_router import get_status as llm_get_status
        status["providers"] = llm_get_status()
    except Exception as e:
        status["providers"] = {"error": str(e)}

    return status


@router.get("/llm/models")
async def api_llm_models():
    """Catalogue des modèles d'IA sélectionnables, groupé par fournisseur."""
    try:
        from core.llm_router import list_models
        models = list_models()
        from core.llm_router import get_default_model
        return {"success": True, "groups": models, "default_model": get_default_model()}
    except Exception as e:
        logger.error(f"Erreur /api/llm/models: {e}")
        return {"success": False, "error": str(e), "groups": []}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - RÉGÉNÉRATION
# ══════════════════════════════════════════════════════════════════

@router.post("/regenerate_post")
async def api_regenerate_post(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    body = await req.json()
    folder_name = body.get("folder", "")
    indication = body.get("indication", "")  # note optionnelle utilisateur
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    meta = _read_post(folder)
    persona = meta.get("persona", "expert_ia")
    topic = meta.get("topic", "")
    account_id_from_meta = meta.get("account_id") or account_id
    # ── Sauvegarde du image_prompt avant régénération ──
    original_image_prompt = meta.get("image_prompt", "")
    
    # ROUTAGE : photography ou texte classique ?
    if _is_photography_persona(persona, account_id_from_meta, platform):
        logger.info(f"[REGENERATE_POST] VISUAL-FIRST pour '{persona}' → Photographer")
        try:
            from shared_agents.photographer.agent import run_photographer
            res = run_photographer(str(folder))
            if res.success:
                return {"success": True, "content": "📸 Nouvelle image générée. Consultez l'onglet validation."}
            return {"success": False, "error": getattr(res, "error_cause", "Echec Photographer")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    try:
        from agents.copywriter.agent import run_copywriter
        from core.llm_router import get_account_llm_config
        plan_entry = {"persona": persona, "sujet": topic}
        if indication:
            plan_entry["indication"] = indication  # injection indication
        llm_cfg = get_account_llm_config(platform, account_id_from_meta)
        res = run_copywriter(str(folder), plan_entry, account_id=account_id_from_meta, platform=platform, model=llm_cfg.get("model"), llm_config=llm_cfg)
        
        if res.success:
            # Réinjection de l'image_prompt original si le LLM ne l'a pas fourni
            meta_after_path = folder / "meta.json"
            try:
                import json as _json
                meta_after = _json.loads(meta_after_path.read_text(encoding="utf-8"))
                if not meta_after.get("image_prompt") and original_image_prompt:
                    meta_after["image_prompt"] = original_image_prompt
                    meta_after_path.write_text(_json.dumps(meta_after, indent=2, ensure_ascii=False), encoding="utf-8")
                    logger.info(f"[REGENERATE_POST] image_prompt original préservé dans {folder_name}")
            except Exception as e_meta:
                logger.warning(f"[REGENERATE_POST] Impossible de vérifier/réinjecter image_prompt: {e_meta}")
            
            text_file = _find_file(folder, _TEXT_FILES)
            content = text_file.read_text(encoding="utf-8") if text_file else ""
            return {"success": True, "content": content}
        return {"success": False, "error": getattr(res, "error_cause", "Impossible de régénérer")}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/regenerate_image")
async def api_regenerate_image(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    body = await req.json()
    folder_name = body.get("folder", "")
    hint = body.get("indication", "")  # note optionnelle utilisateur pour le style visuel
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    task_id = create_task("image_creator", message=f"Régénération image pour {folder_name}")
    
    def _run():
        try:
            update_task(task_id, progress=10, status="running", log="Suppression de l'ancienne image...")
            for img_name in _IMAGE_FILES:
                if (folder / img_name).exists():
                    (folder / img_name).unlink()
            if (folder / "images").exists():
                for existing in (folder / "images").iterdir():
                    if existing.is_file():
                        existing.unlink()

            update_task(task_id, progress=30, log="Appel à l'agent Image Creator (Gemini/Playwright)...")
            meta = _read_post(folder)
            persona = meta.get("persona", "")
            account_id_from_meta = meta.get("account_id") or account_id
            if _is_photography_persona(persona, account_id_from_meta, platform):
                from shared_agents.photographer.agent import run_photographer
                res = run_photographer(str(folder))
            else:
                from agents.image_creator.agent import run_image_creator
                res = run_image_creator(str(folder), platform=platform, hint=hint if hint else None, account_id=account_id)
            
            if res.success:
                _save_meta(folder, {"has_image": True})
                # Sync to DB after regeneration
                if account_id and account_id.isdigit():
                    _sync_folders_to_db(platform, int(account_id))
                update_task(task_id, progress=100, status="completed", message="Image régénérée avec succès.")
            else:
                update_task(task_id, status="failed", message=getattr(res, "error_cause", "Erreur création image"))
        except Exception as e:
            update_task(task_id, status="failed", message=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"success": True, "task_id": task_id, "message": "Régénération d'image lancée."}

@router.post("/regenerate_reel")
async def api_regenerate_reel(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    body = await req.json()
    folder_name = body.get("folder", "")
    target_dir = _get_content_dir(platform, account_id)
    folder = _safe_folder(target_dir, folder_name)
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    task_id = create_task("video_maker", message=f"Régénération reel pour {folder_name}")

    def _run():
        try:
            update_task(task_id, progress=10, status="running", log="Suppression de l'ancien reel...")
            for reel_name in _REEL_FILES:
                if (folder / reel_name).exists(): (folder / reel_name).unlink()
            
            update_task(task_id, progress=40, log="Appel à l'agent Video Maker...")
            from shared_agents.video_maker.agent import run_video_maker
            res = run_video_maker(str(folder))
            
            if res.success:
                _save_meta(folder, {"has_reel": True})
                update_task(task_id, progress=100, status="completed", message="Reel régénéré avec succès.")
            else:
                update_task(task_id, status="failed", message=getattr(res, "error_cause", "Erreur config reel"))
        except Exception as e:
            update_task(task_id, status="failed", message=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"success": True, "task_id": task_id, "message": "Régénération de reel lancée."}


# ══════════════════════════════════════════════════════════════════
# ROUTES PERSONAS — Detail, save, prompt, exemples, AND LIST
# ══════════════════════════════════════════════════════════════════

PERSONAS_DIR = Config.PERSONAS_DIR


def _get_platform_db(platform: str):
    """Retourne une connexion SQLite à la DB de la plateforme."""
    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        return None
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_folder_account(platform: str, folder_name: str) -> dict:
    """Retrouve l'account d'un folder via la table posts de la plateforme."""
    if not folder_name:
        return {}
    conn = _get_platform_db(platform)
    if not conn:
        return {}
    try:
        cursor = conn.execute("SELECT account_id FROM posts WHERE folder_name=?", (folder_name,))
        row = cursor.fetchone()
        if row and row["account_id"]:
            return {"account_id": str(row["account_id"])}
    except Exception:
        pass
    finally:
        conn.close()
    return {}


def _get_account_settings(platform: str, account_id: int):
    if not account_id:
        return {}
    conn = _get_platform_db(platform)
    if not conn:
        return {}
    try:
        cursor = conn.execute("SELECT settings FROM accounts WHERE id=?", (account_id,))
        acc = cursor.fetchone()
        if not acc or not acc["settings"]:
            return {}
        try:
            return json.loads(acc["settings"])
        except Exception:
            return {}
    finally:
        conn.close()


def _get_account_credentials(platform: str, account_id: int) -> dict:
    """Retourne les credentials (page_id, access_token) d'un compte depuis la DB plateforme."""
    if not account_id:
        return {}
    conn = _get_platform_db(platform)
    if not conn:
        return {}
    try:
        cursor = conn.execute("SELECT credentials FROM accounts WHERE id=?", (account_id,))
        acc = cursor.fetchone()
        if not acc or not acc["credentials"]:
            return {}
        try:
            return json.loads(acc["credentials"])
        except Exception:
            return {}
    finally:
        conn.close()


def _get_publisher(platform: str):
    """Retourne la fonction de publication pour la plateforme."""
    logger.info(f"[_get_publisher] Loading publisher for platform: {platform}")
    try:
        if platform == "facebook":
            import importlib.util
            spec = importlib.util.spec_from_file_location("fb_publisher", str(FB_MACHINE / "agents" / "publisher" / "agent.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            original_run = module.run_publisher
            def run_publisher(folder_path: str, account_id: int = None, credentials: dict = None):
                return original_run(folder_path, account_id=account_id, credentials=credentials)
            return run_publisher
            
        elif platform == "linkedin":
            import importlib.util
            spec = importlib.util.spec_from_file_location("li_publisher", str(LI_MACHINE / "agents" / "agent_publisher.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            post_linkedin = module.post_linkedin
            
            def run_publisher(folder_path: str, account_id: int = None, credentials: dict = None, force_text_only: bool = False):
                from shared_agents.models import AgentResult
                result = post_linkedin(folder_path, account_id=account_id, credentials=credentials, force_text_only=force_text_only)
                logger.info(f"[li_publisher] raw result: {repr(result)}, bool: {bool(result)}")

                # Confirmation demandée (image non attachée) -> propager le dict au route
                if isinstance(result, dict) and result.get("needs_confirmation"):
                    return result

                # Use bool() instead of direct == comparison
                if bool(result):
                    logger.info(f"[li_publisher] Returning AgentResult.ok()")
                    return AgentResult.ok()
                else:
                    logger.error(f"LinkedIn publish failed for {folder_path}: result={result}")
                    # Utiliser LAST_ERROR du module pour un message détaillé
                    last_err = getattr(module, "LAST_ERROR", "")
                    if last_err:
                        return AgentResult.fail(f"LinkedIn: {last_err}")
                    # Fallback: diagnostic credentials
                    try:
                        import sys as _sys
                        _sys.path.insert(0, str(LI_MACHINE))
                        from agents.agent_publisher import get_linkedin_credentials
                        _t, _u = get_linkedin_credentials(account_id)
                        detail = "token OK" if _t else "token MANQUANT"
                        detail += ", user_id OK" if _u else ", user_id MANQUANT"
                    except Exception:
                        detail = "diagnostic impossible"
                    return AgentResult.fail(f"Publication LinkedIn échouée ({detail}) - vérifiez credentials et linkedin_post.txt")
            return run_publisher
            
        elif platform == "twitter":
            import importlib.util
            spec = importlib.util.spec_from_file_location("tw_publisher", str(TW_MACHINE / "agents" / "agent_publisher.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            post_twitter = module.post_twitter
            
            def run_publisher(folder_path: str, account_id: int = None, credentials: dict = None):
                from shared_agents.models import AgentResult
                result = post_twitter(folder_path, account_id=account_id, credentials=credentials)
                if bool(result):
                    return AgentResult.ok()
                else:
                    logger.error(f"Twitter publish failed for {folder_path}: result={result}")
                    return AgentResult.fail(f"Publication Twitter échouée - vérifiez credentials et le fichier content")
            return run_publisher
            
    except Exception as e:
        logger.error(f"Error loading publisher for {platform}: {e}")
        return None


def _get_copywriter():
    """Retourne la fonction copywriter depuis facebook-machine."""
    try:
        from agents.copywriter.agent import run_copywriter
        return run_copywriter
    except Exception as e:
        logger.error(f"Error loading copywriter: {e}")
        return None


def _get_image_creator():
    """Retourne la fonction image creator depuis facebook-machine."""
    try:
        from agents.image_creator.agent import run_image_creator
        return run_image_creator
    except Exception as e:
        logger.error(f"Error loading image_creator: {e}")
        return None


def _get_topic_finder():
    """Retourne la fonction topic_finder depuis facebook-machine."""
    try:
        from agents.topic_finder.agent import run_topic_finder
        return run_topic_finder
    except Exception as e:
        logger.error(f"Error loading topic_finder: {e}")
        return None


def _get_scheduler():
    """Retourne la fonction scheduler depuis facebook-machine."""
    try:
        from agents.scheduler.agent import run_pipeline
        return run_pipeline
    except Exception as e:
        logger.error(f"Error loading scheduler: {e}")
        return None


def _get_video_maker():
    """Retourne la fonction video_maker depuis shared_agents."""
    try:
        from shared_agents.video_maker.agent import run_video_maker
        return run_video_maker
    except Exception as e:
        logger.error(f"Error loading video_maker: {e}")
        return None


def _get_account_dir(platform: str, account_id: int = None) -> Path:
    """Retourne le dossier account (accounts/{id}/) si spécifié, en créant tous les sous-dossiers nécessaires."""
    if not account_id:
        return None

    base = PLATFORM_BASE.get(platform)
    if not base:
        return None

    # Nouvelle structure : accounts/{account_id}/
    acc_dir = base / "accounts" / str(account_id)
    personas_dir = acc_dir / "persona"

    # Toujours s'assurer que les dossiers existent
    acc_dir.mkdir(parents=True, exist_ok=True)
    personas_dir.mkdir(exist_ok=True)
    (acc_dir / "content").mkdir(exist_ok=True)

    return acc_dir


def _get_personas_dir_for_account(account_id=None, platform: str = "facebook"):
    """Retourne le dossier personas selon account_id et platform."""
    # Normaliser account_id en int si c'est une string
    if account_id and not isinstance(account_id, int):
        try:
            account_id = int(account_id)
        except (ValueError, TypeError):
            account_id = 1
            
    if not account_id:
        account_id = 1

    # PRIORITÉ 1: account_id spécifique
    acc_dir = _get_account_dir(platform or "facebook", account_id)
    if acc_dir:
        personas_dir = acc_dir / "persona"
        personas_dir.mkdir(exist_ok=True)  # Garantir l'existence
        
        # Migration automatique si le dossier est vide
        has_personas = False
        try:
            has_personas = any(p.is_dir() and not p.name.startswith(('.', '_')) for p in personas_dir.iterdir())
        except Exception:
            pass

        if not has_personas:
            import shutil
            base = PLATFORM_BASE.get(platform or "facebook")
            if base:
                old_dir = base / "accounts" / str(account_id) / "persona"
                root_dir = base / "persona"
                source_dir = None

                if old_dir.exists() and any(p.is_dir() and not p.name.startswith(('.', '_')) for p in old_dir.iterdir()):
                    source_dir = old_dir
                elif root_dir.exists() and any(p.is_dir() and not p.name.startswith(('.', '_')) for p in root_dir.iterdir()):
                    source_dir = root_dir

                if source_dir:
                    try:
                        for item in source_dir.iterdir():
                            if item.is_dir() and not item.name.startswith('.'):
                                dest = personas_dir / item.name
                                if not dest.exists():
                                    shutil.copytree(str(item), str(dest))
                        logger.info(f"[Migration] Personas copiés de {source_dir} vers {personas_dir}")
                    except Exception as e:
                        logger.error(f"[Migration] Erreur copie personas: {e}")
                        return source_dir # Fallback en cas d'erreur de copie
                        
        return personas_dir

    # Fallback extrême: retourner le dossier global de personas
    return Config.PERSONAS_DIR

@router.get("/personas")
async def api_personas(request: Request):
    """Liste tous les personas disponibles - selon plateforme ET account_id."""
    platform = request.query_params.get("platform", "facebook")
    account_id_str = request.query_params.get("account_id", "")

    # Normaliser account_id
    account_id = None
    if account_id_str and account_id_str.strip().isdigit():
        account_id = int(account_id_str)

    personas_dir = _get_personas_dir_for_account(account_id, platform)
    logger.info(f"[personas] account_id={account_id} platform={platform} → {personas_dir}")  # debug
    personas = []
    
    if personas_dir.exists():
        for p in sorted(personas_dir.iterdir()):
            if not p.is_dir() or p.name.startswith("_") or p.name.startswith("."):
                continue
            
            config_file = p / "config.json"
            conf = {}
            if config_file.exists():
                try:
                    conf = json.loads(config_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            personas.append({
                "name": p.name,
                "value": p.name,
                "display_name": conf.get("nom_persona", conf.get("display_name", conf.get("name", p.name.replace("_", " ").title()))),
                "label": conf.get("nom_persona", conf.get("display_name", conf.get("name", p.name.replace("_", " ").title()))),
                "type": "post" if "reel" not in p.name.lower() else "reel",
                "has_image": conf.get("generates_image", conf.get("image", True)),
                "has_reel": "reel" in p.name.lower(),
                "ton": conf.get("ton", conf.get("tone", "")),
                "target_words": conf.get("target_words", conf.get("max_words", 500)),
                "image_enabled": conf.get("generates_image", conf.get("image", True)),
                "has_prompt": (p / "system_prompt.md").exists(),
                "has_examples": (p / "examples.md").exists(),
                "has_config": config_file.exists()
            })
    
    if not any(p["value"] == "reel" for p in personas):
        personas.append({
            "value": "reel", "label": "Format Reel", "type": "reel", "has_image": False, "has_reel": True
        })
    
    return {"personas": personas, "account_id": account_id, "source": "dashboard_api_v2"}


@router.post("/personas/create")
async def api_persona_create(req: Request):
    """Crée un nouveau persona pour le compte (isolé par account_id)."""
    body = await req.json()
    name = body.get("name")
    prompt = body.get("prompt")
    examples = body.get("examples")
    tone = body.get("tone", "professionnel")
    platform = req.query_params.get("platform", "facebook")
    account_id_str = req.query_params.get("account_id", "")

    # Normaliser account_id
    account_id = None
    if account_id_str and account_id_str.strip().isdigit():
        account_id = int(account_id_str)

    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")

    personas_dir = _get_personas_dir_for_account(account_id, platform)
    logger.info(f"[personas/create] account_id={account_id} platform={platform} → {personas_dir}")

    # Sanitize name: lettres, chiffres, underscores uniquement
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name.strip()).lower().strip("_")
    if not safe_name:
        raise HTTPException(status_code=400, detail="Nom invalide")

    p_dir = personas_dir / safe_name
    if p_dir.exists():
        return {"success": False, "error": f"Le persona '{safe_name}' existe déjà pour ce compte."}

    p_dir.mkdir(parents=True, exist_ok=True)

    # Écrire la config
    config = {
        "name": safe_name,
        "display_name": name.strip(),
        "generates_image": True,
        "target_words": 150,
        "tone": tone,
        "account_id": account_id
    }
    (p_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (p_dir / "system_prompt.md").write_text(prompt.strip() if prompt else f"Tu es {name.strip()}.", encoding="utf-8")
    if examples and examples.strip():
        (p_dir / "examples.md").write_text(examples.strip(), encoding="utf-8")

    logger.info(f"[personas/create] Persona '{safe_name}' créé dans {p_dir}")
    return {"success": True, "name": safe_name, "path": str(p_dir)}

@router.delete("/personas/{name}")
async def api_persona_delete(request: Request, name: str):
    """Supprime un persona."""
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    personas_dir = _get_personas_dir_for_account(account_id, platform)

    # Security: validate persona name
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid persona name")
    p_dir = personas_dir / name
    if not str(p_dir.resolve()).startswith(str(personas_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    if p_dir.exists() and p_dir.is_dir():
        import shutil
        shutil.rmtree(p_dir)
        return {"success": True}
    return {"success": False, "error": f"Persona '{name}' introuvable dans {personas_dir}"}

@router.get("/personas/detail")
async def api_persona_detail(request: Request, name: str):
    """Retourne config.json, system_prompt.md et examples.md d'un persona."""
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    personas_dir = _get_personas_dir_for_account(account_id, platform)

    p = personas_dir / name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Persona '{name}' introuvable dans {personas_dir}")
    config = {}
    if (p / "config.json").exists():
        try:
            config = json.loads((p / "config.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    format_data = None
    if (p / "format.json").exists():
        try:
            format_data = json.loads((p / "format.json").read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[persona_detail] Could not load format.json for {name}: {e}")
            format_data = None
    prompt = (p / "system_prompt.md").read_text(encoding="utf-8") if (p / "system_prompt.md").exists() else ""
    examples = (p / "examples.md").read_text(encoding="utf-8") if (p / "examples.md").exists() else ""
    return {"name": name, "config": config, "format": format_data, "system_prompt": prompt, "prompt": prompt, "examples": examples, "content": examples}


@router.post("/personas/save")
async def api_persona_save(req: Request):
    """Sauvegarde config.json d'un persona."""
    body = await req.json()
    name = body.get("name")
    config = body.get("config", {})
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")

    if not name:
        raise HTTPException(status_code=400, detail="name requis")

    personas_dir = _get_personas_dir_for_account(account_id, platform)
    p = personas_dir / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"success": True, "name": name}


@router.post("/personas/save_prompt")
async def api_persona_save_prompt(req: Request):
    """Sauvegarde system_prompt.md d'un persona."""
    body = await req.json()
    name = body.get("name")
    prompt = body.get("prompt") or body.get("content", "")
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")

    if not name:
        raise HTTPException(status_code=400, detail="name requis")

    personas_dir = _get_personas_dir_for_account(account_id, platform)
    p = personas_dir / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "system_prompt.md").write_text(prompt, encoding="utf-8")
    return {"success": True}


@router.get("/personas/examples")
async def api_persona_examples(request: Request, name: str):
    """Retourne examples.md d'un persona."""
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    personas_dir = _get_personas_dir_for_account(account_id, platform)

    p = personas_dir / name / "examples.md"
    content = ""
    if p.exists():
        content = p.read_text(encoding="utf-8")
    return {"examples": content, "content": content, "name": name}


@router.post("/personas/save_examples")
async def api_persona_save_examples(req: Request):
    """Sauvegarde examples.md d'un persona."""
    body = await req.json()
    name = body.get("name")
    examples = body.get("examples") or body.get("content", "")
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")

    if not name:
        raise HTTPException(status_code=400, detail="name requis")

    personas_dir = _get_personas_dir_for_account(account_id, platform)
    p = personas_dir / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "examples.md").write_text(examples, encoding="utf-8")
    return {"success": True}


# ══════════════════════════════════════════════════════════════════
# ROUTES RESOURCES — Ressources post (triggers + contenu)
# ══════════════════════════════════════════════════════════════════

def _load_resources() -> dict:
    f = DATA_DIR / "post_resources.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

# ══════════════════════════════════════════════════════════════════
# ROUTES GROUP POSTER — Partage dans les groupes via profil tiers
# ══════════════════════════════════════════════════════════════════

@router.get("/groups")
async def api_groups():
    """Retourne la liste des groupes configurés et le log de partage du jour."""
    import json as _json
    from datetime import date

    groups_file = DATA_DIR / "facebook_groups.json"
    share_log_file = DATA_DIR / "group_share_log.json"

    groups = []
    if groups_file.exists():
        try:
            groups = _json.loads(groups_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    shared_today = []
    if share_log_file.exists():
        try:
            log = _json.loads(share_log_file.read_text(encoding="utf-8"))
            shared_today = log.get(date.today().isoformat(), [])
        except Exception:
            pass

    # Annoter chaque groupe avec son statut du jour
    for g in groups:
        g["shared_today"] = g.get("name", "") in shared_today

    return {"groups": groups, "shared_today": shared_today}


@router.post("/groups/share")
async def api_groups_share(req: Request):
    """Déclenche le partage du dernier post de la Page dans les groupes.

    Body JSON (optionnel) :
      - post_url (str) : URL spécifique à partager (sinon auto-détectée)
      - comment (str)  : Commentaire global ajouté à chaque partage
    """
    import threading
    body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
    post_url = body.get("post_url", "")
    comment  = body.get("comment", "")

    def _run():
        try:
            from agents.group_poster.agent import run_group_poster
            result = run_group_poster(post_url=post_url, comment=comment)
            logger.info(f"Group poster terminé: {result.data}")
        except Exception as e:
            logger.exception(f"Erreur group poster: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "success": True,
        "message": "Partage démarré en arrière-plan. Vérifiez les logs pour le résultat.",
    }


@router.get("/resources")
async def api_resources():
    """Retourne toutes les ressources de posts."""
    return {"resources": _load_resources()}


@router.get("/resources/save")
async def api_resources_save(post_id: str, trigger: str, content: str):
    """Sauvegarde une ressource texte pour un post (legacy — compatibilité)."""
    resources = _load_resources()
    resources[post_id] = {"trigger_word": trigger, "resource_content": content}
    (DATA_DIR / "post_resources.json").write_text(
        json.dumps(resources, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"success": True}


@router.post("/resources/deploy")
async def api_resources_deploy(req: Request):
    """Déploie une ressource sur GitHub Pages et la lie à un post Facebook.

    Body JSON :
      - post_id (str)      : ID Facebook du post
      - trigger_word (str) : Mot déclencheur
      - content (str)      : Texte de la ressource
    """
    body = await req.json()
    post_id = body.get("post_id")
    trigger = body.get("trigger_word")
    content = body.get("content")
    
    if not post_id or not trigger or not content:
        raise HTTPException(status_code=400, detail="post_id, trigger_word et content requis")
        
    try:
        from scripts.deploy_resource import deploy_single_resource
        url = deploy_single_resource(post_id, trigger, content)
        
        # Sauvegarder localement
        resources = _load_resources()
        resources[post_id] = {"trigger_word": trigger, "resource_content": content, "url": url}
        (DATA_DIR / "post_resources.json").write_text(
            json.dumps(resources, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        
        return {"success": True, "url": url}
    except Exception as e:
        logger.exception(f"Erreur deploy: {e}")
        return {"success": False, "error": str(e)}

@router.delete("/resources/{post_id}")
async def api_resources_delete(post_id: str):
    """Supprime une ressource."""
    resources = _load_resources()
    if post_id in resources:
        del resources[post_id]
        (DATA_DIR / "post_resources.json").write_text(
            json.dumps(resources, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"success": True}
    return {"success": False, "error": "Introuvable"}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - TASKS (TRACKING)
# ══════════════════════════════════════════════════════════════════

@router.get("/tasks/{task_id}")
async def api_get_task(task_id: str):
    """Récupère le statut d'une tâche."""
    try:
        from core.task_tracker import get_task
        task = get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Tâche introuvable")
        return {"task": task}
    except HTTPException:
        raise
    except Exception as e:
        return {"task": None, "error": str(e)}


@router.get("/tasks")
async def api_list_tasks(request: Request):
    """Liste toutes les tâches actives."""
    try:
        from core.task_tracker import get_active_tasks
        tasks = get_active_tasks()
        return {"tasks": tasks}
    except Exception as e:
        return {"tasks": [], "error": str(e)}


@router.post("/tasks")
async def api_create_task(req: Request):
    """Crée une nouvelle tâche."""
    try:
        body = await req.json()
        from core.task_tracker import create_task
        task_id = create_task(
            task_type=body.get("type", "unknown"),
            folder=body.get("folder"),
            message=body.get("message", "")
        )
        return {"task_id": task_id, "success": True}
    except Exception as e:
        return {"error": str(e)}


@router.put("/tasks/{task_id}")
async def api_update_task(task_id: str, req: Request):
    """Met à jour une tâche."""
    try:
        body = await req.json()
        from core.task_tracker import update_task
        update_task(
            task_id,
            progress=body.get("progress"),
            status=body.get("status"),
            message=body.get("message"),
            log=body.get("log")
        )
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - SCHEDULER CONFIG
# ══════════════════════════════════════════════════════════════════

@router.get("/schedule")
async def api_get_schedule(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"schedule": [], "default": DEFAULT_SCHEDULE, "error": "Accès non autorisé à ce compte"}

    schedule = _load_schedule(platform, account_id)
    return {"schedule": schedule, "default": DEFAULT_SCHEDULE}

@router.post("/schedule")
async def api_save_schedule(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    body = await req.json()
    new_schedule = body.get("schedule", [])
    _save_schedule(new_schedule, platform, account_id)
    return {"success": True, "schedule": new_schedule}

@router.post("/schedule/reset")
async def api_reset_schedule(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    _save_schedule(DEFAULT_SCHEDULE.copy(), platform, account_id)
    return {"success": True, "schedule": DEFAULT_SCHEDULE}


# ══════════════════════════════════════════════════════════════════
# ROUTES API - PLANNED TOPICS
# ══════════════════════════════════════════════════════════════════

@router.get("/planned_topics")
async def api_get_planned_topics(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"topics": [], "error": "Accès non autorisé à ce compte"}

    # Support flattened listing for the Laboratoire UI
    group_by = request.query_params.get("group_by") or request.query_params.get("group")
    flatten = request.query_params.get("flatten")
    if (group_by and group_by.lower() in ["none", "flat"]) or (flatten and flatten.lower() == "true"):
        try:
            topics = topics_store.list_topics(platform, account_id)
            return {"topics": topics}
        except Exception:
            # fallback to previous behaviour on error
            pass

    topics = _load_planned_topics(platform, account_id)
    if isinstance(topics, dict) and "topics" in topics:
        return {"topics": topics["topics"]}
    return {"topics": topics}

@router.get("/planned_topics/plan")
async def api_get_daily_plan(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"success": True, "plan": None, "date": "", "error": "Accès non autorisé à ce compte"}

    date = request.query_params.get("date") or datetime.now().strftime("%Y-%m-%d")
    plan_file = _get_daily_plan_file(date, account_id, platform)
    if plan_file.exists():
        try:
            return {"success": True, "plan": json.loads(plan_file.read_text(encoding="utf-8")), "date": date}
        except Exception:
            raise HTTPException(status_code=500, detail="Erreur lecture plan journalier")
    return {"success": True, "plan": None, "date": date}

@router.post("/planned_topics/plan")
async def api_generate_daily_plan(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform", "facebook")
    account_id = req.query_params.get("account_id") or body.get("account_id") or 1
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    date = req.query_params.get("date") or body.get("date") or datetime.now().strftime("%Y-%m-%d")
    force = req.query_params.get("force") == "true" or bool(body.get("force", False))
    try:
        from shared_agents.topic_finder.agent import generate_daily_plan
        result = generate_daily_plan(date=date, force=force, account_id=account_id, platform=platform)
        if result.success:
            return {"success": True, "generated": True, "plan": result.data, "date": date}
        raise HTTPException(status_code=500, detail=getattr(result, "error_cause", "Erreur génération plan"))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"api_generate_daily_plan error: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la génération du plan")

@router.post("/planned_topics/save")
async def api_save_planned_topics(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    body = await req.json()
    topics = body.get("topics", {})
    mode = body.get("mode", "merge")

    from dashboard.api.topics_store import import_topics

    if isinstance(topics, dict):
        flat = []
        for p, items in topics.items():
            for t in (items or []):
                if not isinstance(t, dict):
                    continue
                entry = dict(t)
                entry["persona"] = entry.get("persona") or p
                flat.append(entry)
        topics = flat

    if not isinstance(topics, list):
        return {"success": False, "error": "topics doit être une liste ou un dict par persona"}

    res = import_topics(topics, platform, account_id, mode="replace" if mode == "replace" else "merge")
    return {"success": True, "imported": res.get("imported"), "total": res.get("total")}

@router.post("/planned_topics/suggest")
async def api_suggest_planned_topics(req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    body = await req.json()
    persona = body.get("persona")
    count = body.get("count", 10)
    
    if not persona:
        raise HTTPException(status_code=400, detail="Persona requis")
        
    from shared_agents.topic_finder.agent import suggest_persona_topics
    res = suggest_persona_topics(persona, count=count, account_id=account_id, platform=platform)
    
    if res.success:
        return {"success": True, "topics": res.data.get("topics", [])}
    else:
        return {"success": False, "error": res.error_cause}


@router.post("/planned_topics/generate_planning")
async def api_generate_planning_topics(req: Request):
    """Génère les sujets manquants pour la période donnée, en respectant un angle."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        data = await req.json()
    except Exception:
        data = {}

    angle = data.get("angle", "")
    start_date_str = data.get("start_date")
    end_date_str = data.get("end_date")

    try:
        from shared_agents.topic_finder.agent import suggest_persona_topics
        import time as _time
        from datetime import datetime, timedelta
        
        if not start_date_str:
            start_date_str = datetime.now().strftime("%Y-%m-%d")
        if not end_date_str:
            end_date_str = (datetime.strptime(start_date_str, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
            
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        delta = (end_date - start_date).days
        
        if delta < 0 or delta > 31:
            return {"success": False, "error": "Plage de dates invalide (max 31 jours)."}
            
        dates_to_generate = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(delta + 1)]
        
        sched = _load_schedule(platform, account_id)
        required_by_persona = {}
        for s in sched:
            p = s.get("persona")
            if p:
                required_by_persona[p] = required_by_persona.get(p, 0) + 1
                
        all_topics = topics_store.list_topics(platform, account_id)
        
        total_added = 0
        errors = []
        
        for date_str in dates_to_generate:
            # Compter dispo pour CE jour
            available_by_persona = {}
            for t in all_topics:
                raw = t.get("raw") or {}
                if raw.get("used"): continue
                t_date = t.get("date_prevue")
                if t_date and t_date[:10] == date_str:
                    p = t.get("persona")
                    if p:
                        available_by_persona[p] = available_by_persona.get(p, 0) + 1
                        
            # Si c'est le 1er jour, on compte aussi les sujets sans date comme disponibles
            if date_str == start_date_str:
                for t in all_topics:
                    raw = t.get("raw") or {}
                    if raw.get("used"): continue
                    if not t.get("date_prevue"):
                        p = t.get("persona")
                        if p:
                            available_by_persona[p] = available_by_persona.get(p, 0) + 1
            
            for persona, required in required_by_persona.items():
                available = available_by_persona.get(persona, 0)
                missing = required - available
                
                if missing > 0:
                    logger.info(f"Génération de {missing} sujets pour {persona} à la date {date_str}")
                    res = suggest_persona_topics(persona, count=missing, account_id=account_id, platform=platform, angle=angle)
                    if res.success:
                        topics_list = res.data.get("topics", [])
                        for t in topics_list:
                            topic_data = {
                                "persona": persona,
                                "topic": t.get("topic") or t.get("titre") or "",
                                "context": t.get("context") or t.get("angle") or "",
                                "objectif": t.get("objectif") or "engagement",
                                "variables": t.get("variables", {}),
                                "validated": False,
                                "used": False,
                                "date_prevue": f"{date_str}T12:00:00"
                            }
                            topics_store.create_topic(topic_data, platform, account_id)
                            # On ajoute "virtuellement" pour les prochaines itérations si jamais
                            all_topics.append({"persona": persona, "date_prevue": f"{date_str}T12:00:00", "raw": {"used": False}})
                            total_added += 1
                    else:
                        errors.append(f"{persona} ({date_str})")
                        logger.error(f"Failed to generate topic for {persona}: {res.error_cause}")
                    _time.sleep(2)

        result = {"success": True, "count": total_added}
        if errors:
            result["warnings"] = f"Echec pour {len(errors)} requêtes: {', '.join(errors)}"
        return result
    except Exception as e:
        logger.exception("Error generating planning topics")
        return {"success": False, "error": str(e)}


@router.post("/planned_topics/generate_posts")
async def api_generate_posts_from_validated(req: Request):
    """Génère les posts pour tous les sujets validés qui n'ont pas encore été générés.
    Les posts apparaîtront dans l'onglet Validation."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        # Charger tous les sujets validés et non utilisés
        all_topics = topics_store.list_topics(platform, account_id)
        validated = [t for t in all_topics if t.get("validated") and not (t.get("raw") or {}).get("used")]

        # Trier par date croissante (les sujets sans date passent en dernier)
        def _sort_key(t):
            raw = t.get("raw") or {}
            d = t.get("date") or raw.get("date") or (raw.get("date_prevue") or "")[:10] or ""
            return (1 if not d else 0, d or "", t.get("topic") or "")
        validated.sort(key=_sort_key)

        if not validated:
            return {"success": True, "count": 0, "message": "Aucun sujet validé en attente de génération."}

        import uuid as _uuid
        import threading
        from core.task_tracker import create_task, update_task

        task_id = create_task("batch", f"posts_{_uuid.uuid4().hex[:8]}", f"Génération de {len(validated)} post(s) validé(s)")
        update_task(task_id, progress=5, status="running", log="Démarrage de la génération des posts")

        def run_generation():
            try:
                from machines.facebook_machine.agents.scheduler.agent import process_single_post
                import time as _time
                success_count = 0
                for i, topic in enumerate(validated):
                    raw = topic.get("raw") or {}
                    persona = topic.get("persona") or raw.get("persona", "")
                    t_date = topic.get("date") or raw.get("date") or raw.get("date_prevue", "")[:10]
                    t_time = topic.get("time") or raw.get("time") or ""
                    if t_date and t_time:
                        scheduled_time = f"{t_date[:10]}T{t_time}:00"
                    elif raw.get("date_prevue"):
                        scheduled_time = raw.get("date_prevue")
                    else:
                        scheduled_time = raw.get("time") or raw.get("scheduled_time", "")
                    plan_entry = {
                        "persona": persona,
                        "sujet": raw.get("topic") or raw.get("titre") or topic.get("topic", ""),
                        "context": raw.get("context") or topic.get("context", ""),
                        "objectif": raw.get("objectif", "engagement"),
                        "variables": raw.get("variables", {}),
                        "scheduled_time": scheduled_time,
                        "date_prevue": scheduled_time,
                    }
                    progress = int(((i + 1) / len(validated)) * 90) + 5
                    update_task(task_id, progress=progress, status="running",
                                message=f"[{i+1}/{len(validated)}] Génération: {persona}",
                                log=f"Traitement de {persona}: {plan_entry['sujet'][:60]}")
                    try:
                        res = process_single_post(
                            plan_entry,
                            (t_date or datetime.now().strftime("%Y-%m-%d"))[:10],
                            False,  # Ne pas publier automatiquement
                            task_id=task_id,
                            current=i + 1,
                            total=len(validated),
                            account_id=account_id,
                            platform=platform
                        )
                        if res.success:
                            success_count += 1
                            # Marquer le sujet comme utilisé
                            topics_store.update_topic(topic["id"], {"used": True, "used_at": datetime.now().isoformat()}, platform, account_id)
                        else:
                            logger.error(f"process_single_post failed for {persona}: {getattr(res, 'error', 'unknown')}")
                    except Exception as ex:
                        logger.exception(f"Exception generating post for {persona}: {ex}")
                    if i < len(validated) - 1:
                        _time.sleep(3)  # Pause anti-rate-limit

                _sync_folders_to_db(platform, account_id)
                update_task(task_id, progress=100, status="completed",
                            message=f"Terminé: {success_count}/{len(validated)} post(s) généré(s)")
            except Exception as e:
                logger.exception(f"run_generation error: {e}")
                update_task(task_id, status="failed", message=str(e))

        threading.Thread(target=run_generation, daemon=True).start()
        return {"success": True, "task_id": task_id, "count": len(validated),
                "message": f"Génération de {len(validated)} post(s) démarrée en arrière-plan"}
    except Exception as e:
        logger.exception("Error in generate_posts_from_validated")
        return {"success": False, "error": str(e)}


@router.post("/planned_topics/regenerate/{topic_id}")
async def api_regenerate_planned_topic(topic_id: str, req: Request):
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and account_id.isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        topic = topics_store.get_topic(topic_id, account_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Sujet planifié introuvable")

        persona = topic.get("persona")
        from shared_agents.topic_finder.agent import suggest_persona_topics
        
        res = suggest_persona_topics(persona, count=1, account_id=account_id, platform=platform)
        if not res.success:
            return {"success": False, "error": f"Erreur Groq: {res.error_cause}"}

        topics_list = res.data.get("topics", [])
        if not topics_list:
            return {"success": False, "error": "Aucun sujet retourné par l'IA"}

        new_t = topics_list[0]
        update_data = {
            "topic": new_t.get("topic") or new_t.get("titre") or "",
            "context": new_t.get("context") or new_t.get("angle") or "",
            "objectif": new_t.get("objectif") or "engagement",
            "variables": new_t.get("variables", {}),
            "validated": False
        }
        
        updated = topics_store.update_topic(topic_id, update_data, platform, account_id)
        if not updated:
            return {"success": False, "error": "Impossible de mettre à jour le sujet planifié"}

        return {"success": True, "topic": updated}
    except Exception as e:
        logger.exception(f"Error regenerating planned topic {topic_id}")
        return {"success": False, "error": str(e)}


# --- RESTful endpoints for Laboratoire topics (account-scoped) ---
@router.get("/planned_topics/{topic_id}")
async def api_get_planned_topic(request: Request, topic_id: str):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = None

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id is not None and account_id not in allowed:
        return {"error": "Accès non autorisé à ce compte"}

    try:
        topic = topics_store.get_topic(topic_id, account_id)
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found or not allowed")
        return {"topic": topic}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"api_get_planned_topic error: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.post("/planned_topics")
async def api_create_planned_topic(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform", "facebook")
    account_id = req.query_params.get("account_id") or body.get("account_id")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        topic = topics_store.create_topic(body, platform, account_id)
        # enqueue change for scheduler
        try:
            from scheduler.topic_sync import enqueue_topic_change
            enqueue_topic_change({"action": "create", "topic": topic})
        except Exception:
            pass
        return {"success": True, "topic": topic}
    except Exception as e:
        logger.warning(f"api_create_planned_topic error: {e}")
        raise HTTPException(status_code=500, detail="Erreur création topic")


@router.put("/planned_topics/{topic_id}")
@router.patch("/planned_topics/{topic_id}")
async def api_update_planned_topic(request: Request, topic_id: str):
    body = await request.json()
    platform = request.query_params.get("platform") or body.get("platform", "facebook")
    account_id = request.query_params.get("account_id") or body.get("account_id")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = None

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        updated = topics_store.update_topic(topic_id, body, platform, account_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Topic not found or not allowed")
        try:
            from scheduler.topic_sync import enqueue_topic_change
            enqueue_topic_change({"action": "update", "topic": updated})
        except Exception:
            pass
        return {"success": True, "topic": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"api_update_planned_topic error: {e}")
        raise HTTPException(status_code=500, detail="Erreur update topic")


@router.delete("/planned_topics/{topic_id}")
async def api_delete_planned_topic(topic_id: str, request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = None

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        ok = topics_store.delete_topic(topic_id, platform, account_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Topic not found or not allowed")
        try:
            from scheduler.topic_sync import enqueue_topic_change
            enqueue_topic_change({"action": "delete", "topic_id": topic_id, "platform": platform, "account_id": account_id})
        except Exception:
            pass
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"api_delete_planned_topic error: {e}")
        raise HTTPException(status_code=500, detail="Erreur suppression topic")


@router.post("/planned_topics/import")
async def api_import_planned_topics(req: Request):
    """Import a list of topics from a JSON file."""
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalide")

    topics_list = body.get("topics", [])
    mode = body.get("mode", "merge")
    schedule_override = body.get("schedule_override")

    if not topics_list:
        raise HTTPException(status_code=400, detail="Aucun topic à importer")

    try:
        result = topics_store.import_topics(topics_list, platform, account_id, mode=mode)

        if schedule_override and isinstance(schedule_override, list):
            schedule_file = PLATFORM_BASE.get(platform, DATA_DIR.parent) / "accounts" / str(account_id) / "schedule.json"
            if schedule_file.exists():
                backup = schedule_file.with_suffix(".json.bak")
                import shutil
                shutil.copy2(str(schedule_file), str(backup))
            schedule_file.parent.mkdir(parents=True, exist_ok=True)
            schedule_file.write_text(json.dumps(schedule_override, indent=2, ensure_ascii=False), encoding="utf-8")

        try:
            from scheduler.topic_sync import enqueue_topic_change
            for t in topics_list:
                enqueue_topic_change({"action": "create", "topic": t})
        except Exception:
            pass

        return {"success": True, "imported": result["imported"], "warnings": result["warnings"], "total": result["total"]}
    except Exception as e:
        logger.warning(f"api_import_planned_topics error: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur import: {str(e)}")


# ══════════════════════════════════════════════════════════════════
# ROUTES API - AUTO APPROVE
# ══════════════════════════════════════════════════════════════════

def _load_auto_approve_config():
    config_file = DATA_DIR / "auto_approve.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": False}

def _save_auto_approve_config(config):
    config_file = DATA_DIR / "auto_approve.json"
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_ai_responses_config():
    """Charge la config globale des réponses IA depuis settings.json (partagé avec le webhook)."""
    settings_file = DATA_DIR / "settings.json"
    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return {"enabled": bool(data.get("ai_responses_enabled", False))}
        except Exception:
            pass
    return {"enabled": False}

def _save_ai_responses_config(config):
    settings_file = DATA_DIR / "settings.json"
    data = {}
    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["ai_responses_enabled"] = bool(config.get("enabled", False))
    settings_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

@router.get("/ai_responses")
async def api_get_ai_responses():
    return _load_ai_responses_config()

@router.post("/ai_responses")
async def api_set_ai_responses(req: Request):
    body = await req.json()
    enabled = body.get("enabled", False)
    _save_ai_responses_config({"enabled": enabled})
    return {"success": True, "enabled": enabled}


def _load_reel_mode():
    reel_file = DATA_DIR / "reel_mode.json"
    if reel_file.exists():
        try:
            return json.loads(reel_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"mode": "music"}

def _save_reel_mode(config):
    reel_file = DATA_DIR / "reel_mode.json"
    reel_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

@router.get("/reel_mode")
async def api_get_reel_mode():
    return _load_reel_mode()

@router.post("/reel_mode")
async def api_set_reel_mode(req: Request):
    body = await req.json()
    mode = body.get("mode", "music")
    _save_reel_mode({"mode": mode})
    return {"success": True, "mode": mode}

@router.get("/auto_approve")
async def api_get_auto_approve():
    config = _load_auto_approve_config()
    return config

@router.post("/auto_approve")
async def api_set_auto_approve(req: Request):
    body = await req.json()
    enabled = body.get("enabled", False)
    config = _load_auto_approve_config()
    config["enabled"] = enabled
    _save_auto_approve_config(config)
    return {"success": True, "enabled": enabled}

@router.post("/auto_approve/check")
async def api_check_and_publish():
    """Vérifie les posts pending/approved et publie si l'heure est passée (pour tous les comptes)."""
    accounts = []
    for platform, db_path in PLATFORM_DB.items():
        if Path(db_path).exists():
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, platform, name, status FROM accounts WHERE status='active'")
            for row in cursor:
                accounts.append({"id": row["id"], "platform": row["platform"], "name": row["name"], "status": row["status"]})
            conn.close()
    
    config = _load_auto_approve_config()
    auto_approve_enabled = config.get("enabled", False)
    
    from datetime import datetime
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    total_published = 0
    published_details = []

    for acc in accounts:
        platform = acc["platform"]
        account_id = acc["id"]
        
        schedule = _load_schedule(platform, account_id)
        folders = _list_post_folders(platform, account_id)
        
        for folder in folders:
            post = _read_post(folder)
            status = post.get("status", "draft")
            
            if post.get("published", False): continue
            if status not in ["pending", "approved"]: continue
            
            # Récupérer l'heure programmée
            scheduled_time = post.get("scheduled_time", "")
            if not scheduled_time:
                persona = post.get("persona", "")
                for slot in schedule:
                    if slot.get("persona") == persona:
                        scheduled_time = slot.get("time", "")
                        break
            
            if not scheduled_time: continue
            
            # Comparer date+heure complète si disponible, sinon HH:MM
            scheduled_dt = None
            try:
                if "T" in str(scheduled_time):
                    scheduled_dt = datetime.fromisoformat(str(scheduled_time).replace("Z", "+00:00"))
                    if scheduled_dt.tzinfo is not None:
                        scheduled_dt = scheduled_dt.replace(tzinfo=None)
                else:
                    h, m = map(int, str(scheduled_time).split(":"))
                    scheduled_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            except:
                continue
            
            if now < scheduled_dt: continue
            
            if status == "pending":
                if auto_approve_enabled:
                    _save_meta(folder, {"status": "approved"})
                    status = "approved"
                else:
                    continue
            
            if status == "approved":
                try:
                    run_publisher = _get_publisher(platform)
                    if not run_publisher:
                        logger.warning(f"No publisher found for platform {platform}")
                        continue
                    res = run_publisher(str(folder), account_id=account_id)
                    if res.success:
                        _save_meta(folder, {"status": "published", "published": True})
                        total_published += 1
                        published_details.append(f"{acc.name}: {folder.name}")
                        logger.info(f"Auto-published for {acc.name}: {folder.name}")
                except Exception as e:
                    logger.error(f"Auto-publish failed for {folder.name} (Acc: {acc.name}): {e}")

    return {
        "success": True,
        "message": f"{total_published} post(s) publié(s)",
        "published": published_details,
        "current_time": current_time
    }


def _compute_next_slot(platform: str = "facebook", account_id=None):
    """Calcule le prochain créneau de publication (schedule du compte) non passé.

    Retourne None si aucun créneau à venir, sinon dict {time, persona, type, remaining_min}.
    """
    try:
        schedule = _load_schedule(platform, account_id or 1)
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        next_slot = None
        for slot in schedule:
            try:
                h, m = map(int, str(slot.get("time", "")).split(":"))
            except Exception:
                continue
            slot_minutes = h * 60 + m
            if slot_minutes > current_minutes:
                next_slot = {**slot, "remaining_min": slot_minutes - current_minutes}
                break
        return next_slot
    except Exception as e:
        logger.error(f"compute_next_slot error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# TACHE DE FOND - PUBLICATION AUTOMATIQUE
# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
# ROUTES API - COMPTES (ACCOUNTS)
# ══════════════════════════════════════════════════════════════════

def _get_user_account_ids(request: Request):
    """Retourne la liste des account_ids autorisés pour l'utilisateur connecté, ou None si admin (tous)."""
    # Priorité: session cookie, fallback: X-User-Id header
    user_id = request.session.get("user_id") if "session" in request.scope else None
    if not user_id:
        user_id = request.headers.get("X-User-Id", "")
    if not user_id:
        return None
    try:
        from core.db import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            row = db.execute(text("SELECT account_ids FROM users WHERE id=:uid AND active=1"), {"uid": int(user_id)}).fetchone()
            if row and row[0] and row[0] != "null":
                return json.loads(row[0])
        finally:
            db.close()
    except Exception:
        pass
    return None


@router.get("/accounts")
async def api_get_accounts(request: Request):
    """Récupère la liste des comptes pour une plateforme ou tous les comptes."""
    platform = request.query_params.get("platform", "facebook")
    all_platforms = platform == "all"

    # ── Filtrage par user (session cookie ou header fallback) ──
    user_account_ids = None
    user_id_header = ""
    if "session" in request.scope:
        user_id_header = str(request.session.get("user_id", ""))
    if not user_id_header:
        user_id_header = request.headers.get("X-User-Id", "")
    if user_id_header:
        try:
            from core.db import SessionLocal as _SL
            from sqlalchemy import text
            db = _SL()
            try:
                row = db.execute(text("SELECT account_ids FROM users WHERE id=:uid AND active=1"), {"uid": int(user_id_header)}).fetchone()
                if row and row[0] and row[0] != "null":
                    user_account_ids = json.loads(row[0])
            finally:
                db.close()
        except Exception:
            pass
    
    if all_platforms:
        db_items = [(plat, path) for plat, path in PLATFORM_DB.items() if Path(path).exists()]
        if not db_items:
            return {"accounts": []}
    else:
        db_path = PLATFORM_DB.get(platform)
        if not db_path or not Path(db_path).exists():
            return {"accounts": []}
        db_items = [(platform, db_path)]
    
    try:
        import sqlite3
        result = []
        for plat, db_path in db_items:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
            if not cursor.fetchone():
                conn.close()
                continue

            if all_platforms:
                cursor.execute("SELECT id, platform, name, status, credentials, settings FROM accounts")
            else:
                cursor.execute("SELECT id, platform, name, status, credentials, settings FROM accounts WHERE platform=?", (plat,))

            accounts = cursor.fetchall()
            for acc in accounts:
                try:
                    creds = acc["credentials"]
                    if isinstance(creds, str):
                        try:
                            creds = json.loads(creds)
                        except (json.JSONDecodeError, TypeError):
                            creds = {}
                    elif creds is None:
                        creds = {}

                    settings = {}
                    raw_settings = acc["settings"] if "settings" in acc.keys() else None
                    if raw_settings:
                        try:
                            settings = json.loads(raw_settings)
                        except (json.JSONDecodeError, TypeError):
                            settings = {}

                    page_id = creds.get("page_id", "") or creds.get("linkedin_user_id", "") or creds.get("twitter_user_id", "") or ""

                    api_key = settings.get("llm_api_key", "") or ""
                    masked_key = ""
                    if api_key:
                        masked_key = ("••••••••" + api_key[-4:]) if len(api_key) > 4 else "••••••••"

                    result.append({
                        "id": acc["id"],
                        "platform": acc["platform"],
                        "name": acc["name"],
                        "page_id": page_id,
                        "status": acc["status"],
                        "llm_model": settings.get("llm_model", ""),
                        "llm_api_key": masked_key,
                        "llm_base_url": settings.get("llm_base_url", ""),
                        "created_at": None
                    })
                except Exception as e:
                    logger.error(f"Error processing account {acc['id']}: {e}")
                    continue

            conn.close()

        # ── Filtrer par user_accounts si défini (sauf admin) ──
        is_admin = (user_id_header == "1" or user_account_ids is None)
        if user_account_ids is not None and not is_admin:
            result = [a for a in result if a["id"] in user_account_ids]

        return {"accounts": result}
    except Exception as e:
        logger.error(f"Error in api_get_accounts for {platform}: {e}")
        return {"accounts": []}


@router.post("/accounts/save")
async def api_save_account(req: Request):
    """Ajoute ou met à jour un compte."""
    import json
    body = await req.json()
    
    acc_id = body.get("id")
    platform = body.get("platform")
    name = body.get("name")
    page_id = body.get("page_id", "")
    token = body.get("token", "")
    status = body.get("status", "active")
    llm_model = body.get("llm_model", "").strip()
    llm_api_key = (body.get("llm_api_key") or "").strip()
    llm_base_url = (body.get("llm_base_url") or "").strip()
    
    if not platform or not name:
        raise HTTPException(status_code=400, detail="platform et name requis")
    
    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        return {"success": False, "error": "DB not found for platform"}

    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        settings = {}
        is_new = not body.get("id")

        # Lire les credentials existantes pour preserver le token si vide
        existing_creds = {}
        if acc_id:
            cursor = conn.execute("SELECT credentials, settings FROM accounts WHERE id=?", (acc_id,))
            row = cursor.fetchone()
            if row:
                if row["credentials"]:
                    try:
                        existing_creds = json.loads(row["credentials"])
                    except (json.JSONDecodeError, TypeError):
                        existing_creds = {}
                if row["settings"]:
                    try:
                        settings = json.loads(row["settings"])
                    except (json.JSONDecodeError, TypeError):
                        settings = {}

        # Modèle : "" (défaut global) → on retire la clé pour retomber sur le défaut
        if llm_model:
            settings["llm_model"] = llm_model
        else:
            settings.pop("llm_model", None)

        # On n'écrase la clé / l'URL que si une nouvelle valeur non vide est fournie
        # (le formulaire ne pré-remplit pas la clé : l'utilisateur la resaisit pour changer).
        if llm_api_key:
            settings["llm_api_key"] = llm_api_key
        if llm_base_url:
            settings["llm_base_url"] = llm_base_url

        # Construire les credentials en preservant les anciennes valeurs si le champ est vide
        if platform == "linkedin":
            creds_json = json.dumps({
                "linkedin_token": token or existing_creds.get("linkedin_token", ""),
                "linkedin_user_id": page_id or existing_creds.get("linkedin_user_id", "")
            })
        else:
            creds_json = json.dumps({
                "page_id": page_id or existing_creds.get("page_id", ""),
                "access_token": token or existing_creds.get("access_token", "")
            })

        if acc_id:
            conn.execute(
                "UPDATE accounts SET platform=?, name=?, credentials=?, status=?, settings=? WHERE id=?",
                (platform, name, creds_json, status, json.dumps(settings, ensure_ascii=False), acc_id)
            )
            conn.commit()
            acc_id = int(acc_id)
        else:
            cursor = conn.execute(
                "INSERT INTO accounts (platform, name, credentials, status, settings) VALUES (?, ?, ?, ?, ?)",
                (platform, name, creds_json, status, json.dumps(settings, ensure_ascii=False))
            )
            conn.commit()
            acc_id = cursor.lastrowid
        
        conn.close()
        
        # Créer les dossiers du compte automatiquement
        if platform in PLATFORM_BASE:
            acc_dir = PLATFORM_BASE[platform] / "accounts" / str(acc_id)
            if not acc_dir.exists():
                acc_dir.mkdir(parents=True, exist_ok=True)
                acc_persona_dir = acc_dir / "persona"
                acc_persona_dir.mkdir(exist_ok=True)
                (acc_dir / "content").mkdir(exist_ok=True)
                schedule_file = acc_dir / "schedule.json"
                schedule_file.write_text(json.dumps({"schedule": DEFAULT_SCHEDULE}, indent=2), encoding="utf-8")
                
                import shutil
                template_persona_dir = PLATFORM_BASE[platform] / "persona"
                if template_persona_dir.exists():
                    for item in template_persona_dir.iterdir():
                        if item.is_dir() and not item.name.startswith('_OLD'):
                            dest_item = acc_persona_dir / item.name
                            if not dest_item.exists():
                                shutil.copytree(item, dest_item)
                
                print(f"[accounts] Dossiers créés pour account {acc_id}: {acc_dir}")

        # Auto-ajouter le nouveau compte aux account_ids de l'utilisateur courant
        if is_new:
            try:
                user_id_header = req.headers.get("X-User-Id", "")
                if not user_id_header:
                    user_id_header = str(req.session.get("user_id", "")) if "session" in req.scope else ""
                if user_id_header:
                    from core.db import SessionLocal as _SL
                    from sqlalchemy import text
                    db = _SL()
                    try:
                        row = db.execute(text("SELECT account_ids FROM users WHERE id=:uid AND active=1"), {"uid": int(user_id_header)}).fetchone()
                        if row:
                            current_ids = json.loads(row[0]) if row[0] and row[0] != "null" else []
                            if acc_id not in current_ids:
                                current_ids.append(acc_id)
                                db.execute(text("UPDATE users SET account_ids=:ids WHERE id=:uid"), {"ids": json.dumps(current_ids), "uid": int(user_id_header)})
                                db.commit()
                    finally:
                        db.close()
            except Exception:
                pass
        
        return {"success": True, "id": acc_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/accounts/{account_id}")
async def api_delete_account(account_id: int, platform: str = "facebook"):
    """Supprime un compte."""
    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        raise HTTPException(status_code=404, detail="DB not found")
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


@router.post("/accounts/{account_id}/toggle")
async def api_toggle_account(account_id: int, platform: str = "facebook"):
    """Bascule le statut d'un compte (active/inactive)."""
    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        raise HTTPException(status_code=404, detail="DB not found")
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT status FROM accounts WHERE id=?", (account_id,))
        acc = cursor.fetchone()
        if not acc:
            raise HTTPException(status_code=404, detail="Compte introuvable")
        
        new_status = "inactive" if acc["status"] == "active" else "active"
        conn.execute("UPDATE accounts SET status=? WHERE id=?", (new_status, account_id))
        conn.commit()
        return {"success": True, "status": new_status}
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════
# ROUTES API - CLIENTS
# ══════════════════════════════════════════════════════════════════

def _db_client_session():
    from core.db import SessionLocal, Client
    return SessionLocal(), Client


def _client_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email or "",
        "plan": c.plan or "starter",
        "active": bool(c.active),
        "account_ids": c.account_ids or [],
        "created_at": str(c.created_at) if c.created_at else "",
    }


def _account_key(platform, account_id):
    return f"{platform}:{account_id}"


def _all_accounts_by_id():
    """Indexe tous les comptes (toutes plateformes) par clé 'platform:id'."""
    index = {}
    for plat, db_path in PLATFORM_DB.items():
        if not Path(db_path).exists():
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            for acc in conn.execute("SELECT id, platform, name, status, credentials FROM accounts"):
                creds = acc["credentials"]
                if isinstance(creds, str):
                    try:
                        creds = json.loads(creds)
                    except Exception:
                        creds = {}
                key = _account_key(acc["platform"] or plat, acc["id"])
                index[key] = {
                    "platform": acc["platform"] or plat,
                    "id": acc["id"],
                    "name": acc["name"],
                    "status": acc["status"],
                    "page_id": (creds or {}).get("page_id", "") or (creds or {}).get("user_id", ""),
                }
            conn.close()
        except Exception as e:
            logger.warning(f"[clients] index {plat} échoué: {e}")
    return index


def _resolve_client_accounts(account_ids):
    """Retourne la liste détaillée des comptes d'un client.

    account_ids accepte deux formats : [1, 6] (déprécié → facebook par défaut)
    ou [{platform, id}, ...] (recommandé, sans ambiguïté entre plateformes).
    """
    index = _all_accounts_by_id()
    result = []
    for entry in (account_ids or []):
        if isinstance(entry, dict):
            plat = entry.get("platform", "facebook")
            aid = entry.get("id")
        else:
            plat, aid = "facebook", entry
        key = _account_key(plat, aid)
        if key in index:
            result.append(index[key])
        else:
            result.append({"platform": plat, "id": aid, "name": f"Compte {aid} ({plat})", "status": "?", "page_id": ""})
    return result


def _client_account_entries(client_id):
    """Retourne la liste des comptes (dict {platform, id}) rattachés à un client."""
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return []
        entries = []
        for entry in (c.account_ids or []):
            if isinstance(entry, dict):
                entries.append({"platform": entry.get("platform", "facebook"), "id": entry.get("id")})
            else:
                entries.append({"platform": "facebook", "id": entry})
        return entries
    finally:
        db.close()


def _client_content_dirs(client_id):
    """Retourne la liste des content_dir des comptes rattachés à un client."""
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return []
        dirs = []
        for entry in (c.account_ids or []):
            if isinstance(entry, dict):
                plat = entry.get("platform", "facebook")
                aid = entry.get("id")
            else:
                plat, aid = "facebook", entry
            try:
                d = _get_content_dir(plat, int(aid))
                if d and Path(d).exists():
                    dirs.append(d)
            except Exception:
                continue
        return dirs
    finally:
        db.close()


@router.get("/clients")
async def api_get_clients():
    """Liste tous les clients (admin)."""
    db, Client = _db_client_session()
    try:
        clients = db.query(Client).order_by(Client.name).all()
        return {"success": True, "clients": [_client_to_dict(c) for c in clients]}
    finally:
        db.close()


@router.post("/clients")
async def api_create_client(req: Request):
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "Nom requis"}, status_code=400)
    db, Client = _db_client_session()
    try:
        client = Client(
            name=name,
            email=body.get("email", ""),
            plan=body.get("plan", "starter"),
            active=body.get("active", True),
            account_ids=body.get("account_ids", []),
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return {"success": True, "client": _client_to_dict(client)}
    finally:
        db.close()


@router.put("/clients/{client_id}")
async def api_update_client(client_id: int, req: Request):
    body = await req.json()
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return JSONResponse({"success": False, "error": "Client introuvable"}, status_code=404)
        if "name" in body and body["name"]:
            c.name = body["name"].strip()
        if "email" in body:
            c.email = body.get("email", "")
        if "plan" in body:
            c.plan = body.get("plan", "starter")
        if "active" in body:
            c.active = body.get("active", True)
        if "account_ids" in body:
            c.account_ids = body.get("account_ids", [])
        db.commit()
        db.refresh(c)
        return {"success": True, "client": _client_to_dict(c)}
    finally:
        db.close()


@router.delete("/clients/{client_id}")
async def api_delete_client(client_id: int):
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return JSONResponse({"success": False, "error": "Client introuvable"}, status_code=404)
        db.delete(c)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.get("/clients/{client_id}/accounts")
async def api_get_client_accounts(client_id: int):
    """Retourne les comptes (détaillés) rattachés à un client + tous les comptes disponibles."""
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return JSONResponse({"success": False, "error": "Client introuvable"}, status_code=404)
        return {
            "success": True,
            "client": _client_to_dict(c),
            "accounts": _resolve_client_accounts(c.account_ids),
            "available": _all_accounts_by_id(),
        }
    finally:
        db.close()


@router.post("/clients/{client_id}/accounts")
async def api_set_client_accounts(client_id: int, req: Request):
    body = await req.json()
    db, Client = _db_client_session()
    try:
        c = db.query(Client).filter(Client.id == client_id).first()
        if not c:
            return JSONResponse({"success": False, "error": "Client introuvable"}, status_code=404)
        c.account_ids = body.get("account_ids", [])
        db.commit()
        db.refresh(c)
        return {"success": True, "client": _client_to_dict(c)}
    finally:
        db.close()


@router.post("/linkedin/update_token")
async def api_update_linkedin_token(req: Request):
    """Met à jour le token LinkedIn dans la DB et le .env."""
    import json
    body = await req.json()
    new_token = body.get("token", "").strip()
    user_id = body.get("user_id", "").strip()
    account_id = body.get("account_id")
    
    if not new_token:
        return {"success": False, "error": "Token requis"}
    
    # 1. Mettre à jour la DB LinkedIn
    db_path = PLATFORM_DB.get("linkedin")
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        if account_id:
            cursor = conn.execute("SELECT credentials FROM accounts WHERE id=? AND platform='linkedin'", (account_id,))
        else:
            cursor = conn.execute("SELECT id, credentials FROM accounts WHERE platform='linkedin' AND status='active' LIMIT 1")
        
        row = cursor.fetchone()
        if row:
            creds = json.loads(row["credentials"]) if row["credentials"] else {}
            creds["linkedin_token"] = new_token
            if user_id:
                creds["linkedin_user_id"] = user_id
            conn.execute("UPDATE accounts SET credentials=? WHERE id=?", (json.dumps(creds), row["id"]))
            conn.commit()
            logger.info(f"LinkedIn token updated in DB for account {row['id']}")
        
        conn.close()
    except Exception as e:
        logger.error(f"Error updating LinkedIn token in DB: {e}")
        return {"success": False, "error": f"DB update failed: {e}"}
    
    # 2. Mettre à jour le .env (pour le fallback)
    try:
        env_path = str(ROOT_DIR / ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        
        import re
        env_content = re.sub(r"LINKEDIN_TOKEN=.*", f"LINKEDIN_TOKEN={new_token}", env_content)
        if user_id:
            env_content = re.sub(r"LINKEDIN_USER_ID=.*", f"LINKEDIN_USER_ID={user_id}", env_content)
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        
        logger.info("LinkedIn token updated in .env")
    except Exception as e:
        logger.error(f"Error updating LinkedIn token in .env: {e}")
        return {"success": False, "error": f"DB OK mais .env update failed: {e}"}
    
    return {"success": True, "message": "Token LinkedIn mis à jour (DB + .env). Redémarrez le dashboard."}


@router.get("/token/refresh")
async def api_token_refresh(req: Request):
    """Vérifie l'état du token LinkedIn (DB) sans le modifier."""
    db_path = PLATFORM_DB.get("linkedin")
    if not db_path or not Path(db_path).exists():
        return {"valid": False, "error": "DB LinkedIn introuvable"}
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT credentials FROM accounts WHERE platform='linkedin' AND status='active' LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row["credentials"]:
            creds = json.loads(row["credentials"]) if isinstance(row["credentials"], str) else row["credentials"]
            token = creds.get("linkedin_token", "")
            expires = creds.get("expires_at") or creds.get("token_expires_at")
            return {
                "valid": bool(token),
                "expires": expires or (creds.get("expires_in") and "30 jours") or None,
            }
        return {"valid": False, "error": "Aucun compte LinkedIn actif"}
    except Exception as e:
        logger.exception(f"Erreur token/refresh: {e}")
        return {"valid": False, "error": str(e)}


@router.get("/analytics")
async def api_analytics(request: Request):
    """Statistiques réelles des posts générés, selon platform + account_id (ou client_id).

    Source : meta.json des dossiers content (données réelles, pas de mock).
    """
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    client_id = request.query_params.get("client_id")
    try:
        from agents.analytics.agent import analyze_content, analyze_content_multi, list_posts, list_posts_multi
    except Exception as e:
        logger.exception(f"[analytics] import agent échoué: {e}")
        return {"success": True, "total": 0, "avg_words": 0, "by_persona": [], "compliance": {"green": 0, "yellow": 0, "red": 0}}

    client_dirs = []
    if client_id and client_id.isdigit():
        client_dirs = _client_content_dirs(int(client_id))
        if not client_dirs:
            return {"success": True, "total": 0, "avg_words": 0, "by_persona": [], "compliance": {"green": 0, "yellow": 0, "red": 0}, "client_id": int(client_id)}

    if client_dirs:
        try:
            stats = analyze_content_multi(client_dirs)
        except Exception as e:
            logger.exception(f"[analytics] analyze_content_multi échoué: {e}")
            stats = {}
        posts = []
        try:
            posts = list_posts_multi(client_dirs, published_only=False)
        except Exception as e:
            logger.warning(f"[analytics] list_posts_multi échoué: {e}")
    else:
        target_dir = _get_content_dir(platform, int(account_id) if account_id and account_id.isdigit() else None)
        try:
            stats = analyze_content(target_dir)
        except Exception as e:
            logger.exception(f"[analytics] analyze_content échoué: {e}")
            stats = {}
        posts = []
        try:
            posts = list_posts(target_dir, published_only=False)
        except Exception as e:
            logger.warning(f"[analytics] list_posts échoué: {e}")

    compliance = {
        "green": int(stats.get("compliance", {}).get("green", 0)),
        "yellow": int(stats.get("compliance", {}).get("yellow", 0)),
        "red": int(stats.get("compliance", {}).get("red", 0)),
    }

    resp = {
        "success": True,
        "total": int(stats.get("total", 0)),
        "published": int(stats.get("published", 0)),
        "unpublished": int(stats.get("unpublished", 0)),
        "avg_words": int(stats.get("avg_word_count", 0)),
        "by_persona": [
            {"persona": k, "count": int(v)}
            for k, v in sorted(stats.get("by_persona", {}).items(), key=lambda x: -x[1])
        ],
        "by_type": [
            {"type": k, "count": int(v)}
            for k, v in sorted(stats.get("by_type", {}).items(), key=lambda x: -x[1])
        ],
        "with_images": int(stats.get("with_images", 0)),
        "with_reels": int(stats.get("with_reels", 0)),
        "with_resources": int(stats.get("with_resources", 0)),
        "compliance": compliance,
        "post_count": len(posts),
    }
    if client_id and client_id.isdigit():
        resp["client_id"] = int(client_id)
    return resp

_INSIGHTS_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "engagement_cache.json"
_INSIGHTS_CACHE_TTL = 3600  # 1h


def _load_insights_cache() -> dict:
    try:
        if _INSIGHTS_CACHE_FILE.exists():
            return json.loads(_INSIGHTS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[insights] cache illisible: {e}")
    return {}


def _save_insights_cache(data: dict):
    try:
        _INSIGHTS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _INSIGHTS_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[insights] cache non sauvegardé: {e}")


@router.get("/facebook/insights")
async def api_facebook_insights(request: Request):
    """Engagement réel des posts publiés (Graph API) avec cache 1h.

    Source : post_id + access_token du compte → GET /{post_id}?fields=reactions.summary(true),comments.summary(true),shares.
    Cache : data/engagement_cache.json (évite les appels répétés).
    """
    account_id = request.query_params.get("account_id")
    client_id = request.query_params.get("client_id")
    try:
        from agents.analytics.agent import list_posts, list_posts_multi
    except Exception as e:
        logger.exception(f"[insights] import agent échoué: {e}")
        return {"success": True, "total_likes": 0, "total_comments": 0, "posts": []}

    # Périmètre : client (multi-comptes FB) ou compte unique
    client_dirs = []
    if client_id and client_id.isdigit():
        client_dirs = _client_content_dirs(int(client_id))
    try:
        if client_dirs:
            posts = list_posts_multi(client_dirs, published_only=True)
        else:
            target_dir = _get_content_dir("facebook", int(account_id) if account_id and account_id.isdigit() else None)
            posts = list_posts(target_dir, published_only=True)
    except Exception as e:
        logger.warning(f"[insights] list_posts échoué: {e}")
        posts = []

    # Pas de post publié → rien à mesurer
    if not posts:
        return {"success": True, "total_likes": 0, "total_comments": 0, "posts": [], "message": "Aucun post publié"}

    # Récupérer le token du compte pour les appels Graph (depuis la DB plateforme)
    token = ""
    page_id = ""
    resolved_account_id = int(account_id) if account_id and account_id.isdigit() else None
    if client_dirs:
        # Pour un client : token du 1er compte FB rattaché
        for entry in (_client_account_entries(int(client_id)) or []):
            if entry.get("platform") == "facebook":
                resolved_account_id = entry.get("id")
                break
    creds = _get_account_credentials("facebook", resolved_account_id)
    if creds:
        token = creds.get("access_token", "")
        page_id = str(creds.get("page_id", ""))

    cache = _load_insights_cache()
    now = int(__import__("time").time())
    results = []
    total_likes, total_comments = 0, 0

    import requests as _requests

    for p in posts:
        pid = p.get("post_id", "")
        if not pid:
            results.append({**p, "likes": 0, "comments": 0, "shares": 0})
            continue
        # Normaliser : si pas de "page_post", préfixer par le page_id du compte
        if "_" not in pid and page_id:
            graph_id = f"{page_id}_{pid}"
        else:
            graph_id = pid
        cached = cache.get(graph_id)
        if cached and now - cached.get("ts", 0) < _INSIGHTS_CACHE_TTL:
            metrics = cached.get("metrics", {"likes": 0, "comments": 0, "shares": 0})
        else:
            metrics = {"likes": 0, "comments": 0, "shares": 0}
            if token:
                try:
                    url = f"https://graph.facebook.com/v18.0/{graph_id}"
                    resp = _requests.get(url, params={
                        "fields": "reactions.summary(true),comments.summary(true),shares",
                        "access_token": token,
                    }, timeout=12)
                    if resp.status_code == 200:
                        j = resp.json()
                        reactions = (j.get("reactions") or {}).get("summary", {})
                        comments = (j.get("comments") or {}).get("summary", {})
                        metrics = {
                            "likes": int(reactions.get("total_count", 0)),
                            "comments": int(comments.get("total_count", 0)),
                            "shares": int((j.get("shares") or {}).get("count", 0)),
                        }
                    elif resp.status_code == 400 and "access token" in resp.text.lower():
                        token = ""  # token invalide → on s'arrête, on garde le cache
                except Exception as e:
                    logger.warning(f"[insights] erreur post {pid}: {e}")
            # Cache même les échecs (TTL court) pour éviter les appels répétés
            cache[graph_id] = {"ts": now, "metrics": metrics}
        results.append({**p, "likes": metrics["likes"], "comments": metrics["comments"], "shares": metrics["shares"]})
        total_likes += metrics["likes"]
        total_comments += metrics["comments"]

    _save_insights_cache(cache)

    return {
        "success": True,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "posts": results,
        "account_id": account_id,
        "page_id": page_id,
    }


@router.get("/report/export")
async def api_report_export(request: Request):
    """Exporte un rapport client (CSV ou PDF) pour la période + compte (ou client) choisis."""
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    client_id = request.query_params.get("client_id")
    fmt = (request.query_params.get("format", "csv") or "csv").lower()
    from_str = request.query_params.get("from", "")
    to_str = request.query_params.get("to", "")

    try:
        from agents.analytics.agent import analyze_content, analyze_content_multi, list_posts, list_posts_multi
    except Exception as e:
        logger.exception(f"[report] import agent échoué: {e}")
        return JSONResponse({"success": False, "error": "Agent analytics indisponible"}, status_code=500)

    # Périmètre : client (multi-comptes) ou compte unique
    client_dirs = []
    if client_id and client_id.isdigit():
        client_dirs = _client_content_dirs(int(client_id))
    try:
        if client_dirs:
            stats = analyze_content_multi(client_dirs)
            posts = list_posts_multi(client_dirs, published_only=True)
        else:
            target_dir = _get_content_dir(platform, int(account_id) if account_id and account_id.isdigit() else None)
            stats = analyze_content(target_dir)
            posts = list_posts(target_dir, published_only=True)
    except Exception as e:
        logger.warning(f"[report] analyse échouée: {e}")
        stats, posts = {}, []

    # Période
    def _in_period(p):
        if not from_str and not to_str:
            return True
        pd = (p.get("published_at") or p.get("created_at") or "")[:10]
        if not pd:
            return True
        if from_str and pd < from_str:
            return False
        if to_str and pd > to_str:
            return False
        return True

    filtered = [p for p in posts if _in_period(p)]

    # Enrichir avec l'engagement en cache (éviter les appels API graphiques)
    cache = _load_insights_cache()
    account_index = _all_accounts_by_id()
    for p in filtered:
        pid = p.get("post_id", "")
        if not pid:
            p["likes"], p["comments"], p["shares"] = 0, 0, 0
            continue
        # Résoudre le page_id : priorité au client (page_id du compte FB correspondant), sinon compte demandé
        page_id = ""
        if client_id and client_id.isdigit():
            for entry in (_client_account_entries(int(client_id)) or []):
                if entry.get("platform") == "facebook":
                    key = _account_key("facebook", entry.get("id"))
                    acc = account_index.get(key) or {}
                    page_id = str(acc.get("page_id", ""))
                    break
        if not page_id:
            creds = _get_account_credentials("facebook", int(account_id) if account_id and account_id.isdigit() else None)
            page_id = str(creds.get("page_id", "")) if creds else ""
        gid = f"{page_id}_{pid}" if ("_" not in pid and page_id) else pid
        m = (cache.get(gid) or {}).get("metrics", {})
        p["likes"] = int(m.get("likes", 0))
        p["comments"] = int(m.get("comments", 0))
        p["shares"] = int(m.get("shares", 0))

    total_likes = sum(p.get("likes", 0) for p in filtered)
    total_comments = sum(p.get("comments", 0) for p in filtered)

    acc_label = account_id or "—"
    if client_dirs:
        acc_label = f"Client #{client_id}"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Rapport Content Machine", platform.upper(), "Compte", acc_label])
        writer.writerow(["Généré le", generated_at, "Période", f"{from_str or 'début'} → {to_str or 'auj.'}"])
        writer.writerow([])
        writer.writerow(["KPIs", "Valeur"])
        writer.writerow(["Posts publiés (période)", len(filtered)])
        writer.writerow(["Total posts", int(stats.get("total", 0))])
        writer.writerow(["Likes (période)", total_likes])
        writer.writerow(["Commentaires (période)", total_comments])
        writer.writerow(["Mots moyens", int(stats.get("avg_word_count", 0))])
        writer.writerow(["Avec image", int(stats.get("with_images", 0))])
        writer.writerow(["Avec reel", int(stats.get("with_reels", 0))])
        writer.writerow(["Conforme", int(stats.get("compliance", {}).get("green", 0))])
        writer.writerow(["Acceptable", int(stats.get("compliance", {}).get("yellow", 0))])
        writer.writerow(["Non conforme", int(stats.get("compliance", {}).get("red", 0))])
        writer.writerow([])
        writer.writerow(["Date", "Persona", "Message", "Likes", "Commentaires", "Partages"])
        for p in filtered:
            writer.writerow([
                p.get("date", ""),
                p.get("persona", ""),
                (p.get("message", "") or "").replace("\n", " ")[:120],
                p.get("likes", 0),
                p.get("comments", 0),
                p.get("shares", 0),
            ])
        filename = f"rapport_{platform}_{acc_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        data = buf.getvalue().encode("utf-8-sig")
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=data, media_type="text/csv; charset=utf-8", headers=headers)

    # PDF via fpdf
    try:
        from fpdf import FPDF
    except Exception as e:
        logger.warning(f"[report] fpdf absent: {e}")
        return JSONResponse({"success": False, "error": "Génération PDF indisponible (fpdf manquant)"}, status_code=500)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    # Police Unicode (Arial) pour supporter accents, tirets, etc.
    try:
        pdf.add_font("Arial", "", r"C:\Windows\Fonts\arial.ttf")
        pdf.add_font("Arial", "B", r"C:\Windows\Fonts\arialbd.ttf")
        FONT = "Arial"
    except Exception:
        FONT = "Helvetica"
    pdf.add_page()
    pdf.set_font(FONT, "B", 16)
    pdf.cell(0, 10, f"Rapport {platform.upper()} — Compte {acc_label}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Généré le {generated_at}  |  Période : {from_str or 'début'} → {to_str or 'auj.'}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font(FONT, "B", 12)
    pdf.cell(0, 8, "Indicateurs clés", new_x="LMARGIN", new_y="NEXT")
    kpis = [
        ("Posts publiés (période)", str(len(filtered))),
        ("Total posts", str(int(stats.get("total", 0)))),
        ("Likes (période)", str(total_likes)),
        ("Commentaires (période)", str(total_comments)),
        ("Mots moyens", str(int(stats.get("avg_word_count", 0)))),
        ("Avec image", str(int(stats.get("with_images", 0)))),
        ("Avec reel", str(int(stats.get("with_reels", 0)))),
        ("Conformité — Conforme / Acceptable / Non conforme",
         f"{int(stats.get('compliance', {}).get('green', 0))} / "
         f"{int(stats.get('compliance', {}).get('yellow', 0))} / "
         f"{int(stats.get('compliance', {}).get('red', 0))}"),
    ]
    for label, val in kpis:
        pdf.set_font(FONT, "", 9)
        pdf.cell(0, 6, f"{label} : {val}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font(FONT, "B", 12)
    pdf.cell(0, 8, f"Posts publiés ({len(filtered)})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "B", 8)
    col_w = {"date": 22, "persona": 28, "msg": 78, "l": 14, "c": 18, "s": 16}
    pdf.cell(col_w["date"], 6, "Date", border=1)
    pdf.cell(col_w["persona"], 6, "Persona", border=1)
    pdf.cell(col_w["msg"], 6, "Message", border=1)
    pdf.cell(col_w["l"], 6, "Likes", border=1, align="C")
    pdf.cell(col_w["c"], 6, "Comment.", border=1, align="C")
    pdf.cell(col_w["s"], 6, "Partages", border=1, align="C")
    pdf.ln()
    pdf.set_font(FONT, "", 8)
    for p in filtered:
        msg = (p.get("message", "") or "").replace("\n", " ")[:80]
        pdf.cell(col_w["date"], 6, p.get("date", ""), border=1)
        pdf.cell(col_w["persona"], 6, p.get("persona", ""), border=1)
        pdf.cell(col_w["msg"], 6, msg, border=1)
        pdf.cell(col_w["l"], 6, str(p.get("likes", 0)), border=1, align="C")
        pdf.cell(col_w["c"], 6, str(p.get("comments", 0)), border=1, align="C")
        pdf.cell(col_w["s"], 6, str(p.get("shares", 0)), border=1, align="C")
        pdf.ln()

    filename = f"rapport_{platform}_{acc_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    data = bytes(pdf.output())
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=data, media_type="application/pdf", headers=headers)

@router.get("/logs")
async def api_logs(since: int = 0):
    """Agrège les logs de scheduler, copywriter et dashboard.
    Paramètre since: index du dernier log connu (retourne seulement les nouveaux)."""
    LOG_FILES = [
        ("scheduler", ROOT_DIR / "logs" / "scheduler.log"),
        ("copywriter", ROOT_DIR / "logs" / "copywriter.log"),
        ("dashboard", ROOT_DIR / "logs" / "dashboard_api.log"),
    ]

    def parse_log_file(source, filepath):
        entries = []
        if not filepath.exists():
            return entries
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")
            entry = None
            for line in text.strip().split("\n"):
                if not line.strip():
                    continue
                if line.startswith(tuple(str(year) for year in range(2000, 2100))) and " - " in line:
                    if entry:
                        entries.append(entry)
                    parts = line.split(" - ", 2)
                    if len(parts) >= 3:
                        entry = {"time": parts[0].strip(), "level": parts[1].strip(), "message": parts[2].strip(), "source": source}
                    else:
                        entry = {"time": "", "level": "INFO", "message": line.strip(), "source": source}
                elif entry:
                    entry["message"] += "\n" + line
                else:
                    entry = {"time": "", "level": "INFO", "message": line.strip(), "source": source}
            if entry:
                entries.append(entry)
        except Exception:
            pass
        return entries

    all_logs = []
    for source, path in LOG_FILES:
        all_logs.extend(parse_log_file(source, path))

    all_logs.sort(key=lambda x: x.get("time", ""))
    total = len(all_logs)
    all_logs = all_logs[-300:]

    if since > 0 and since < total:
        offset = max(0, total - 300)
        all_logs = all_logs[since - offset:]

    return {"logs": all_logs, "total": total}

def _ensure_users_table():
    """Crée la table users si elle n'existe pas."""
    try:
        from core.db import SessionLocal
        from sqlalchemy import text, inspect as sa_inspect
        db = SessionLocal()
        try:
            inspector = sa_inspect(db.get_bind())
            if "users" not in inspector.get_table_names():
                db.execute(text("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        code TEXT UNIQUE NOT NULL,
                        account_ids TEXT DEFAULT '[]',
                        active INTEGER DEFAULT 1
                    )
                """))
                db.commit()
                db.execute(
                    text("INSERT INTO users (name, code, account_ids) VALUES (:name, :code, :acc)"),
                    {"name": "Admin", "code": "255800", "acc": "null"},
                )
                db.commit()
                logger.info("Table 'users' créée avec admin par défaut")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Erreur init users table: {e}")


@router.on_event("startup")
async def startup_event():
    logger.info("Démarrage du dashboard...")
    init_db()  # Initialize database tables
    _ensure_users_table()
    # Note: La synchronisation DB est effectuée à la demande via les endpoints API, pas au démarrage

    import asyncio
    async def auto_approve_loop():
        # Rattrapage immédiat au démarrage: publier les posts dont l'heure planifiée est déjà passée
        try:
            catch_up = await api_check_and_publish()
            logger.info(f"[CATCH-UP] Au démarrage: {getattr(catch_up, 'message', 'OK')}")
        except Exception as e:
            logger.error(f"[CATCH-UP] Erreur au démarrage: {e}")
        while True:
            try:
                await api_check_and_publish()
            except Exception as e:
                logger.error(f"Erreur background auto_publish: {e}")
            await asyncio.sleep(60)
            
    async def auto_generate_loop():
        """Déclenche la génération du batch chaque jour à 21:00."""
        logger.info("Démarrage de la boucle auto-generate (21h)")
        while True:
            try:
                from datetime import datetime
                now = datetime.now()
                # Vérifier si on est à l'heure du batch (fenêtre de 2 min pour éviter les ratés)
                if now.hour == BATCH_HOUR and now.minute == BATCH_MINUTE:
                    logger.info(f">>> HEURE DU BATCH ({BATCH_HOUR}h{BATCH_MINUTE:02d}) - Lancement automatique...")
                    
                    # On simule un appel à api_generate_batch
                    from agents.scheduler.agent import run_pipeline
                    from core.notifier import notify_batch_completed
                    
                    # Générer pour le LENDEMAIN (J+1) : les posts d'actualité sont rédigés la veille
                    # et passent par Validation le matin, puis publication auto à l'heure planifiée.
                    from datetime import timedelta
                    target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                    logger.info(f"Batch auto-generate : génération pour le {target_date}")
                    
                    # Exécuter le pipeline (non-bloquant via asyncio si possible, mais ici on est dans un thread séparé de facto)
                    # Pour éviter de bloquer, on peut utiliser loop.run_in_executor
                    loop = asyncio.get_event_loop()
                    res = await loop.run_in_executor(None, run_pipeline, "all", False, target_date)
                    
                    if res.success:
                        total = res.data.get("total", 7)
                        success = res.data.get("success", total)
                        notify_batch_completed(success, total)
                        logger.info(f"Batch auto-généré: {success}/{total}")
                    
                    # Attendre 1 minute pour sortir de la fenêtre de 21:00
                    await asyncio.sleep(65)
            except Exception as e:
                logger.error(f"Erreur background auto_generate: {e}")
            
            await asyncio.sleep(30) # Vérifie toutes les 30 secondes

    asyncio.create_task(auto_approve_loop())
    asyncio.create_task(auto_generate_loop())

def _get_topics_file(platform: str, account_id: int) -> Path:
    base = PLATFORM_BASE.get(platform)
    if not base:
        base = DATA_DIR.parent
    
    # Primary path: accounts/{id}/planned_topics.json
    new_path = base / "accounts" / str(account_id) / "planned_topics.json"
    # Legacy path: acc_{id}/planned_topics.json
    legacy_path = base / f"acc_{account_id}" / "planned_topics.json"
    
    # If new path doesn't exist but legacy does, migrate transparently
    if not new_path.exists() and legacy_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(str(legacy_path), str(new_path))
        logger.info(f"[TOPICS] Migrated from {legacy_path} to {new_path}")
    elif not new_path.parent.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"[TOPICS] Using path: {new_path}, exists: {new_path.exists()}")
    return new_path

def _load_topics(platform: str = "facebook", account_id: int = 1):
    f = _get_topics_file(platform, account_id)
    topics_list = []
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "version" in data and "topics" in data:
                for t in data["topics"]:
                    if not t.get("used", False):
                        topics_list.append({
                            "id": t.get("id", str(uuid.uuid4())),
                            "persona": t.get("persona", ""),
                            "topic": t.get("topic", ""),
                            "context": t.get("context", ""),
                            "media": t.get("media", "none"),
                            "date": t.get("date", ""),
                            "time": t.get("time", ""),
                        })
            else:
                for persona, p_topics in data.items():
                    for t in p_topics:
                        if not t.get("used", False):
                            topics_list.append({
                                "id": t.get("id", str(uuid.uuid4())),
                                "persona": persona,
                                "topic": t.get("topic", ""),
                                "context": t.get("context", ""),
                            })
        except:
            pass
    return topics_list

def _save_topics(topics_list: list, platform: str = "facebook", account_id: int = 1):
    f = _get_topics_file(platform, account_id)

    existing_topics = []
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "version" in data and "topics" in data:
                existing_topics = [t for t in data["topics"] if t.get("used", False)]
            else:
                for persona, p_topics in data.items():
                    for t in p_topics:
                        if t.get("used", False):
                            t.setdefault("persona", persona)
                            existing_topics.append(t)
        except Exception as e:
            logger.warning(f"Error loading topics: {e}")

    all_topics = existing_topics
    for t in topics_list:
        entry = {
            "id": t.get("id", str(uuid.uuid4())),
            "persona": t.get("persona", "default"),
            "topic": t.get("topic", ""),
            "context": t.get("context", ""),
            "media": t.get("media", "none"),
            "date": t.get("date", ""),
            "time": t.get("time", ""),
            "validated": t.get("validated", False),
            "used": False,
        }
        all_topics.append(entry)

    save_data = {"version": "1.0", "topics": all_topics}
    f.write_text(json.dumps(save_data, indent=2, ensure_ascii=False), encoding="utf-8")

@router.post("/scheduler/toggle")
async def api_toggle_scheduler(req: Request):
    import json
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform", "facebook")
    account_id = req.query_params.get("account_id") or body.get("account_id", 1)
    if str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = 1
    enabled = body.get("enabled", False)

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        return {"success": False, "error": "DB not found"}
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT settings FROM accounts WHERE id=?", (account_id,))
        acc = cursor.fetchone()
        if acc:
            settings = json.loads(acc["settings"]) if acc["settings"] else {}
            settings["scheduler_active"] = enabled
            conn.execute("UPDATE accounts SET settings=? WHERE id=?", (json.dumps(settings), account_id))
            conn.commit()
            return {"success": True, "enabled": enabled}
        return {"success": False, "error": "Account not found"}
    finally:
        conn.close()

@router.get("/scheduler/status")
async def api_scheduler_status(request: Request):
    import json
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id", 1)
    if str(account_id).isdigit():
        account_id = int(account_id)
    else:
        account_id = 1

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"active": False, "error": "Accès non autorisé à ce compte"}

    db_path = PLATFORM_DB.get(platform)
    if not db_path or not Path(db_path).exists():
        return {"active": False}
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT settings FROM accounts WHERE id=?", (account_id,))
        acc = cursor.fetchone()
        active = False
        if acc and acc["settings"]:
            settings = json.loads(acc["settings"])
            active = settings.get("scheduler_active", False)
        return {"active": active}
    finally:
        conn.close()

@router.get("/topics")
async def api_get_topics(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id", "1")
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"topics": [], "error": "Accès non autorisé à ce compte"}

    topics = _load_topics(platform, account_id)
    return {"topics": topics}

@router.post("/topics")
async def api_add_topic(req: Request):
    import uuid
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform", "facebook")
    account_id = req.query_params.get("account_id") or body.get("account_id", 1)
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    topic = {
        "id": str(uuid.uuid4()),
        "persona": body.get("persona", "unknown"),
        "topic": body.get("topic", ""),
        "context": body.get("context", ""),
        "media": body.get("media", "none"),
        "date": body.get("date", ""),
        "time": body.get("time", ""),
    }
    
    topics = _load_topics(platform, account_id)
    topics.append(topic)
    _save_topics(topics, platform, account_id)
    return {"success": True, "topic": topic}

@router.delete("/topics/{topic_id}")
async def api_delete_topic(topic_id: str, request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id", 1)
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)

    allowed = _get_user_account_ids(request)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    topics = _load_topics(platform, account_id)
    topics = [t for t in topics if t.get("id") != topic_id]
    _save_topics(topics, platform, account_id)
    return {"success": True}

@router.post("/topics/generate")
async def api_generate_topics(req: Request):
    import uuid
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform", "facebook")
    account_id = req.query_params.get("account_id") or body.get("account_id", 1)
    if account_id and str(account_id).isdigit():
        account_id = int(account_id)

    allowed = _get_user_account_ids(req)
    if allowed is not None and account_id not in allowed:
        return {"success": False, "error": "Accès non autorisé à ce compte"}

    persona = body.get("persona", "unknown")
    
    try:
        from core.llm_router import call_llm, get_account_llm_config
        platform_label = platform.upper() if platform != "facebook" else "Facebook"
        prompt = f"Génère 10 idées de sujets de posts {platform_label} pour le persona '{persona}'. Format: JSON liste de strings. Ne renvoie que le JSON."
        llm_cfg = get_account_llm_config(platform, account_id)
        res, _ = call_llm(
            "Tu es un expert en stratégie de contenu social. Réponds uniquement avec un JSON valide.",
            prompt,
            model=llm_cfg.get("model"),
            api_key=llm_cfg.get("api_key"),
            base_url=llm_cfg.get("base_url"),
        )
        if not res:
            return {"success": False, "error": "Les APIs IA ont échoué"}
        import re, json
        match = re.search(r"\[.*\]", res, re.DOTALL)
        new_topics = []
        if match:
            try:
                parsed = json.loads(match.group(0))
                for pt in parsed:
                    if isinstance(pt, str):
                        new_topics.append({
                            "id": str(uuid.uuid4()),
                            "persona": persona,
                            "topic": pt,
                            "context": "G?n?r? par IA"
                        })
            except Exception as e:
                logger.warning(f"Error in topic generation: {e}")
        
        if not new_topics:
            for i in range(10):
                new_topics.append({
                    "id": str(uuid.uuid4()),
                    "persona": persona,
                    "topic": f"Sujet g?n?r? automatiquement {i+1} pour {persona}",
                    "context": "G?n?r? par IA"
                })
                
        topics = _load_topics(platform, account_id)
        topics.extend(new_topics)
        _save_topics(topics, platform, account_id)
        return {"success": True, "count": len(new_topics)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# ROUTE CALENDRIER — Vue calendrier des publications planifiées
# ══════════════════════════════════════════════════════════════════

@router.get("/calendar")
async def api_calendar(request: Request):
    """Agrège les publications planifiées (planned_topics + posts générés) sur toutes les plateformes.
    Paramètres optionnels: platform, account_id, start, end (YYYY-MM-DD).
    """
    platform_filter = request.query_params.get("platform")
    account_filter = request.query_params.get("account_id")
    start = request.query_params.get("start")
    end = request.query_params.get("end")

    events = []
    accounts = []
    for platform, db_path in PLATFORM_DB.items():
        if platform_filter and platform != platform_filter:
            continue
        if not Path(db_path).exists():
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT id, name, status FROM accounts WHERE status='active'")
            for row in cursor:
                if account_filter and str(row["id"]) != str(account_filter):
                    continue
                accounts.append({"id": row["id"], "name": row["name"], "platform": platform})
            conn.close()
        except Exception as e:
            logger.error(f"Calendar: erreur listage comptes {platform}: {e}")

    for acc in accounts:
        platform = acc["platform"]
        account_id = acc["id"]

        # 1. Events depuis planned_topics.json (sujets planifiés)
        try:
            topics_data = topics_store.list_topics(platform, account_id)
            for t in topics_data:
                t_date = (t.get("date") or "")[:10]
                t_time = t.get("time") or ""
                # Fallback: extraire l'heure de date_prevue si time vide (anciens topics)
                if not t_time:
                    raw_dp = (t.get("raw") or {}).get("date_prevue") or ""
                    if "T" in str(raw_dp):
                        t_time = str(raw_dp).split("T")[1][:5]
                if not t_date:
                    continue
                if start and t_date < start: continue
                if end and t_date > end: continue
                events.append({
                    "id": t.get("id"),
                    "source": "planned_topic",
                    "platform": platform,
                    "account_id": account_id,
                    "account_name": acc["name"],
                    "date": t_date,
                    "time": t_time,
                    "persona": t.get("persona", ""),
                    "topic": t.get("topic", ""),
                    "status": "validated" if t.get("validated") else "draft",
                    "validated": bool(t.get("validated")),
                    "used": bool((t.get("raw") or {}).get("used", t.get("used", False))),
                })
        except Exception as e:
            logger.error(f"Calendar: erreur planned_topics {platform}/{account_id}: {e}")

        # 2. Events depuis les posts générés (meta.json scheduled_time)
        try:
            folders = _list_post_folders(platform, account_id)
            for folder in folders:
                meta = _read_post(folder)
                sched = meta.get("scheduled_time", "")
                if not sched:
                    continue
                sched_str = str(sched)
                if "T" in sched_str:
                    d = sched_str[:10]
                    tm = sched_str[11:16]
                else:
                    parts = sched_str.split(" ")
                    d = parts[0][:10] if parts and len(parts[0]) > 4 else ""
                    tm = parts[1][:5] if len(parts) > 1 else sched_str[:5]
                if not d:
                    continue
                if start and d < start: continue
                if end and d > end: continue
                events.append({
                    "id": folder.name,
                    "source": "post",
                    "platform": platform,
                    "account_id": account_id,
                    "account_name": acc["name"],
                    "date": d,
                    "time": tm,
                    "persona": meta.get("persona", ""),
                    "topic": meta.get("topic", ""),
                    "status": meta.get("status", "draft"),
                    "published": bool(meta.get("published", False)),
                    "ai_responses": meta.get("ai_responses"),
                    "folder": folder.name,
                })
        except Exception as e:
            logger.error(f"Calendar: erreur posts {platform}/{account_id}: {e}")

    events.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    return {"events": events, "count": len(events)}


# Include the router into the existing app (already created at line 75)
# DO NOT create a new FastAPI app here - it would lose the "/" and "/dashboard" routes
app.include_router(router)

# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    import argparse
    
    parser = argparse.ArgumentParser(description="IncidenX Dashboard API")
    parser.add_argument("--port", type=int, default=API_PORT, help="Port de l'API")
    args = parser.parse_args()
    
    print("=" * 50)
    print("IncidenX Dashboard API starting...")
    print(f"http://localhost:{args.port}")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=args.port, reload=False)
