"""
core/routes/validation_routes.py — Routes API V5 pour la validation des posts
"""

import shutil
from fastapi import APIRouter, Request, HTTPException

from core.routes.api_helpers import _get_content_dir, _list_folders, _read_post, _save_meta

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

def validate_request_params(request: Request) -> tuple:
    """Extrait et valide platform et account_id. Lève HTTPException si manquant."""
    platform = request.query_params.get("platform") or request.json().get("platform") if hasattr(request, 'json') else None
    account_id = request.query_params.get("account_id") or (request.json().get("account_id") if hasattr(request, 'json') else None)
    
    # Fallback depuis body si GET
    body = {}
    if request.method == "POST":
        try:
            # Note: request.json() is async, géré par FastAPI
            pass
        except:
            pass
    
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    return platform, account_id

@router.get("/pending")
async def api_pending(request: Request):
    platform = request.query_params.get("platform")
    account_id = request.query_params.get("account_id")
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    
    content_dir = _get_content_dir(platform, account_id)
    content_dir.mkdir(parents=True, exist_ok=True)
    folders = _list_folders(content_dir)
    pending = []
    for f in folders:
        meta = _read_post(f)
        if meta.get("status") in ["pending", "written", "approved"]:
            # Add URLs
            params = f"?platform={platform}&account_id={account_id}"
            meta["image_url"] = f"/api/image/{f.name}{params}" if meta.get("has_image") else None
            meta["reel_url"] = f"/api/reel/{f.name}{params}" if meta.get("has_reel") else None
            pending.append(meta)
    return {"count": len(pending), "posts": pending}

@router.post("/approve")
async def api_approve(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform")
    account_id = req.query_params.get("account_id") or body.get("account_id")
    
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    
    folder = _get_content_dir(platform, account_id) / body.get("folder", "")
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    _save_meta(folder, {"status": "approved"})
    return {"success": True}

@router.post("/approve_all")
async def api_approve_all(request: Request):
    platform = request.query_params.get("platform")
    account_id = request.query_params.get("account_id")
    
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    
    content_dir = _get_content_dir(platform, account_id)
    content_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in _list_folders(content_dir):
        if _read_post(f)["status"] in ["pending", "approved"]:
            _save_meta(f, {"status": "approved"})
            count += 1
    return {"success": True, "approved": count}

@router.post("/reject")
async def api_reject(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform")
    account_id = req.query_params.get("account_id") or body.get("account_id")
    
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    
    folder = _get_content_dir(platform, account_id) / body.get("folder", "")
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    shutil.rmtree(folder)
    return {"success": True}

@router.post("/publish_now")
async def api_publish_now(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform") or body.get("platform")
    account_id = req.query_params.get("account_id") or body.get("account_id")
    
    if not platform or not account_id:
        raise HTTPException(status_code=400, detail="platform and account_id are required")
    
    folder_name = body.get("folder", "")
    folder = _get_content_dir(platform, account_id) / folder_name
    
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