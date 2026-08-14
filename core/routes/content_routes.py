"""
core/routes/content_routes.py — Routes API V5 pour la gestion du contenu
"""

import json
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse

from core.config import Config
from core.routes.api_helpers import CONTENT_DIR, _get_content_dir, _list_folders, _read_post, _save_meta, _find_file, _TEXT_FILES, _IMAGE_FILES, _REEL_FILES

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

@router.get("/content")
async def api_content(request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None

    content_dir = _get_content_dir(platform, account_id)
    content_dir.mkdir(parents=True, exist_ok=True)
    folders = _list_folders(content_dir)
    posts = [_read_post(f) for f in folders]
    return {"count": len(posts), "posts": posts}

@router.get("/content/{folder}")
async def api_content_detail(folder: str, request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None
    folder_path = _get_content_dir(platform, account_id) / folder
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Post non trouvé")
    return _read_post(folder_path)

@router.post("/update_post")
async def api_update_post(req: Request):
    body = await req.json()
    platform = req.query_params.get("platform", "facebook")
    account_id = req.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None
    folder_name = body.get("folder", "")
    new_text = body.get("text", "")
    
    folder = _get_content_dir(platform, account_id) / folder_name
    if not folder.exists():
        return {"success": False, "error": "Dossier introuvable"}
    
    text_file = _find_file(folder, _TEXT_FILES)
    if text_file:
        text_file.write_text(new_text, encoding="utf-8")
        return {"success": True}
    return {"success": False, "error": "Fichier texte introuvable"}

@router.get("/image/{folder}")
async def api_image(folder: str, request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None

    folder_path = _get_content_dir(platform, account_id) / folder
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    
    image_file = _find_file(folder_path, _IMAGE_FILES)
    if not image_file:
        raise HTTPException(status_code=404, detail="Image introuvable")
    
    return FileResponse(image_file)

@router.get("/reel/{folder}")
async def api_reel(folder: str, request: Request):
    platform = request.query_params.get("platform", "facebook")
    account_id = request.query_params.get("account_id")
    try:
        account_id = int(account_id) if account_id else None
    except Exception:
        account_id = None

    folder_path = _get_content_dir(platform, account_id) / folder
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    
    reel_file = _find_file(folder_path, _REEL_FILES)
    if not reel_file:
        raise HTTPException(status_code=404, detail="Reel introuvable")
    
    return FileResponse(reel_file)