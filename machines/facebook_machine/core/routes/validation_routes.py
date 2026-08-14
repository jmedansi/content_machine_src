"""
core/routes/validation_routes.py — Routes API V5 pour la validation des posts
"""

import shutil
from fastapi import APIRouter, Request

from core.routes.api_helpers import CONTENT_DIR, _list_post_folders, _read_post, _save_meta

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

@router.get("/pending")
async def api_pending():
    folders = _list_post_folders()
    pending = [ _read_post(f) for f in folders if _read_post(f)["status"] == "pending" ]
    return {"count": len(pending), "posts": pending}

@router.post("/approve")
async def api_approve(req: Request):
    body = await req.json()
    folder = CONTENT_DIR / body.get("folder", "")
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    _save_meta(folder, {"status": "approved"})
    return {"success": True}

@router.post("/approve_all")
async def api_approve_all():
    count = 0
    for f in _list_post_folders():
        if _read_post(f)["status"] == "pending":
            _save_meta(f, {"status": "approved"})
            count += 1
    return {"success": True, "approved": count}

@router.post("/reject")
async def api_reject(req: Request):
    body = await req.json()
    folder = CONTENT_DIR / body.get("folder", "")
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    shutil.rmtree(folder)
    return {"success": True}

@router.post("/publish_now")
async def api_publish_now(req: Request):
    body = await req.json()
    folder_name = body.get("folder", "")
    folder = CONTENT_DIR / folder_name
    
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    try:
        from agents.publisher.agent import run_publisher
        res = run_publisher(str(folder))
        
        if res.success:
            _save_meta(folder, {"status": "published", "published": True})
            return {"success": True, "published": True}
        else:
            return {"success": False, "error": getattr(res, "error_cause", "Échec inconnu")}
    except Exception as e:
        return {"success": False, "error": str(e)}