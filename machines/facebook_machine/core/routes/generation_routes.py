"""
core/routes/generation_routes.py — Routes API V5 pour la génération de contenu
"""

import threading
import uuid
from datetime import datetime
from fastapi import APIRouter, Request

from core.config import Config
from core.routes.api_helpers import CONTENT_DIR

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

@router.get("/generate")
async def api_generate(persona: str = "", topic: str = "", publish: str = "false", media: str = "none", 
                   context: str = "", objectif: str = "engagement", story: str = "", account_id: int = None, platform: str = "facebook"):
    try:
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
async def api_generate_reel(topic: str = "", script: str = "", publish: str = "false", context: str = "", objectif: str = "engagement", audience: str = "freelance", account_id: int = None, platform: str = "facebook"):
    try:
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
    new_topic = body.get("topic", "")
    account_id = req.query_params.get("account_id")
    platform = req.query_params.get("platform", "facebook")
    
    if account_id: account_id = int(account_id)
    
    from core.routes.api_helpers import _get_content_dir, _save_meta
    target_dir = _get_content_dir(platform, account_id)
    folder = target_dir / folder_name
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    from agents.scheduler.agent import process_single_post
    from datetime import datetime
    
    plan_entry = {
        "persona": "auto",
        "topic": new_topic,
        "audience": "tous"
    }
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    result = process_single_post(plan_entry, date_str, False, account_id=account_id, platform=platform)
    
    if result.success:
        _save_meta(folder, {"status": "draft"})
        return {"success": True}
    return {"success": False, "error": getattr(result, 'error_cause', 'Erreur inconnue')}

@router.post("/regenerate_image")
async def api_regenerate_image(req: Request):
    body = await req.json()
    folder_name = body.get("folder", "")
    
    folder = CONTENT_DIR / folder_name
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    try:
        from agents.post_image_generator import regenerate_image
        result = regenerate_image(str(folder))
        
        if result.success:
            return {"success": True}
        return {"success": False, "error": getattr(result, 'error_cause', 'Erreur génération')}
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
