"""
core/routes/generation_routes.py — Routes API V5 pour la génération de contenu
"""

import sys
import threading
import uuid
import json
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.config import Config
from core.routes.api_helpers import CONTENT_DIR, _get_content_dir
import sqlite3

try:
    from core.paths import PLATFORM_DB
except ImportError:
    PLATFORM_DB = {
        "facebook": str(Path(__file__).resolve().parent.parent.parent / "machines" / "facebook_machine" / "data" / "leads_station.db"),
        "linkedin": str(Path(__file__).resolve().parent.parent.parent / "machines" / "linkedin_machine" / "data" / "leads_station.db"),
        "twitter": str(Path(__file__).resolve().parent.parent.parent / "machines" / "twitter_machine" / "data" / "leads_station.db"),
    }

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

def validate_account_platform(account_id: str, platform: str):
    """Valide que account_id existe et appartient à platform"""
    if not account_id or not platform:
        raise HTTPException(status_code=400, detail="account_id and platform are required")
    # TODO: check DB
    # For now, assume valid if provided
    return True


@router.get("/generate")
async def api_generate(persona: str = "", topic: str = "", publish: str = "false", media: str = "none", 
                   context: str = "", objectif: str = "engagement", story: str = "", account_id: str = "", platform: str = "facebook"):
    try:
        validate_account_platform(account_id, platform)
        from core.task_tracker import create_task, update_task
        publish_bool = publish.lower() == "true"
        task_id = create_task("copywriter", message=f"Génération post: {topic[:30]}...")
        
        def run_generation():
            import sys, io
            try:
                update_task(task_id, progress=10, status="running", log="Démarrage...")
                from agents.scheduler.agent import process_single_post
                
                plan_entry = {
                    "persona": persona,
                    "topic": topic if topic else f"Sujet automatique ({persona})",
                    "audience": "tous",
                    "context": context,
                    "objectif": objectif,
                    "story": story
                }
                date_str = datetime.now().strftime("%Y-%m-%d")
                update_task(task_id, progress=30, log="Génération du texte...")
                
                old_img_setting = Config.POST_IMAGE_ENABLED
                if media == "none":
                    Config.POST_IMAGE_ENABLED = False
                
                result = process_single_post(plan_entry, date_str, publish_bool, task_id=task_id, current=1, total=1, account_id=account_id, platform=platform)
                Config.POST_IMAGE_ENABLED = old_img_setting
                
                if result.success:
                    update_task(task_id, progress=100, status="completed", message="Post généré!")
                else:
                    error_msg = getattr(result, 'error_cause', 'Erreur inconnue')
                    update_task(task_id, status="failed", message=error_msg)
            except Exception as e:
                update_task(task_id, status="failed", message=str(e))
        
        thread = threading.Thread(target=run_generation, daemon=True)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Génération du post démarrée en arrière-plan."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/generate_reel")
async def api_generate_reel(topic: str = "", script: str = "", publish: str = "false", context: str = "", objectif: str = "engagement", audience: str = "freelance", account_id: str = "", platform: str = "facebook"):
    try:
        validate_account_platform(account_id, platform)
        from core.task_tracker import create_task, update_task
        publish_bool = publish.lower() == "true"
        task_id = create_task("reel", message=f"Génération reel: {topic[:30]}...")
        
        def run_reel():
            import sys, io
            try:
                update_task(task_id, progress=10, status="running", log="Démarrage...")
                from agents.scheduler.agent import process_reel
                
                date_str = datetime.now().strftime("%Y-%m-%d")
                update_task(task_id, progress=30, log="Génération du script...")
                
                reel_entry = {
                    "topic": topic,
                    "audience": audience,
                    "context": context,
                    "objectif": objectif
                }
                
                result = process_reel(reel_entry, date_str, publish_bool, task_id=task_id, current=1, total=1, account_id=account_id, platform=platform)
                
                if result.success:
                    update_task(task_id, progress=100, status="completed", message="Reel généré!")
                else:
                    update_task(task_id, status="failed", message=getattr(result, 'error_cause', 'Erreur génération'))
            except Exception as e:
                update_task(task_id, status="failed", message=str(e))
        
        thread = threading.Thread(target=run_reel, daemon=True)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Génération du reel démarrée en arrière-plan."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/regenerate_post")
async def api_regenerate_post(req: Request):
    body = await req.json()
    folder_name = body.get("folder", "")
    indication = body.get("indication", "")  # note optionnelle utilisateur
    account_id = req.query_params.get("account_id")
    platform = req.query_params.get("platform", "facebook")
    
    if account_id:
        try:
            account_id = int(account_id)
        except (ValueError, TypeError):
            account_id = None
    
    from core.routes.api_helpers import _get_content_dir
    target_dir = _get_content_dir(platform, account_id)
    folder = target_dir / folder_name
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    # Lire le meta existant pour récupérer persona, topic et image_prompt
    import json as _json
    meta_path = folder / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    persona = meta.get("persona", "expert_ia")
    topic = meta.get("topic", meta.get("sujet", ""))
    original_image_prompt = meta.get("image_prompt", "")
    
    try:
        from agents.copywriter.agent import run_copywriter
        from core.llm_router import get_account_llm_config
        plan_entry = {"persona": persona, "topic": topic}
        if indication:
            plan_entry["indication"] = indication
        llm_cfg = get_account_llm_config(platform, account_id)
        res = run_copywriter(str(folder), plan_entry, account_id=account_id, platform=platform, model=llm_cfg.get("model"), llm_config=llm_cfg)
        
        if res.success:
            # Réinjection de l'image_prompt si le LLM ne l'a pas fourni
            try:
                meta_after = _json.loads(meta_path.read_text(encoding="utf-8"))
                if not meta_after.get("image_prompt") and original_image_prompt:
                    meta_after["image_prompt"] = original_image_prompt
                    meta_path.write_text(_json.dumps(meta_after, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            
            from core.routes.api_helpers import _save_meta
            _save_meta(folder, {"status": "draft"})
            
            # Lire le contenu généré
            _TEXT_FILES = ["facebook_post.txt", "linkedin_post.txt", "tweet_post.txt", "tweet.txt"]
            text_file = None
            for fname in _TEXT_FILES:
                if (folder / fname).exists():
                    text_file = folder / fname
                    break
            content = text_file.read_text(encoding="utf-8") if text_file else ""
            return {"success": True, "content": content}
        return {"success": False, "error": getattr(res, 'error_cause', 'Erreur inconnue')}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/regenerate_image")
async def api_regenerate_image(req: Request):
    body = await req.json()
    folder_name = body.get("folder", "")
    hint = body.get("indication", "")  # note optionnelle style visuel
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None

    folder = _get_content_dir(platform, account_id) / folder_name
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    try:
        from agents.image_creator.agent import run_image_creator
        res = run_image_creator(str(folder), platform=platform, hint=hint if hint else None)
        
        if res.success:
            return {"success": True}
        return {"success": False, "error": getattr(res, 'error_cause', 'Erreur génération')}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/generate_batch")
async def api_generate_batch():
    import sys, io
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (ValueError, AttributeError):
            pass

    def run_batch():
        from agents.scheduler.agent import run_pipeline
        from core.task_tracker import create_task, update_task
        import uuid

        task_id = create_task("batch", f"batch_{uuid.uuid4().hex[:8]}", "Generation batch complet")
        update_task(task_id, progress=5, status="running", log="Demarrage pipeline...")

        res = run_pipeline("all", False, task_id=task_id)

        if res.success:
            total = res.data.get("total", 100)
            success = res.data.get("success", total)
            update_task(task_id, progress=100, status="completed", message=f"Termine: {success}/{total}")
        else:
            update_task(task_id, status="failed", message=getattr(res, 'error_cause', 'Erreur batch'))

    thread = threading.Thread(target=run_batch, daemon=True)
    thread.start()
    return {"success": True, "message": "Generation du batch demarree"}

@router.get('/tasks/{task_id}')
async def api_task_status(task_id: str):
    from core.task_tracker import get_task
    task = get_task(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='Tche non trouve')
    return task

@router.get('/tasks')
async def api_active_tasks():
    from core.task_tracker import get_active_tasks
    return get_active_tasks()
