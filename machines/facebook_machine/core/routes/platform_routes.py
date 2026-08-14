"""
Routes API pour LinkedIn et Twitter
Ces routes permettent au dashboard multiplateforme de fonctionner.
"""

import os
import sys
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid
from core.task_tracker import create_task, update_task
from core.config import Config

router = APIRouter(prefix="/api/v1", tags=["dashboard-v1"])

_BASE_DIR = Path("D:/Content_Machine")
_LINKEDIN_DIR = _BASE_DIR / "machines" / "machines/linkedin-machine"
_TWITTER_DIR = _BASE_DIR / "machines" / "machines/twitter-machine"


def _get_pending_posts(platform_dir: Path) -> list:
    """Liste les posts pending pour une plateforme."""
    content_dir = platform_dir / "content"
    if not content_dir.exists():
        return []
    
    pending = []
    for folder in content_dir.iterdir():
        if not folder.is_dir():
            continue
        meta_file = folder / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("status") == "pending" or (meta.get("status") is None and not meta.get("published", False)):
                    # Detecter le type de fichier selon la plateforme
                    platform = platform_dir.name
                    if "linkedin" in platform:
                        post_file = folder / "linkedin_post.txt"
                        if not post_file.exists():
                            for fallback in ["facebook_post.txt", "post.txt", "content.txt"]:
                                if (folder / fallback).exists():
                                    post_file = folder / fallback
                                    break
                    elif "twitter" in platform:
                        post_file = folder / "tweet.txt"
                        if not post_file.exists():
                            if (folder / "thread.json").exists():
                                post_file = None
                            else:
                                continue
                    else:
                        post_file = folder / "post.txt"
                    text = post_file.read_text(encoding="utf-8") if post_file and post_file.exists() else ""
                    pending.append({
                        "folder": folder.name,
                        "text": text[:200],
                        "status": meta.get("status"),
                        "created": meta.get("created"),
                    })
            except Exception:
                pass
    return pending


def _get_published_posts(platform_dir: Path) -> list:
    """Liste les posts publishés pour une plateforme."""
    content_dir = platform_dir / "content"
    if not content_dir.exists():
        return []
    
    published = []
    for folder in content_dir.iterdir():
        if not folder.is_dir():
            continue
        meta_file = folder / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("published"):
                    published.append({
                        "folder": folder.name,
                        "url": meta.get("url", ""),
                        "published_at": meta.get("published_at"),
                    })
            except Exception:
                pass
    return published


# ══════════════════════════════════════════════════════════════════
# LINKEDIN
# ══════════════════════════════════════════════════════════════════

@router.get("/linkedin/stats")
async def linkedin_stats():
    """Stats LinkedIn."""
    posts = _get_published_posts(_LINKEDIN_DIR)
    pending = _get_pending_posts(_LINKEDIN_DIR)
    return {
        "published_count": len(posts),
        "pending_count": len(pending),
        "last_post": posts[-1] if posts else None,
    }


@router.get("/linkedin/pending")
async def linkedin_pending():
    """Posts en attente de validation LinkedIn."""
    return {"count": len(_get_pending_posts(_LINKEDIN_DIR)), "posts": _get_pending_posts(_LINKEDIN_DIR)}


@router.get("/linkedin/published")
async def linkedin_published():
    """Posts publishés LinkedIn."""
    return {"count": len(_get_published_posts(_LINKEDIN_DIR)), "posts": _get_published_posts(_LINKEDIN_DIR)}


@router.post("/linkedin/approve")
async def linkedin_approve(body: dict):
    """Approuver un post LinkedIn."""
    folder = body.get("folder")
    if not folder:
        return {"success": False, "error": "folder requis"}
    
    meta_file = _LINKEDIN_DIR / "content" / folder / "meta.json"
    if not meta_file.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["status"] = "approved"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True}


@router.post("/linkedin/reject")
async def linkedin_reject(body: dict):
    """Rejeter un post LinkedIn."""
    folder = body.get("folder")
    if not folder:
        return {"success": False, "error": "folder requis"}
    
    meta_file = _LINKEDIN_DIR / "content" / folder / "meta.json"
    if not meta_file.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["status"] = "rejected"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True}


@router.get("/linkedin/carousel")
async def linkedin_carousel():
    """Liste les carousels générés."""
    carousel_dir = _LINKEDIN_DIR / "carousel"
    if not carousel_dir.exists():
        return {"count": 0, "carousels": []}
    
    carousels = []
    for f in carousel_dir.iterdir():
        if f.is_file() and f.suffix == ".pdf":
            from datetime import datetime
            carousels.append({
                "id": f.stem,
                "name": f.name,
                "size": f.stat().st_size,
                "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    
    return {"count": len(carousels), "carousels": carousels}


@router.post("/linkedin/publish")
async def linkedin_publish(body: dict):
    """Publier un post ou carousel LinkedIn."""
    folder = body.get("folder")
    carousel_id = body.get("carousel_id")
    account_id = body.get("account_id")  # ID du compte LinkedIn dans la DB
    if not folder and not carousel_id:
        return {"success": False, "error": "folder ou carousel_id requis"}
    
    try:
        sys.path.insert(0, str(_LINKEDIN_DIR))
        from agents.agent_publisher import post_linkedin
        
        if carousel_id:
            from pathlib import Path
            carousel_dir = _LINKEDIN_DIR / "carousel"
            carousel_path = carousel_dir / f"{carousel_id}.pdf"
            if carousel_path.exists():
                result = post_linkedin(str(carousel_path.parent), account_id)
                return {"success": result, "message": "Carousel publié" if result else "Erreur"}
        
        if folder:
            content_dir = _LINKEDIN_DIR / "content" / folder
            result = post_linkedin(str(content_dir), account_id)
            if result:
                return {"success": True, "message": "Publié sur LinkedIn"}
            return {"success": False, "message": "Erreur de publication"}
        
        return {"success": False, "error": "Fichier introuvable"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# TWITTER
# ══════════════════════════════════════════════════════════════════

@router.get("/twitter/stats")
async def twitter_stats():
    """Stats Twitter."""
    posts = _get_published_posts(_TWITTER_DIR)
    pending = _get_pending_posts(_TWITTER_DIR)
    return {
        "published_count": len(posts),
        "pending_count": len(pending),
        "last_post": posts[-1] if posts else None,
    }


@router.get("/twitter/pending")
async def twitter_pending():
    """Posts en attente de validation Twitter."""
    return {"count": len(_get_pending_posts(_TWITTER_DIR)), "posts": _get_pending_posts(_TWITTER_DIR)}


@router.get("/twitter/published")
async def twitter_published():
    """Posts publishés Twitter."""
    return {"count": len(_get_published_posts(_TWITTER_DIR)), "posts": _get_published_posts(_TWITTER_DIR)}


@router.post("/twitter/approve")
async def twitter_approve(body: dict):
    """Approuver un post Twitter."""
    folder = body.get("folder")
    if not folder:
        return {"success": False, "error": "folder requis"}
    
    meta_file = _TWITTER_DIR / "content" / folder / "meta.json"
    if not meta_file.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["status"] = "approved"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True}


@router.post("/twitter/reject")
async def twitter_reject(body: dict):
    """Rejeter un post Twitter."""
    folder = body.get("folder")
    if not folder:
        return {"success": False, "error": "folder requis"}
    
    meta_file = _TWITTER_DIR / "content" / folder / "meta.json"
    if not meta_file.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["status"] = "rejected"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True}


@router.get("/twitter/thread")
async def twitter_thread():
    """Liste les threads générés."""
    content_dir = _TWITTER_DIR / "content"
    if not content_dir.exists():
        return {"count": 0, "threads": []}
    
    threads = []
    for folder in content_dir.iterdir():
        if not folder.is_dir():
            continue
        if (folder / "thread.json").exists():
            try:
                thread_data = json.loads((folder / "thread.json").read_text(encoding="utf-8"))
                threads.append({
                    "id": folder.name,
                    "title": thread_data.get("title", ""),
                    "tweets": thread_data.get("tweets", []),
                    "date": folder.stat().st_mtime,
                })
            except Exception:
                pass
    
    return {"count": len(threads), "threads": threads}


@router.post("/twitter/thread")
async def create_twitter_thread(body: dict):
    """Créer un thread Twitter."""
    topic = body.get("topic", "")
    num_tweets = body.get("num_tweets", 5)
    
    if not topic:
        return {"success": False, "error": "topic requis"}
    
    from core.groq_router import call_groq
    
    prompt = f"""Génère un thread Twitter de {num_tweets} tweets sur: {topic}

Format JSON:
{{
  "title": "Titre du thread",
  "tweets": [
    {{"text": "Tweet 1 (intro hook)"}},
    {{"text": "Tweet 2 (point 1)"}},
    ...
    {{"text": "Tweet {num_tweets} (CTA)"}}
  ]
}}

Règles:
- Chaque tweet max 280 caractères
- Thread éducatif et percutant
- Dernier tweet avec CTA (follow, like, RT)"""
    
    result = await call_groq(prompt, model=Config.TWITTER_LLM_MODEL or Config.DEFAULT_LLM_MODEL)
    if not result.success:
        return {"success": False, "message": "Erreur génération IA"}
    
    import re
    content = result.data.get("content", {}).get("text", "")
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if not json_match:
        return {"success": False, "message": "Erreur parsing"}
    
    try:
        thread_data = json.loads(json_match.group())
    except:
        return {"success": False, "message": "Erreur parsing JSON"}
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = content_dir / f"thread_{timestamp}"
    folder.mkdir(exist_ok=True)
    
    (folder / "thread.json").write_text(json.dumps(thread_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    for i, tweet in enumerate(thread_data.get("tweets", []), 1):
        (folder / f"tweet_{i}.txt").write_text(tweet.get("text", ""), encoding="utf-8")
    
    return {"success": True, "thread_id": folder.name, "message": f"Thread de {len(thread_data.get('tweets', []))} tweets"}


@router.post("/twitter/publish")
async def twitter_publish(body: dict):
    """Publier un post ou thread Twitter."""
    folder = body.get("folder")
    thread_id = body.get("thread_id")
    
    if not folder and not thread_id:
        return {"success": False, "error": "folder ou thread_id requis"}
    
    try:
        sys.path.insert(0, str(_TWITTER_DIR))
        from agents.agent_publisher import post_tweet, post_thread
        
        if thread_id:
            content_dir = _TWITTER_DIR / "content" / thread_id
            result = post_thread(str(content_dir))
        elif folder:
            content_dir = _TWITTER_DIR / "content" / folder
            result = post_tweet(str(content_dir))
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# GENERATE (pour chaque plateforme)
# ══════════════════════════════════════════════════════════════════

import asyncio
import threading
from datetime import datetime

@router.get("/linkedin/generate")
async def linkedin_generate(account_id: int = None):
    """Générer un post LinkedIn via l'agent_writer (Async via Subprocess)."""
    task_id = create_task("linkedin_writer", message="Génération de posts LinkedIn...")
    
    def _run():
        try:
            import subprocess
            update_task(task_id, progress=10, status="running", log="Démarrage de l'agent LinkedIn via subprocess...")
            
            # Utiliser subprocess pour isoler l'exécution et éviter les conflits d'imports/chemins
            cmd = [sys.executable, "agents/agent_writer.py"]
            
            result = subprocess.run(
                cmd, 
                cwd=str(_LINKEDIN_DIR), 
                capture_output=True, 
                text=True, 
                encoding="utf-8"
            )
            
            if result.returncode == 0:
                # Extraire le nombre de posts générés du stdout si possible
                output = result.stdout
                count_match = re.search(r"Rédaction de (\d+) post", output)
                count = count_match.group(1) if count_match else "?"
                update_task(task_id, progress=100, status="completed", message=f"Génération LinkedIn terminée ({count} posts).")
            else:
                error_log = result.stderr or result.stdout
                update_task(task_id, status="failed", message=f"Erreur agent (code {result.returncode}): {error_log[:200]}")
        except Exception as e:
            update_task(task_id, status="failed", message=str(e))
    
    import threading
    import re
    threading.Thread(target=_run, daemon=True).start()
    return {"success": True, "task_id": task_id, "message": "Génération LinkedIn démarrée en arrière-plan."}


@router.get("/twitter/generate")
async def twitter_generate():
    """Générer et persister un post Twitter via le copywriter (Async)."""
    task_id = create_task("twitter_writer", message="Génération d'un tweet...")
    
    def _run():
        try:
            update_task(task_id, progress=20, status="running", log="Appel à l'IA Twitter...")
            from core.groq_router import call_groq
            
            prompt = """Génère un tweet percutant (max 280 caractères) sur un sujet tech/business.
            Tweet style: tranchant, direct.
            Format: 1 tweet seul."""
            
            tweet = call_groq(prompt, model=Config.TWITTER_LLM_MODEL or Config.DEFAULT_LLM_MODEL, temperature=0.85, max_tokens=280)
            
            if not tweet:
                update_task(task_id, status="failed", message="Pas de réponse de l'IA.")
                return

            tweet = tweet[:280]
            update_task(task_id, progress=60, log="Enregistrement du tweet...")
            
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            slug = f"generated_{timestamp}"
            folder = _TWITTER_DIR / "content" / slug
            folder.mkdir(parents=True, exist_ok=True)
            
            (folder / "tweet.txt").write_text(tweet, encoding="utf-8")
            
            meta = {
                "created": now.isoformat(),
                "published": False,
                "status": "pending",
            }
            (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            
            update_task(task_id, progress=100, status="completed", message="Tweet généré et enregistré.")
        except Exception as e:
            update_task(task_id, status="failed", message=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"success": True, "task_id": task_id, "message": "Génération Twitter démarrée."}


@router.get("/linkedin/recent")
async def linkedin_recent():
    """Posts récents LinkedIn."""
    return _get_published_posts(_LINKEDIN_DIR)


@router.get("/twitter/recent")
async def twitter_recent():
    """Posts récents Twitter."""
    return _get_published_posts(_TWITTER_DIR)