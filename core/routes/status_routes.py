"""
core/routes/status_routes.py — Routes API V5 pour le statut des services
"""

import httpx
from datetime import datetime, timezone
from fastapi import APIRouter

from core.config import Config
from core.routes.api_helpers import _load_ai_responses_config, SCHEDULE, load_schedule

router = APIRouter(prefix="/api/v5", tags=["dashboard-v5"])

@router.get("/status")
async def api_status():
    load_schedule()
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass

    now_utc = datetime.now(timezone.utc)
    benin_hour = (now_utc.hour + 1) % 24
    benin_time = f"{benin_hour:02d}:{now_utc.minute:02d}"

    current_minutes = benin_hour * 60 + now_utc.minute
    next_pub = None
    for s in SCHEDULE:
        h, m = map(int, s["time"].split(":"))
        slot_minutes = h * 60 + m
        if slot_minutes > current_minutes:
            remaining = slot_minutes - current_minutes
            next_pub = {**s, "remaining_min": remaining}
            break

    from core.routes.api_helpers import _list_post_folders, _read_post
    pending_count = len([
        f for f in _list_post_folders() 
        if _read_post(f)["status"] == "pending"
    ])

    return {
        "webhook":          True,
        "tunnel":           False,
        "scheduler":        True,
        "ollama":           ollama_ok,
        "token_valid":      bool(Config.FB_PAGE_ACCESS_TOKEN),
        "pending_count":    pending_count,
        "next_publication": next_pub,
        "benin_time":       benin_time,
        "reel_mode":        "music",
        "ai_responses":     _load_ai_responses_config(),
    }

@router.get("/llm_status")
async def api_llm_status():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass
    return {"ollama": ollama_ok}