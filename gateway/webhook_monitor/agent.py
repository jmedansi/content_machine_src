# agent.py — Serveur webhook pour commentaires Facebook
import sys
import os
import logging
from pathlib import Path
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(_ROOT_DIR))

import json
import requests
import time
import httpx
from sqlalchemy import text
import sqlite3
import shutil
import re
from datetime import datetime, timezone, timedelta

from core.paths import ROOT_DIR, PLATFORM_BASE, PLATFORM_DB, LI_MACHINE, VALID_PLATFORMS

# Shared client to reuse connection pools and reduce handshake latency
shared_httpx_client = httpx.AsyncClient(timeout=30.0)
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse, RedirectResponse

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger

logger = get_node_logger("webhook_monitor")
class DummyLog:
    def info(self, m): logger.info(m)
    def warning(self, m): logger.warning(m)
    def error(self, m): logger.error(m)
    def exception(self, m): logger.exception(m)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="Facebook Webhook Server")

# ── Session middleware (cookie signé, 7 jours) ─────────────────────────────
_SESSION_SECRET = os.getenv("SESSION_SECRET", "incidenx-session-secret-2026-change-in-prod")
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    max_age=604800,
    same_site="lax",
    https_only=False,
)

# ── CORS pour permettre les appels depuis le dashboard ──────────────────────
_CORS_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://webhook.mjautomation.shop",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dashboard : fichiers statiques et routes API ───────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent  # racine du projet
_DASHBOARD = _ROOT / "dashboard"

# Servir CSS et JS depuis leurs dossiers dédiés
app.mount("/css", StaticFiles(directory=str(_DASHBOARD / "css")), name="css")
app.mount("/js",  StaticFiles(directory=str(_DASHBOARD / "js")),  name="js")
app.mount("/icons", StaticFiles(directory=str(_DASHBOARD / "icons")), name="icons")

# Servir manifest.json
@app.get("/manifest.json", tags=["dashboard"])
async def serve_manifest():
    manifest = _DASHBOARD / "manifest.json"
    return HTMLResponse(content=manifest.read_text(encoding="utf-8"), media_type="application/json")

# ── Jinja2 Templates pour V5 ─────────────────────────────────────────
templates_v5 = Jinja2Templates(directory=str(_DASHBOARD / "templates"))

# Dashboard V5 - accessible sur / et /dashboard
@app.get("/", response_class=HTMLResponse, tags=["dashboard"])
@app.get("/dashboard", response_class=HTMLResponse, tags=["dashboard"])
async def serve_dashboard(request: Request):
    user_id = request.session.get("user_id")
    is_admin = _is_admin(user_id) if user_id else False
    return templates_v5.TemplateResponse(
        name="views/dashboard_v5.html",
        request=request,
        context={"request": request, "admin_token": _ADMIN_TOKEN, "is_admin": is_admin}
    )

# Ancien V5 (backup - depreciated)
@app.get("/dashboard-v5", response_class=HTMLResponse, tags=["dashboard"])
async def serve_dashboard_v5(request: Request):
    return templates_v5.TemplateResponse(
        name="views/dashboard_v5.html", 
        request=request, 
        context={"request": request}
    )

# Inclure toutes les routes /api/* du dashboard
from dashboard.dashboard_api_v2 import router as dashboard_router
app.include_router(dashboard_router)

# Routes API V5 (nouveau préfixe /api/v5)
from core.routes.status_routes import router as status_router
from core.routes.validation_routes import router as validation_router
from core.routes.content_routes import router as content_router
from core.routes.generation_routes import router as generation_router
from core.routes.platform_routes import router as platform_router
from core.routes.accounts import router as accounts_router
app.include_router(status_router)
app.include_router(validation_router)
app.include_router(content_router)
app.include_router(generation_router)
app.include_router(platform_router)
app.include_router(accounts_router)

_ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# ══════════════════════════════════════════════════════════════════
# LINKEDIN OAUTH - Flow automatique
# ══════════════════════════════════════════════════════════════════
import secrets
import urllib.parse
from dotenv import load_dotenv as _ld

_LINKEDIN_OAUTH_STATE = {}

import html as _html

@app.get("/api/linkedin/auth", tags=["linkedin"])
async def api_linkedin_auth():
    """Génère le lien d'autorisation LinkedIn OAuth."""
    _ld(str(ROOT_DIR / ".env"))
    client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return {"success": False, "error": "LINKEDIN_CLIENT_ID ou LINKEDIN_CLIENT_SECRET manquant dans .env"}

    state = secrets.token_urlsafe(32)
    _LINKEDIN_OAUTH_STATE[state] = datetime.now().timestamp()

    redirect_uri = "http://localhost:8000/callback"
    scopes = "openid profile w_member_social"

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scopes,
    }

    auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)
    return {"success": True, "auth_url": auth_url, "state": state}


@app.get("/callback", tags=["linkedin"])
async def api_linkedin_callback(code: str = "", state: str = "", error: str = ""):
    """Callback LinkedIn OAuth — échange le code pour un token et met à jour DB + .env."""
    if error:
        return HTMLResponse(content=f"<h1>Erreur LinkedIn OAuth</h1><p>{error}</p>", status_code=400)

    if not code or not state:
        return HTMLResponse(content="<h1>Erreur</h1><p>Code ou state manquant</p>", status_code=400)

    if state not in _LINKEDIN_OAUTH_STATE:
        return HTMLResponse(content="<h1>Erreur</h1><p>State invalide — réessayez depuis /api/linkedin/auth</p>", status_code=400)

    del _LINKEDIN_OAUTH_STATE[state]

    _ld(str(ROOT_DIR / ".env"))
    client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    redirect_uri = "http://localhost:8000/callback"

    token_resp = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    if token_resp.status_code != 200:
        return HTMLResponse(content=f"<h1>Erreur échange token</h1><pre>{_html.escape(token_resp.text)}</pre>", status_code=400)

    token_data = token_resp.json()
    access_token = token_data.get("access_token", "")

    if not access_token:
        return HTMLResponse(content=f"<h1>Token manquant</h1><pre>{_html.escape(str(token_data))}</pre>", status_code=400)

    userinfo_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers={
        "Authorization": f"Bearer {access_token}"
    })

    user_id = ""
    if userinfo_resp.status_code == 200:
        user_id = userinfo_resp.json().get("sub", "")

    import sqlite3 as _sq
    db_path = PLATFORM_DB.get("linkedin")
    try:
        conn = _sq.connect(db_path)
        conn.row_factory = _sq.Row
        cursor = conn.execute("SELECT id, credentials FROM accounts WHERE platform='linkedin' AND status='active' LIMIT 1")
        row = cursor.fetchone()
        if row:
            creds = json.loads(row["credentials"]) if row["credentials"] else {}
            creds["linkedin_token"] = access_token
            if user_id:
                creds["linkedin_user_id"] = user_id
            conn.execute("UPDATE accounts SET credentials=? WHERE id=?", (json.dumps(creds), row["id"]))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"LinkedIn OAuth DB update error: {e}")
        return HTMLResponse(content=f"<h1>Erreur DB</h1><p>{e}</p>", status_code=500)

    env_path = str(ROOT_DIR / ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        import re
        env_content = re.sub(r"LINKEDIN_TOKEN=.*", f"LINKEDIN_TOKEN={access_token}", env_content)
        if user_id:
            env_content = re.sub(r"LINKEDIN_USER_ID=.*", f"LINKEDIN_USER_ID={user_id}", env_content)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
    except Exception as e:
        logger.error(f"LinkedIn OAuth .env update error: {e}")

    return HTMLResponse(content=f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:50px">
        <h1 style="color:green">Token LinkedIn mis à jour !</h1>
        <p>User ID: <b>{user_id}</b></p>
        <p>Token: <b>{access_token[:20]}...{access_token[-10:]}</b></p>
        <p>Vous pouvez fermer cette page.</p>
        <script>setTimeout(() => window.close(), 3000)</script>
        </body></html>
    """)


# ══════════════════════════════════════════════════════════════════
# FACEBOOK OAUTH - Connexion de pages
# ══════════════════════════════════════════════════════════════════
_FB_OAUTH_STATE = {}
_FB_PAGES_CACHE = {}  # state -> list of pages (for selection step)

@app.get("/api/facebook/auth", tags=["facebook"])
async def api_facebook_auth():
    """Génère le lien d'autorisation Facebook pour connecter une page."""
    _ld(str(ROOT_DIR / ".env"))
    app_id = os.getenv("FB_APP_ID", "")
    app_secret = os.getenv("FB_APP_SECRET", "")

    if not app_id or not app_secret:
        return {"success": False, "error": "FB_APP_ID ou FB_APP_SECRET manquant dans .env"}

    state = secrets.token_urlsafe(32)
    _FB_OAUTH_STATE[state] = datetime.now().timestamp()

    redirect_uri = "https://webhook.mjautomation.shop/fb-callback"
    scopes = "pages_manage_posts,pages_read_engagement,pages_show_list,pages_manage_metadata"

    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scopes,
        "response_type": "code",
    }

    auth_url = "https://www.facebook.com/v18.0/dialog/oauth?" + urllib.parse.urlencode(params)
    return {"success": True, "auth_url": auth_url, "state": state}


@app.get("/fb-callback", tags=["facebook"])
async def api_facebook_callback(code: str = "", state: str = "", error: str = "", request: Request = None):
    """Callback Facebook OAuth — échange le code, récupère les pages, affiche la sélection."""
    if error:
        return HTMLResponse(content=f"<h1>Erreur Facebook OAuth</h1><p>{error}</p>", status_code=400)

    if not code or not state:
        return HTMLResponse(content="<h1>Erreur</h1><p>Code ou state manquant</p>", status_code=400)

    if state not in _FB_OAUTH_STATE:
        return HTMLResponse(content="<h1>Erreur</h1><p>State invalide — réessayez depuis le dashboard</p>", status_code=400)

    del _FB_OAUTH_STATE[state]

    _ld(str(ROOT_DIR / ".env"))
    app_id = os.getenv("FB_APP_ID", "")
    app_secret = os.getenv("FB_APP_SECRET", "")
    redirect_uri = "https://webhook.mjautomation.shop/fb-callback"

    # 1. Échanger le code pour un user access token (court durée)
    token_resp = requests.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "client_secret": app_secret,
        "code": code,
    })

    if token_resp.status_code != 200:
        return HTMLResponse(content=f"<h1>Erreur échange token</h1><pre>{_html.escape(token_resp.text)}</pre>", status_code=400)

    token_json = token_resp.json()
    short_token = token_json.get("access_token", "")
    if not short_token:
        return HTMLResponse(content=f"<h1>Token manquant</h1><pre>{_html.escape(str(token_json))}</pre>", status_code=400)

    logger.info(f"FB OAuth: short token obtained, length={len(short_token)}")

    # Vérifier les permissions accordées
    perm_resp = requests.get("https://graph.facebook.com/v18.0/me/permissions", params={
        "access_token": short_token,
    })
    granted_perms = []
    if perm_resp.status_code == 200:
        for p in perm_resp.json().get("data", []):
            if p.get("status") == "granted":
                granted_perms.append(p.get("permission", ""))
    logger.info(f"FB OAuth: granted permissions = {granted_perms}")

    # 2. Échanger pour un token long durée (60 jours)
    ll_resp = requests.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": short_token,
    })

    long_token = short_token
    if ll_resp.status_code == 200:
        long_token = ll_resp.json().get("access_token", short_token)
        logger.info(f"FB OAuth: long-lived token obtained, length={len(long_token)}")
    else:
        logger.warning(f"FB OAuth: long-lived exchange failed: {ll_resp.text[:200]}")

    # 3. Récupérer la liste des pages gérées
    pages_resp = requests.get("https://graph.facebook.com/v18.0/me/accounts", params={
        "access_token": long_token,
    })

    if pages_resp.status_code != 200:
        return HTMLResponse(content=f"<h1>Erreur récupération pages</h1><pre>{_html.escape(pages_resp.text)}</pre>", status_code=400)

    pages = pages_resp.json().get("data", [])

    if not pages:
        perms_info = ", ".join(granted_perms) if granted_perms else "aucune"
        return HTMLResponse(content=f"""
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h1>Aucune page trouvée</h1>
            <p>Vous n'avez aucune page Facebook accessible avec ce compte.</p>
            <div style="background:#f3f4f6;padding:16px;border-radius:8px;text-align:left;margin:20px auto;max-width:500px">
                <p style="margin:0 0 8px 0"><b>Permissions accordées :</b></p>
                <p style="margin:0;font-family:monospace;font-size:13px">{perms_info}</p>
            </div>
            <p><b>Pour connecter des pages, l'app nécessite les permissions :</b></p>
            <ul style="text-align:left;max-width:400px;margin:12px auto">
                <li>pages_show_list</li>
                <li>pages_manage_posts</li>
                <li>pages_read_engagement</li>
            </ul>
            <p style="color:#dc2626;font-weight:600">En mode Live, ces permissions nécessitent une App Review Facebook.</p>
            <script>setTimeout(() => window.close(), 8000)</script>
            </body></html>
        """)

    if len(pages) == 1:
        # Une seule page → récupérer le token infinite puis sauvegarder
        page = pages[0]
        infinite_token = _exchange_for_infinite_page_token(page["id"], long_token)
        final_token = infinite_token or page.get("access_token", "")
        return await _save_fb_page(page["id"], page["name"], final_token, long_token, request, expires_in=None)

    # Plusieurs pages → afficher la sélection
    _FB_PAGES_CACHE[state] = {"pages": pages, "user_token": long_token}
    pages_html = ""
    for p in pages:
        pages_html += f"""
            <label style="display:flex;align-items:center;gap:12px;padding:16px;border:1px solid #e5e7eb;border-radius:12px;cursor:pointer;transition:all 0.2s" 
                   onmouseover="this.style.borderColor='#3b82f6'" onmouseout="this.style.borderColor='#e5e7eb'">
                <input type="radio" name="page_id" value="{p['id']}" data-name="{p['name']}" data-token="{p.get('access_token','')}" style="width:18px;height:18px;accent-color:#3b82f6">
                <div>
                    <p style="font-weight:600;margin:0">{p['name']}</p>
                    <p style="font-size:12px;color:#9ca3af;margin:2px 0 0 0">ID: {p['id']}</p>
                </div>
            </label>
        """

    return HTMLResponse(content=f"""
        <html><body style="font-family:sans-serif;padding:40px;max-width:500px;margin:0 auto">
        <h1 style="margin-bottom:8px">Sélectionnez une page</h1>
        <p style="color:#6b7280;margin-bottom:24px">{len(pages)} pages trouvées</p>
        <form id="page-form" style="display:flex;flex-direction:column;gap:12px">
            {pages_html}
        </form>
        <button onclick="submitPage()" style="width:100%;margin-top:24px;padding:14px;background:#3b82f6;color:white;border:none;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer">
            Connecter cette page
        </button>
        <script>
        function submitPage() {{
            var selected = document.querySelector('input[name="page_id"]:checked');
            if (!selected) {{ alert('Sélectionnez une page'); return; }}
            fetch('/api/facebook/select-page', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    page_id: selected.value,
                    page_name: selected.dataset.name,
                    page_token: selected.dataset.token,
                    state: '{state}'
                }})
            }})
            .then(r => r.json())
            .then(d => {{
                if (d.success) {{
                    document.body.innerHTML = '<div style="text-align:center;padding:50px;font-family:sans-serif"><h1 style="color:green">Page connectée !</h1><p>' + selected.dataset.name + '</p><p>Vous pouvez fermer cette page.</p></div>';
                    setTimeout(() => window.close(), 2000);
                }} else {{
                    alert('Erreur: ' + (d.error || 'inconnue'));
                }}
            }});
        }}
        </script>
        </body></html>
    """)


@app.post("/api/facebook/select-page", tags=["facebook"])
async def api_facebook_select_page(req: Request):
    """Sauvegarde la page Facebook sélectionnée dans DB + .env."""
    body = await req.json()
    page_id = body.get("page_id", "").strip()
    page_name = body.get("page_name", "").strip()
    page_token = body.get("page_token", "").strip()
    state = body.get("state", "")

    if not page_id or not page_token:
        return {"success": False, "error": "page_id et page_token requis"}

    # Récupérer le user_token depuis le cache pour obtenir un token infinite
    user_token = ""
    cached = _FB_PAGES_CACHE.get(state, {})
    if cached:
        user_token = cached.get("user_token", "")

    infinite_token = _exchange_for_infinite_page_token(page_id, user_token) if user_token else ""
    final_token = infinite_token or page_token

    return await _save_fb_page(page_id, page_name, final_token, user_token, req, expires_in=None)


def _exchange_for_infinite_page_token(page_id: str, long_lived_user_token: str) -> str:
    """Échange un long-lived user token pour un page token qui n'expire jamais.
    
    Appelle GET /v18.0/{page_id}?fields=access_token avec le user token.
    Facebook retourne un page token permanent si le user token est long-lived.
    """
    try:
        resp = requests.get(
            f"https://graph.facebook.com/v18.0/{page_id}",
            params={
                "fields": "access_token",
                "access_token": long_lived_user_token,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            infinite_token = data.get("access_token", "")
            if infinite_token and infinite_token != long_lived_user_token:
                logger.info(f"FB OAuth: infinite page token obtained for page {page_id}, length={len(infinite_token)}")
                return infinite_token
            else:
                logger.warning(f"FB OAuth: page token exchange returned same token or empty for {page_id}")
        else:
            logger.warning(f"FB OAuth: page token exchange failed for {page_id}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"FB OAuth: page token exchange exception: {e}")
    return ""


async def _save_fb_page(page_id: str, page_name: str, page_token: str, user_token: str, request: Request = None, expires_in: int = None):
    """Sauvegarde la page Facebook dans DB + .env + dossiers complets."""
    FB_MACHINE = PLATFORM_BASE["facebook"]
    DB_PATH = str(FB_MACHINE / "data/leads_station.db")

    # Calculer expires_at (null = illimité)
    expires_at = None
    if expires_in and expires_in > 0:
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    DEFAULT_SCHEDULE = {
        "schedule": [
            {"time": "08:00", "persona": "ia_design", "type": "post"},
            {"time": "10:30", "persona": "post_court", "type": "post"},
            {"time": "12:30", "persona": "mini_formation", "type": "post"},
            {"time": "14:00", "persona": "storytelling_pro", "type": "post"},
            {"time": "16:30", "persona": "ia_integration", "type": "post"},
            {"time": "19:00", "persona": "business_auto", "type": "post"},
            {"time": "20:30", "persona": "cta", "type": "post"},
        ]
    }

    # 1. Mettre à jour la DB
    account_id = None
    is_new = False
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Chercher un compte Facebook existant pour cette page
        cursor = conn.execute(
            "SELECT id, credentials FROM accounts WHERE platform='facebook' AND status='active'"
        )
        existing = None
        for row in cursor.fetchall():
            creds = json.loads(row["credentials"]) if row["credentials"] else {}
            if creds.get("page_id") == page_id:
                existing = row
                break

        if existing:
            # Mettre à jour le token
            creds = json.loads(existing["credentials"]) if existing["credentials"] else {}
            creds["access_token"] = page_token
            creds["token_type"] = "page"
            creds["expires_at"] = expires_at
            if user_token:
                creds["user_token"] = user_token
            conn.execute("UPDATE accounts SET credentials=? WHERE id=?", (json.dumps(creds), existing["id"]))
            account_id = existing["id"]
        else:
            # Créer un nouveau compte
            is_new = True
            creds = {"page_id": page_id, "access_token": page_token, "token_type": "page", "expires_at": expires_at}
            if user_token:
                creds["user_token"] = user_token
            settings = {"scheduler_active": True, "llm_model": "llama-3.3-70b-versatile"}
            cursor = conn.execute(
                "INSERT INTO accounts (platform, name, credentials, settings, status) VALUES (?, ?, ?, ?, ?)",
                ("facebook", page_name, json.dumps(creds), json.dumps(settings), "active")
            )
            account_id = cursor.lastrowid

        conn.commit()
        conn.close()
        logger.info(f"Facebook page saved: {page_name} (page_id={page_id}, account_id={account_id}, new={is_new})")

        # Ajouter automatiquement le compte à l'utilisateur connecté
        if account_id and request:
            try:
                user_id = None
                if hasattr(request, 'session'):
                    user_id = request.session.get("user_id")
                if not user_id:
                    user_id = request.headers.get("X-User-Id", "")
                if user_id:
                    from core.db import SessionLocal as _UsersDB
                    from sqlalchemy import text as _text
                    udb = _UsersDB()
                    try:
                        row = udb.execute(_text("SELECT account_ids FROM users WHERE id=:uid AND active=1"), {"uid": int(user_id)}).fetchone()
                        if row and row[0] and row[0] != "null":
                            current_ids = json.loads(row[0])
                        else:
                            current_ids = []
                        if account_id not in current_ids:
                            current_ids.append(account_id)
                            udb.execute(_text("UPDATE users SET account_ids=:acc WHERE id=:uid"), {"acc": json.dumps(current_ids), "uid": int(user_id)})
                            udb.commit()
                            logger.info(f"Auto-added account {account_id} to user {user_id}'s account_ids: {current_ids}")
                    finally:
                        udb.close()
            except Exception as e:
                logger.warning(f"Could not auto-update user account_ids: {e}")
    except Exception as e:
        logger.error(f"Facebook OAuth DB save error: {e}")
        return {"success": False, "error": f"DB: {e}"}

    # 2. Créer la structure de dossiers + schedule + personas (si nouveau compte)
    if is_new and account_id:
        try:
            account_dir = FB_MACHINE / "accounts" / str(account_id)
            persona_dir = account_dir / "persona"
            content_dir = account_dir / "content"

            # Dossiers de base
            persona_dir.mkdir(parents=True, exist_ok=True)
            content_dir.mkdir(parents=True, exist_ok=True)

            # schedule.json
            schedule_path = account_dir / "schedule.json"
            if not schedule_path.exists():
                schedule_path.write_text(json.dumps(DEFAULT_SCHEDULE, indent=2, ensure_ascii=False), encoding="utf-8")

            # meta.json
            meta_path = account_dir / "meta.json"
            if not meta_path.exists():
                meta_path.write_text(json.dumps({
                    "name": page_name,
                    "platform": "facebook",
                    "page_id": page_id,
                    "created": datetime.now().isoformat()
                }, indent=2, ensure_ascii=False), encoding="utf-8")

            # Copier les personas depuis les templates
            template_dir = FB_MACHINE / "persona"
            if template_dir.exists():
                for item in template_dir.iterdir():
                    if item.is_dir() and not item.name.startswith("_OLD"):
                        dest = persona_dir / item.name
                        if not dest.exists():
                            shutil.copytree(item, dest)
                            logger.info(f"  Copied persona: {item.name}")

            logger.info(f"Account {account_id} folder structure created")
        except Exception as e:
            logger.error(f"Folder setup error: {e}")
            # Non bloquant — la DB est OK

    # 3. Mettre à jour le .env (page par défaut)
    try:
        env_path = str(ROOT_DIR / ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        env_content = re.sub(r"FB_PAGE_ID=.*", f"FB_PAGE_ID={page_id}", env_content)
        env_content = re.sub(r"FB_PAGE_ACCESS_TOKEN=.*", f"FB_PAGE_ACCESS_TOKEN={page_token}", env_content)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
    except Exception as e:
        logger.error(f"Facebook OAuth .env update error: {e}")

    return {"success": True, "page_id": page_id, "page_name": page_name, "account_id": account_id}


@app.get("/api/facebook/token-status", tags=["facebook"])
async def api_facebook_token_status(account_id: int = None):
    """Vérifie la validité du token Facebook d'un compte et retourne le countdown."""
    FB_MACHINE = PLATFORM_BASE["facebook"]
    DB_PATH = str(FB_MACHINE / "data/leads_station.db")

    if not account_id:
        return {"success": False, "error": "account_id requis"}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT credentials FROM accounts WHERE id=? AND platform='facebook'", (account_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"success": False, "error": "Compte introuvable"}

        creds = json.loads(row["credentials"]) if row["credentials"] else {}
        token = creds.get("access_token", "")
        page_id = creds.get("page_id", "")
        expires_at = creds.get("expires_at")
        token_type = creds.get("token_type", "unknown")

        if not token:
            return {"success": True, "valid": False, "reason": "Token manquant", "expires_at": None, "token_type": token_type}

        # Tester le token via Graph API
        try:
            r = requests.get(
                f"https://graph.facebook.com/v18.0/{page_id}",
                params={"access_token": token, "fields": "id,name"},
                timeout=10,
            )
            valid = r.status_code == 200 and "id" in r.json()
        except Exception:
            valid = False

        return {
            "success": True,
            "valid": valid,
            "expires_at": expires_at,
            "token_type": token_type,
            "page_id": page_id,
        }
    except Exception as e:
        logger.error(f"Facebook token-status error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/facebook/refresh-token", tags=["facebook"])
async def api_facebook_refresh_token(req: Request):
    """Régénère le page access token via le user_token stocké en DB.
    
    Utilise le user_token (long-lived, ~60j) pour obtenir un nouveau
    page token infinite via GET /{page_id}?fields=access_token.
    """
    FB_MACHINE = PLATFORM_BASE["facebook"]
    DB_PATH = str(FB_MACHINE / "data/leads_station.db")

    body = await req.json()
    account_id = body.get("account_id")

    if not account_id:
        return {"success": False, "error": "account_id requis"}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id, name, credentials FROM accounts WHERE id=? AND platform='facebook'", (account_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"success": False, "error": "Compte introuvable"}

        creds = json.loads(row["credentials"]) if row["credentials"] else {}
        user_token = creds.get("user_token", "")
        page_id = creds.get("page_id", "")

        if not user_token:
            conn.close()
            return {
                "success": False,
                "error": "Aucun user_token stocké. Ré-authentifiez-vous via /api/facebook/auth pour sauvegarder le user_token.",
            }

        if not page_id:
            conn.close()
            return {"success": False, "error": "page_id manquant dans les credentials"}

        # Tenter l'échange vers un token infinite
        infinite_token = _exchange_for_infinite_page_token(page_id, user_token)

        if not infinite_token:
            # Le user_token est peut-être expiré — vérifier sa validité
            try:
                check_resp = requests.get(
                    f"https://graph.facebook.com/v18.0/me",
                    params={"access_token": user_token},
                    timeout=10,
                )
                user_token_valid = check_resp.status_code == 200
            except Exception:
                user_token_valid = False

            if not user_token_valid:
                conn.close()
                return {
                    "success": False,
                    "error": "Le user_token a expiré. Ré-authentifiez-vous via /api/facebook/auth.",
                    "user_token_expired": True,
                }
            else:
                conn.close()
                return {"success": False, "error": "Échec de l'échange page token. Vérifiez les permissions de l'app."}

        # Mettre à jour la DB avec le nouveau token
        creds["access_token"] = infinite_token
        creds["token_type"] = "page"
        creds["expires_at"] = None
        conn.execute("UPDATE accounts SET credentials=? WHERE id=?", (json.dumps(creds), account_id))
        conn.commit()
        conn.close()

        # Mettre à jour le .env si c'est le compte par défaut
        try:
            env_path = str(ROOT_DIR / ".env")
            with open(env_path, "r", encoding="utf-8") as f:
                env_content = f.read()
            env_content = re.sub(r"FB_PAGE_ACCESS_TOKEN=.*", f"FB_PAGE_ACCESS_TOKEN={infinite_token}", env_content)
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)
        except Exception as e:
            logger.warning(f"Could not update .env after token refresh: {e}")

        logger.info(f"Facebook token refreshed for account {account_id} (page {page_id})")
        return {
            "success": True,
            "page_id": page_id,
            "token_length": len(infinite_token),
            "message": "Token régénéré avec succès (infinite).",
        }

    except Exception as e:
        logger.error(f"Facebook refresh-token error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/facebook/disconnect", tags=["facebook"])
async def api_facebook_disconnect(req: Request):
    """Déconnecte une page Facebook : révoque le token, supprime le compte et les dossiers."""
    FB_MACHINE = PLATFORM_BASE["facebook"]
    DB_PATH = str(FB_MACHINE / "data/leads_station.db")

    body = await req.json()
    account_id = body.get("account_id")

    if not account_id:
        return {"success": False, "error": "account_id requis"}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("SELECT credentials FROM accounts WHERE id=? AND platform='facebook'", (account_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"success": False, "error": "Compte introuvable"}

        creds = json.loads(row["credentials"]) if row["credentials"] else {}
        token = creds.get("access_token", "")
        page_id = creds.get("page_id", "")

        # 1. Révoquer le token via Graph API (best effort)
        if token:
            try:
                requests.delete(
                    "https://graph.facebook.com/v18.0/me/permissions",
                    params={"access_token": token},
                    timeout=10,
                )
            except Exception:
                pass

        # 2. Supprimer de la DB
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        conn.commit()
        conn.close()

        # 3. Supprimer le dossier du compte
        account_dir = FB_MACHINE / "accounts" / str(account_id)
        if account_dir.exists():
            try:
                shutil.rmtree(account_dir)
            except Exception as e:
                logger.warning(f"Could not remove account dir {account_dir}: {e}")

        # 4. Retirer du user account_ids
        try:
            user_id = None
            if hasattr(req, 'session'):
                user_id = req.session.get("user_id")
            if not user_id:
                user_id = req.headers.get("X-User-Id", "")
            if user_id:
                from core.db import SessionLocal as _UsersDB
                from sqlalchemy import text as _text
                udb = _UsersDB()
                try:
                    row = udb.execute(_text("SELECT account_ids FROM users WHERE id=:uid AND active=1"), {"uid": int(user_id)}).fetchone()
                    if row and row[0] and row[0] != "null":
                        current_ids = json.loads(row[0])
                        if account_id in current_ids:
                            current_ids.remove(account_id)
                            udb.execute(_text("UPDATE users SET account_ids=:acc WHERE id=:uid"), {"acc": json.dumps(current_ids), "uid": int(user_id)})
                            udb.commit()
                finally:
                    udb.close()
        except Exception as e:
            logger.warning(f"Could not update user account_ids: {e}")

        logger.info(f"Facebook account {account_id} (page_id={page_id}) disconnected")
        return {"success": True}
    except Exception as e:
        logger.error(f"Facebook disconnect error: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# AUTH - Code simple + localStorage
# ══════════════════════════════════════════════════════════════════
from core.db import SessionLocal as _SessionLocal

ADMIN_CODE = os.getenv("ADMIN_CODE", "255800")

def _init_users_table():
    """Crée la table users si elle n'existe pas + insère l'admin + ajoute email/facebook_id si manquants."""
    from sqlalchemy import inspect
    try:
        db = _SessionLocal()
        try:
            inspector = inspect(db.get_bind())
            if "users" not in inspector.get_table_names():
                db.execute(text("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        code TEXT UNIQUE NOT NULL,
                        email TEXT DEFAULT '',
                        facebook_id TEXT DEFAULT '',
                        account_ids TEXT DEFAULT '[]',
                        active INTEGER DEFAULT 1
                    )
                """))
                db.commit()
                db.execute(
                    text("INSERT INTO users (name, code, account_ids) VALUES (:name, :code, :acc)"),
                    {"name": "Admin", "code": ADMIN_CODE, "acc": "null"},
                )
                db.commit()
                logger.info("Table 'users' créée avec admin par défaut (code: 255800)")
            else:
                # Ajouter les colonnes manquantes (migration)
                columns = [col["name"] for col in inspector.get_columns("users")]
                if "email" not in columns:
                    db.execute(text("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''"))
                    db.commit()
                    logger.info("Colonne 'email' ajoutée à la table users")
                if "facebook_id" not in columns:
                    db.execute(text("ALTER TABLE users ADD COLUMN facebook_id TEXT DEFAULT ''"))
                    db.commit()
                    logger.info("Colonne 'facebook_id' ajoutée à la table users")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Erreur init users table: {e}")


@app.get("/login", tags=["auth"])
async def login_page():
    login_path = ROOT_DIR / "dashboard" / "templates" / "login.html"
    if login_path.exists():
        return HTMLResponse(content=login_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Login page not found</h1>", status_code=404)


@app.post("/api/auth/login", tags=["auth"])
async def auth_login(req: Request):
    """Reçoit un code, crée une session et retourne user_id + name + account_ids."""
    body = await req.json()
    code = body.get("code", "").strip()
    if not code:
        return {"success": False, "error": "Code requis"}

    try:
        db = _SessionLocal()
        try:
            row = db.execute(
                text("SELECT id, name, account_ids FROM users WHERE code=:code AND active=1"),
                {"code": code}
            ).fetchone()
            if not row:
                return {"success": False, "error": "Code incorrect"}
            import json as _json
            # Créer la session cookie
            req.session["user_id"] = row[0]
            req.session["user_name"] = row[1]
            return {
                "success": True,
                "user_id": row[0],
                "name": row[1],
                "account_ids": _json.loads(row[2]) if row[2] else None,
            }
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/auth/logout", tags=["auth"])
async def auth_logout(request: Request):
    """Détruit la session et déconnecte l'utilisateur."""
    request.session.clear()
    return {"success": True}


@app.get("/api/auth/me", tags=["auth"])
async def auth_me(request: Request):
    """Vérifie si l'utilisateur a une session valide."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False}
    try:
        db = _SessionLocal()
        try:
            row = db.execute(
                text("SELECT id, name, code, account_ids FROM users WHERE id=:uid AND active=1"),
                {"uid": int(user_id)}
            ).fetchone()
            if not row:
                return {"authenticated": False}
            import json as _json
            return {
                "authenticated": True,
                "user_id": row[0],
                "name": row[1],
                "is_admin": row[2] == ADMIN_CODE,
                "account_ids": _json.loads(row[3]) if row[3] else None,
            }
        finally:
            db.close()
    except Exception:
        return {"authenticated": False}


# ── Admin : gestion des users ───────────────────────────────

def _is_admin(user_id):
    """Vérifie si le user est admin (code 255800)."""
    if not user_id:
        return False
    try:
        db = _SessionLocal()
        try:
            row = db.execute(text("SELECT code FROM users WHERE id=:uid"), {"uid": int(user_id)}).fetchone()
            return row and row[0] == ADMIN_CODE
        finally:
            db.close()
    except Exception:
        return False


@app.get("/api/admin/users", tags=["admin"])
async def admin_list_users(request: Request):
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    try:
        db = _SessionLocal()
        try:
            rows = db.execute(text("SELECT id, name, code, email, facebook_id, account_ids, active FROM users ORDER BY id")).fetchall()
            import json as _json
            users = [{"id": r[0], "name": r[1], "code": r[2], "email": r[3] or "", "facebook_id": r[4] or "", "account_ids": _json.loads(r[5]) if r[5] else None, "active": bool(r[6])} for r in rows]
            return {"success": True, "users": users}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/users", tags=["admin"])
async def admin_create_user(request: Request):
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    body = await request.json()
    name = body.get("name", "").strip()
    code = body.get("code", "").strip()
    email = body.get("email", "").strip()
    facebook_id = body.get("facebook_id", "").strip()
    account_ids = body.get("account_ids", [])
    if not name or not code:
        return {"success": False, "error": "Nom et code requis"}
    try:
        db = _SessionLocal()
        try:
            db.execute(
                text("INSERT INTO users (name, code, email, facebook_id, account_ids) VALUES (:name, :code, :email, :fb_id, :acc)"),
                {"name": name, "code": code, "email": email, "fb_id": facebook_id, "acc": json.dumps(account_ids)},
            )
            db.commit()
            return {"success": True}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/users/{uid}/toggle", tags=["admin"])
async def admin_toggle_user(uid: int, request: Request):
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    try:
        db = _SessionLocal()
        try:
            row = db.execute(text("SELECT active FROM users WHERE id=:uid"), {"uid": uid}).fetchone()
            if row:
                db.execute(text("UPDATE users SET active=:val WHERE id=:uid"), {"val": 0 if row[0] else 1, "uid": uid})
                db.commit()
            return {"success": True}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/admin/users/{uid}", tags=["admin"])
async def admin_delete_user(uid: int, request: Request):
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    try:
        db = _SessionLocal()
        try:
            db.execute(text("DELETE FROM users WHERE id=:uid"), {"uid": uid})
            db.commit()
            return {"success": True}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.put("/api/admin/users/{uid}", tags=["admin"])
async def admin_update_user(uid: int, request: Request):
    """Met à jour un utilisateur (nom, code, email, facebook_id, comptes autorisés)."""
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    body = await request.json()
    name = body.get("name", "").strip()
    code = body.get("code", "").strip()
    email = body.get("email", "").strip()
    facebook_id = body.get("facebook_id", "").strip()
    account_ids = body.get("account_ids")
    try:
        db = _SessionLocal()
        try:
            updates = []
            params = {"uid": uid}
            if name:
                updates.append("name=:name")
                params["name"] = name
            if code:
                updates.append("code=:code")
                params["code"] = code
            if email is not None:
                updates.append("email=:email")
                params["email"] = email
            if facebook_id is not None:
                updates.append("facebook_id=:fb_id")
                params["fb_id"] = facebook_id
            if account_ids is not None:
                updates.append("account_ids=:acc")
                params["acc"] = json.dumps(account_ids)
            if updates:
                db.execute(text(f"UPDATE users SET {', '.join(updates)} WHERE id=:uid"), params)
                db.commit()
            return {"success": True}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════
# FACEBOOK APP INVITATIONS — Gestion des invitations Testeur
# ══════════════════════════════════════════════════════════════

@app.get("/api/admin/fb-invitations", tags=["admin", "facebook"])
async def admin_list_fb_invitations(request: Request):
    """Liste toutes les invitations Facebook App."""
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    
    try:
        db = _SessionLocal()
        try:
            from core.db import FBAppInvitation
            invitations = db.query(FBAppInvitation).order_by(FBAppInvitation.invited_at.desc()).all()
            
            result = []
            for inv in invitations:
                # Vérifier si expiré
                status = inv.status
                if status == "pending" and inv.is_expired():
                    status = "expired"
                
                result.append({
                    "id": inv.id,
                    "user_id": inv.user_id,
                    "user_name": inv.user_name,
                    "user_code": inv.user_code,
                    "invited_by": inv.invited_by,
                    "status": status,
                    "facebook_user_id": inv.facebook_user_id,
                    "notes": inv.notes,
                    "invited_at": inv.invited_at.isoformat() if inv.invited_at else None,
                    "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
                    "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                })
            
            return {"success": True, "invitations": result}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/fb-invite/{target_user_id}", tags=["admin", "facebook"])
async def admin_create_fb_invitation(target_user_id: int, request: Request):
    """Crée une invitation Facebook App pour un utilisateur."""
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    
    try:
        db = _SessionLocal()
        try:
            from core.db import FBAppInvitation
            
            # Récupérer les infos de l'utilisateur cible
            user_row = db.execute(
                text("SELECT id, name, code, email FROM users WHERE id = :uid"),
                {"uid": target_user_id}
            ).fetchone()
            
            if not user_row:
                return {"success": False, "error": "Utilisateur non trouvé"}
            
            user_email = user_row[3] or ""
            
            # Vérifier si une invitation pending existe déjà
            existing = db.query(FBAppInvitation).filter(
                FBAppInvitation.user_id == target_user_id,
                FBAppInvitation.status == "pending"
            ).first()
            
            if existing and not existing.is_expired():
                return {"success": False, "error": "Une invitation est déjà en attente pour cet utilisateur"}
            
            # Créer l'invitation
            invitation = FBAppInvitation(
                user_id=target_user_id,
                user_name=user_row[1],
                user_code=user_row[2],
                invited_by=user_id,
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.add(invitation)
            db.commit()
            
            # Envoyer notification Telegram avec l'email
            _ld(str(ROOT_DIR / ".env"))
            app_id = os.getenv("FB_APP_ID", "")
            _send_invitation_notification(user_row[1], user_email, app_id)
            
            logger.info(f"FB Invitation créée: user={user_row[1]} (email={user_email}), par admin={user_id}")
            
            return {
                "success": True,
                "invitation_id": invitation.id,
                "dashboard_meta_url": f"https://developers.facebook.com/apps/{app_id}/roles/roles/" if app_id else None
            }
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/fb-invite/{invite_id}/verify", tags=["admin", "facebook"])
async def admin_verify_fb_invitation(invite_id: int, request: Request):
    """Vérifie le statut d'une invitation (si l'utilisateur peut se connecter = testeur accepté)."""
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    
    try:
        db = _SessionLocal()
        try:
            from core.db import FBAppInvitation
            
            invitation = db.query(FBAppInvitation).filter(FBAppInvitation.id == invite_id).first()
            if not invitation:
                return {"success": False, "error": "Invitation non trouvée"}
            
            # Vérifier si l'utilisateur a un compte actif dans notre DB
            # Si oui, cela signifie qu'il a pu passer l'OAuth = il est testeur
            user_accounts = db.execute(
                text("SELECT account_ids FROM users WHERE id = :uid"),
                {"uid": invitation.user_id}
            ).fetchone()
            
            if user_accounts and user_accounts[0]:
                import json as _json
                account_ids = _json.loads(user_accounts[0])
                if account_ids:  # L'utilisateur a des comptes assignés
                    invitation.status = "accepted"
                    invitation.accepted_at = datetime.now(timezone.utc)
                    db.commit()
                    
                    # Notification Telegram
                    _send_invitation_accepted_notification(invitation.user_name)
                    
                    return {"success": True, "status": "accepted", "message": "L'utilisateur a été ajouté comme testeur"}
            
            # Vérifier si expiré
            if invitation.is_expired():
                invitation.status = "expired"
                db.commit()
                return {"success": True, "status": "expired", "message": "L'invitation a expiré"}
            
            return {"success": True, "status": "pending", "message": "L'invitation est toujours en attente"}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/admin/fb-invite/{invite_id}/revoke", tags=["admin", "facebook"])
async def admin_revoke_fb_invitation(invite_id: int, request: Request):
    """Révoque une invitation Facebook App."""
    user_id = request.session.get("user_id")
    if not _is_admin(user_id):
        return {"success": False, "error": "Accès admin requis"}
    
    try:
        db = _SessionLocal()
        try:
            from core.db import FBAppInvitation
            
            invitation = db.query(FBAppInvitation).filter(FBAppInvitation.id == invite_id).first()
            if not invitation:
                return {"success": False, "error": "Invitation non trouvée"}
            
            invitation.status = "revoked"
            db.commit()
            
            logger.info(f"FB Invitation révoquée: id={invite_id}, user={invitation.user_name}")
            
            return {"success": True, "message": "Invitation révoquée"}
        finally:
            db.close()
    except Exception as e:
        return {"success": False, "error": str(e)}


def _send_invitation_notification(user_name: str, user_email: str, app_id: str):
    """Envoie une notification Telegram pour une nouvelle invitation."""
    try:
        from core.notifier import send_telegram_message
        email_info = f"\n📧 Email: `{user_email}`" if user_email else "\n📧 Email: non renseigné"
        msg = (
            "📩 *Nouvelle Invitation Facebook App*\n\n"
            f"👤 Invité: *{user_name}*"
            f"{email_info}\n"
            f"📅 Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"👉 Ajoutez l'utilisateur comme *Tester* dans le Dashboard Meta:\n"
            f"https://developers.facebook.com/apps/{app_id}/roles/roles/\n\n"
            f"⚠️ L'utilisateur doit avoir un compte Meta Developer pour être ajouté."
        )
        send_telegram_message(msg)
    except Exception as e:
        logger.warning(f"Erreur notification Telegram invitation: {e}")


def _send_invitation_accepted_notification(user_name: str):
    """Envoie une notification Telegram quand une invitation est acceptée."""
    try:
        from core.notifier import send_telegram_message
        msg = (
            "✅ *Invitation Facebook App Acceptée*\n\n"
            f"👤 Utilisateur: *{user_name}*\n"
            f"📅 Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"L'utilisateur peut maintenant connecter ses pages Facebook."
        )
        send_telegram_message(msg)
    except Exception as e:
        logger.warning(f"Erreur notification Telegram acceptance: {e}")


# Initialize database on startup
@app.on_event("startup")
async def startup_webhook():
    from core.db import init_db
    logger.info("Initializing database for webhook server...")
    init_db()
    _init_users_table()
    check_all_tokens()

DATA_DIR = Config.DATA_DIR
DATA_DIR.mkdir(exist_ok=True)
POST_RESOURCES_FILE = DATA_DIR / "post_resources.json"
SENT_LOG_FILE = DATA_DIR / "sent_log.json"

VERIFY_TOKEN = Config.FB_VERIFY_TOKEN or "default_verify_token"
PAGE_ACCESS_TOKEN = Config.FB_PAGE_ACCESS_TOKEN
PAGE_ID = Config.FB_PAGE_ID
GRAPH_API_URL = "https://graph.facebook.com/v18.0"

def load_post_resources():
    if POST_RESOURCES_FILE.exists():
        try:
            return json.loads(POST_RESOURCES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erreur lecture post_resources.json: {e}")
            return {}
    return {}

def save_post_resources(data):
    POST_RESOURCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_sent_log():
    if SENT_LOG_FILE.exists():
        try:
            return json.loads(SENT_LOG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erreur lecture sent_log.json: {e}")
            return {}
    return {}


def poll_comments():
    """Mode polling: vérifie les commentaires toutes les X minutes (configurable)."""
    import time
    
    print("[POLLING] Démarrage du mode polling...")
    logger.info("Mode polling démarré")
    
    while True:
        try:
            settings = load_settings()
            polling_interval = settings.get("polling_interval_seconds", 600)
            trigger_enabled = settings.get("trigger_dm_enabled", True)

            print(f"[POLLING] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — Vérification des commentaires...")
            
            if not PAGE_ACCESS_TOKEN or not PAGE_ID:
                logger.error("PAGE_ACCESS_TOKEN ou PAGE_ID manquant")
                time.sleep(polling_interval)
                continue
            
            posts_url = f"{GRAPH_API_URL}/{PAGE_ID}/published_posts"
            params = {
                "access_token": PAGE_ACCESS_TOKEN,
                "fields": "id,message",
                "limit": 20
            }
            
            response = requests.get(posts_url, params=params, timeout=30)
            if response.status_code != 200:
                logger.error(f"Erreur récupération posts: {response.text}")
                time.sleep(polling_interval)
                continue
            
            posts = response.json().get("data", [])
            resources = load_post_resources()
            sent_log = load_sent_log()
            
            for post in posts:
                post_id = post.get("id")
                resource_data = resources.get(post_id, {})
                trigger_word = resource_data.get("trigger_word", "").upper()
                
                comments_url = f"{GRAPH_API_URL}/{post_id}/comments"
                comments_params = {
                    "access_token": PAGE_ACCESS_TOKEN,
                    "fields": "from,message,id",
                    "limit": 50
                }
                
                comments_resp = requests.get(comments_url, params=comments_params, timeout=30)
                if comments_resp.status_code != 200:
                    continue
                
                comments = comments_resp.json().get("data", [])
                
                for comment in comments:
                    comment_id = comment.get("id")
                    message = comment.get("message", "")
                    from_data = comment.get("from", {})
                    user_id = from_data.get("id", "") if isinstance(from_data, dict) else ""
                    user_name = from_data.get("name", "quelqu'un") if isinstance(from_data, dict) else "quelqu'un"
                    
                    if trigger_enabled:
                        handled_as_cta = check_and_send_resource(comment_id, message, post_id, user_id=user_id)
                        if handled_as_cta:
                            continue
                    
                    check_and_send_ai_response(comment_id, message, post_id, user_name)
            
            print(f"[POLLING] Terminé, prochaine vérification dans {polling_interval}s...")
            
        except Exception as e:
            logger.error(f"Erreur polling: {e}")
            print(f"[ERROR] Erreur polling: {e}")
        
        time.sleep(polling_interval)


def get_all_facebook_accounts():
    """Récupère tous les comptes Facebook actifs depuis la DB."""
    try:
        from core.db import SessionLocal, Account
        db = SessionLocal()
        accounts = db.query(Account).filter(
            Account.platform == "facebook",
            Account.status == "active"
        ).all()
        result = []
        for acc in accounts:
            creds = acc.credentials or {}
            if creds.get("page_id") and creds.get("access_token"):
                result.append({
                    "id": acc.id,
                    "name": acc.name,
                    "page_id": creds["page_id"],
                    "access_token": creds["access_token"]
                })
        db.close()
        return result
    except Exception as e:
        logger.error(f"Erreur récupération comptes: {e}")
        return []


DEFAULT_DM_MESSAGE = "Thanks for your comment! Follow my page so you don't miss any free tips. See you soon!"

SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_SETTINGS = {
    "trigger_dm_enabled": True,
    "auto_dm_enabled": False,
    "ai_responses_enabled": False,
    "polling_interval_seconds": 600,
    "dm_polling_interval_seconds": 300,
    "default_llm_model": "llama-3.3-70b-versatile",
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = DEFAULT_SETTINGS.copy()
            merged.update(data)
            return merged
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Erreur lecture settings.json: {e}")
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")

def get_setting(key, default=None):
    return load_settings().get(key, default)


def send_auto_dm(comment_id, page_id, access_token):
    """Envoie une réponse automatique au commentaire (DM ou reply public)."""
    try:
        url = f"{GRAPH_API_URL}/{comment_id}/private_replies"
        params = {"access_token": access_token, "message": DEFAULT_DM_MESSAGE}

        resp = requests.post(url, params=params, timeout=30)

        if resp.status_code == 200:
            logger.info(f"DM automatique envoyé pour commentaire {comment_id}")
            return True

        logger.warning(f"Private reply échoué, tentative réponse publique: {resp.text[:100]}")

        reply_url = f"{GRAPH_API_URL}/{comment_id}/comments"
        reply_params = {"access_token": access_token, "message": DEFAULT_DM_MESSAGE}

        reply_resp = requests.post(reply_url, params=reply_params, timeout=30)

        if reply_resp.status_code == 200:
            logger.info(f"Réponse publique envoyée pour commentaire {comment_id}")
            return True
        else:
            logger.error(f"Erreur réponse publique: {reply_resp.text}")
            return False

    except Exception as e:
        logger.error(f"Exception send_auto_dm: {e}")
        return False


def check_and_send_auto_dm(comment_id, message, post_id, page_id, access_token):
    """Vérifie et envoie le DM automatique (sans trigger)."""
    if not get_setting("auto_dm_enabled", False):
        return False

    sent_log = load_sent_log()
    log_key = f"auto_dm_{comment_id}"

    if sent_log.get(log_key):
        return False

    success = send_auto_dm(comment_id, page_id, access_token)

    if success:
        sent_log[log_key] = {
            "post_id": post_id,
            "comment_id": comment_id,
            "timestamp": datetime.now().isoformat()
        }
        save_sent_log(sent_log)

    return success


def poll_all_accounts_dm():
    """Mode polling: vérifie les commentaires pour TOUS les comptes et envoie DM automatique."""
    import time
    
    print("[POLLING ALL] Démarrage du polling multi-comptes pour DM automatique...")
    logger.info("Mode polling multi-comptes démarré")
    
    while True:
        try:
            settings = load_settings()
            polling_interval = settings.get("dm_polling_interval_seconds", 300)
            trigger_enabled = settings.get("trigger_dm_enabled", True)
            auto_dm_enabled = settings.get("auto_dm_enabled", False)

            print(f"[POLLING ALL] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — Vérification...")

            accounts = get_all_facebook_accounts()
            print(f"[POLLING ALL] {len(accounts)} compte(s) Facebook trouvé(s)")

            resources = load_post_resources()

            for account in accounts:
                page_id = account["page_id"]
                access_token = account["access_token"]
                account_name = account["name"]

                print(f"[POLLING ALL] Vérification compte: {account_name} ({page_id})")

                posts_url = f"{GRAPH_API_URL}/{page_id}/published_posts"
                params = {
                    "access_token": access_token,
                    "fields": "id,message",
                    "limit": 10
                }

                response = requests.get(posts_url, params=params, timeout=30)
                if response.status_code != 200:
                    print(f"[POLLING ALL] Erreur posts pour {account_name}: {response.text[:100]}")
                    continue

                posts = response.json().get("data", [])

                for post in posts:
                    post_id = post.get("id")

                    comments_url = f"{GRAPH_API_URL}/{post_id}/comments"
                    comments_params = {
                        "access_token": access_token,
                        "fields": "from,message,id",
                        "limit": 50
                    }

                    comments_resp = requests.get(comments_url, params=comments_params, timeout=30)
                    if comments_resp.status_code != 200:
                        continue

                    comments = comments_resp.json().get("data", [])

                    for comment in comments:
                        comment_id = comment.get("id")
                        message = comment.get("message", "")
                        user_from = comment.get("from", {})
                        user_id = user_from.get("id") if isinstance(user_from, dict) else None

                        if user_id == page_id:
                            continue

                        if trigger_enabled:
                            handled_as_cta = check_and_send_resource(comment_id, message, post_id, access_token=access_token, user_id=user_id or "")
                            if handled_as_cta:
                                continue

                        if auto_dm_enabled:
                            check_and_send_auto_dm(comment_id, message, post_id, page_id, access_token)

            print(f"[POLLING ALL] Terminé, prochaine vérification dans {polling_interval}s...")

        except Exception as e:
            logger.error(f"Erreur polling all: {e}")
            print(f"[ERROR] Erreur polling all: {e}")

        time.sleep(polling_interval)


def save_sent_log(data):
    SENT_LOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_account_by_page_id(page_id):
    """Retrouve un compte Facebook actif par son page_id (DB leads_station.db)."""
    if not page_id:
        return None
    page_id = str(page_id)
    try:
        import sqlite3
        db_path = PLATFORM_DB.get("facebook")
        if not db_path or not Path(db_path).exists():
            return None
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT * FROM accounts WHERE status='active'")
            for row in cursor:
                creds = row["credentials"]
                if isinstance(creds, str):
                    try:
                        creds = json.loads(creds)
                    except Exception:
                        creds = {}
                if str(creds.get("page_id", "")) == page_id:
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "page_id": page_id,
                        "access_token": creds.get("access_token", ""),
                        "credentials": creds,
                    }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"resolve_account_by_page_id error: {e}")
    return None


def _resolve_account_by_post_id(post_id):
    """Trouve le compte qui a publié ce post en cherchant facebook_post_id dans tous les dossiers content."""
    if not post_id:
        return None
    try:
        post_id_short = post_id.split("_")[-1] if "_" in post_id else post_id
    except Exception:
        post_id_short = post_id

    for account in _iter_all_content_accounts():
        found = _find_post_folder(account["content_root"], post_id, post_id_short)
        if found:
            return {**account, "folder": found["folder"], "meta": found["meta"]}
    return None

def reply_to_comment(comment_id, message, access_token=None, page_id=None):
    """Répond à un commentaire via Graph API (token du compte propriétaire du post si possible)."""
    token = access_token or PAGE_ACCESS_TOKEN
    if not token:
        logger.error("PAGE_ACCESS_TOKEN non configuré")
        return False

    url = f"{GRAPH_API_URL}/{comment_id}/comments"
    params = {"access_token": token, "message": message}

    try:
        response = requests.post(url, params=params, timeout=30)
        if response.status_code == 200:
            logger.info(f"Réponse au commentaire {comment_id} (page {page_id or PAGE_ID}): {message[:50]}...")
            return True
        else:
            logger.error(f"Erreur reply: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception reply: {e}")
        return False

def send_private_reply(comment_id, message, access_token=None):
    """Envoie une réponse privée via /{comment_id}/private_replies."""
    token = access_token or PAGE_ACCESS_TOKEN
    if not token:
        logger.error("PAGE_ACCESS_TOKEN non configuré")
        return False

    chunk_size = 1800
    chunks = [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]

    url = f"{GRAPH_API_URL}/{comment_id}/private_replies"
    params = {
        "access_token": token,
        "message": chunks[0]
    }

    try:
        response = requests.post(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.error(f"Erreur private_reply: {response.text}")
            return False
        logger.info(f"Private reply envoyé sur commentaire {comment_id}")
    except Exception as e:
        logger.error(f"Exception private_reply: {e}")
        return False

    if len(chunks) > 1:
        time.sleep(1)
        for chunk in chunks[1:]:
            params["message"] = chunk
            try:
                requests.post(url, params=params, timeout=30)
                time.sleep(1)
            except:
                pass

    return True

def get_trigger_for_post(post_id):
    """Récupère le trigger word et la ressource pour un post."""
    resources = load_post_resources()
    result = resources.get(post_id, None)
    if result:
        logger.debug(f"Trigger trouvé pour post {post_id}: word='{result.get('trigger_word')}'")
    return result

def clean_for_messenger(text):
    """Convertit Markdown pour Messenger (supporte *gras* mais pas **)."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)  # **gras** → *gras*
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)  # # Titre → Titre
    text = re.sub(r'__(.+?)__', r'*\1*', text)       # __gras__ → *gras*
    return text

def send_messenger_resource(user_id, resource_content, access_token=None):
    """Envoie la ressource via Messenger (conversation initiée par l'utilisateur)."""
    token = access_token or PAGE_ACCESS_TOKEN
    if not token:
        return False
    url = f"{GRAPH_API_URL}/{PAGE_ID}/messages"
    chunk_size = 1800
    try:
        clean_content = clean_for_messenger(resource_content)
        chunks = [clean_content[i:i+chunk_size] for i in range(0, len(clean_content), chunk_size)]
        r = requests.post(f"{url}?access_token={token}", json={
            "recipient": {"id": user_id},
            "message": {"text": f"Here is your resource:\n\n{chunks[0]}"},
            "messaging_type": "RESPONSE"
        }, timeout=30)
        if r.status_code != 200:
            logger.error(f"Erreur Messenger: {r.text}")
            return False
        for chunk in chunks[1:]:
            time.sleep(1)
            requests.post(f"{url}?access_token={token}", json={
                "recipient": {"id": user_id},
                "message": {"text": chunk},
                "messaging_type": "RESPONSE"
            }, timeout=30)
        logger.info(f"Ressource envoyée via Messenger à {user_id}")
        return True
    except Exception as e:
        logger.error(f"Exception Messenger: {e}")
        return False

OLLAMA_URL = Config.OLLAMA_URL


def _get_ai_responses_enabled() -> bool:
    """Lit l'état du toggle IA depuis settings.json puis ai_responses.json (fallback)."""
    settings_val = get_setting("ai_responses_enabled")
    if settings_val is not None:
        return bool(settings_val)

    f = DATA_DIR / "ai_responses.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("enabled", False)
        except Exception:
            pass
    return Config.AI_RESPONSES_ENABLED


def _is_ai_response_enabled_for_post(post_id):
    """Détermine si les réponses IA sont actives pour un post donné.
    Priorité : flag explicite du post (meta.json ai_responses) > réglage global.
    """
    post_info = get_post_info(post_id)
    if post_info:
        per_post = post_info.get("ai_responses")
        if per_post is not None:
            return bool(per_post)
    return _get_ai_responses_enabled()


def generate_ai_response(comment_text, post_id, user_name="quelqu'un"):
    """Génère une réponse IA personnalisée au commentaire.

    Utilise le routeur LLM unifié (core.llm_router.call_llm) : Ollama en
    priorité, fallback en cascade sur le modèle par défaut puis Groq.
    """
    post_info = get_post_info(post_id)
    
    if not post_info:
        return None
    
    persona = post_info.get("persona", "expert_ia")
    post_text = post_info.get("post_text", "")[:1000]
    
    system_prompts = {
        "historien": "Tu es un historien français expert, passionné par les anecdotes historiques méconnues. Tu responds de manière culturelle, instructive mais accessible.",
        "expert_ia": "Tu es un expert français en IA et innovation digitale. Tu responses de manière professionnelle, pédagogique et accessible.",
        "cta": "Tu es un marketeur français expert en croissance. Tu responses de manière persuasive, avec des conseils concrets.",
        "kebane_humain": "Tu es Kebane, un entrepreneur français authentique et transparent. Tu partages ton expérience personnelle avec sincérité.",
        "kebane_intellectuel": "Tu es Kebane, un stratège français qui aime analyser les situations en profondeur. Tu responses de manière posée et analytique.",
        "kebane_stratege": "Tu es Kebane, un consultant français en stratégie digitale. Tu responses de manière concise et orientée résultats.",
    }
    
    system = system_prompts.get(persona, system_prompts["expert_ia"])
    system += f"\n\nTu réponds à un commentaire sur un post Facebook de ta propre page. Le commentaire est de {user_name}. "
    system += "Sois naturel, concis (1-3 phrases), et engageant. "
    system += "Si le commentaire pose une question, réponds directement. "
    system += "Si c'est un compliment, remercie avec sincérité. "
    system += "Si c'est une critique constructive, acknowledge et propose des pistes. "
    system += "Ne sois pas trop formel - le ton est celui des réseaux sociaux."
    
    user_prompt = f"Post original:\n{post_text}\n\nCommentaire auquel répondre:\n{comment_text}\n\nTa réponse (en français, 1-3 phrases max):"
    
    try:
        from core.llm_router import call_llm
        # Groq en priorité (fiable, clé configurée). Fallback cascade auto :
        # modèle par défaut puis Ollama local, si Groq échoue.
        text, metadata = call_llm(
            system,
            user_prompt,
            model="groq/llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=300,
            fallback=True,
        )
        if text and str(text).strip():
            logger.info(f"[AI] Réponse générée via {metadata.get('provider')}/{metadata.get('model')}")
            return str(text).strip()
    except Exception as e:
        logger.error(f"Erreur génération IA: {e}")
    return None

def _iter_all_content_accounts():
    """Itère sur tous les comptes ayant un dossier content (DB + fichiers), y compris le dossier racine."""
    seen_ids = set()

    # 1. Dossier racine (Config.CONTENT_DIR)
    root = Path(Config.CONTENT_DIR)
    if root.exists():
        yield {"id": None, "name": "root", "page_id": PAGE_ID, "access_token": PAGE_ACCESS_TOKEN, "content_root": root}

    # 2. Comptes depuis les bases de données plateforme
    for platform, db_path in PLATFORM_DB.items():
        if not db_path or not Path(db_path).exists():
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute("SELECT * FROM accounts WHERE status='active'")
                for row in cursor:
                    creds = row["credentials"]
                    if isinstance(creds, str):
                        try:
                            creds = json.loads(creds)
                        except Exception:
                            creds = {}
                    account_id = row["id"]
                    if account_id in seen_ids:
                        continue
                    seen_ids.add(account_id)
                    base = PLATFORM_BASE.get(platform)
                    content_root = (base / "accounts" / str(account_id) / "content") if base else None
                    if content_root and content_root.exists():
                        yield {
                            "id": account_id,
                            "name": row["name"],
                            "page_id": creds.get("page_id", ""),
                            "access_token": creds.get("access_token", ""),
                            "platform": platform,
                            "content_root": content_root,
                        }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"iter accounts error {platform}: {e}")


def _find_post_folder(content_root, post_id, post_id_short):
    """Cherche dans content_root le dossier dont meta.json facebook_post_id matche post_id ou post_id_short."""
    try:
        for folder in content_root.iterdir():
            if not folder.is_dir():
                continue
            meta_file = folder / "meta.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            fb_id = str(meta.get("facebook_post_id", ""))
            if fb_id == post_id or fb_id == post_id_short:
                return {"folder": folder, "meta": meta}
    except Exception as e:
        logger.warning(f"find_post_folder error: {e}")
    return None


def get_post_info(post_id):
    """Récupère les infos du post (persona, contenu, compte) depuis les fichiers générés.

    Cherche dans tous les comptes (racine + machines/*/accounts/*/content), pas seulement Config.CONTENT_DIR.
    """
    try:
        post_id_short = post_id.split("_")[-1] if "_" in post_id else post_id
    except Exception:
        post_id_short = post_id

    for account in _iter_all_content_accounts():
        found = _find_post_folder(account["content_root"], post_id, post_id_short)
        if not found:
            continue
        folder = found["folder"]
        meta = found["meta"]
        post_text = ""
        post_file = folder / "facebook_post.txt"
        if not post_file.exists():
            post_file = folder / "post.txt"
        if not post_file.exists():
            post_file = folder / "content.txt"
        if post_file.exists():
            post_text = post_file.read_text(encoding="utf-8")
        return {
            "persona": meta.get("persona", "expert_ia"),
            "post_text": post_text,
            "folder": folder.name,
            "ai_responses": meta.get("ai_responses"),
            "account_id": account.get("id"),
            "account_name": account.get("name"),
            "page_id": account.get("page_id"),
            "access_token": account.get("access_token"),
            "platform": account.get("platform", "facebook"),
        }
    return None

def check_and_send_ai_response(comment_id, message, post_id, user_name="quelqu'un"):
    """Envoie une réponse IA personnalisée au commentaire.
    Mode: répond automatiquement SI et seulement SI aucune réponse manuelle n'a été postée.
    Appelé uniquement si le commentaire n'a PAS déclenché le flow CTA.
    """
    if not _is_ai_response_enabled_for_post(post_id):
        return False
    
    # Vérifier si une réponse manuelle a déjà été postée par la page
    if has_manual_reply(post_id, comment_id):
        logger.info(f"Commentaire {comment_id} a déjà une réponse manuelle, pas d'auto-reply")
        return False
    
    sent_log = load_sent_log()
    sent_key = f"ai_response_{post_id}_{comment_id}"
    if sent_key in sent_log.get("ai_sent", []):
        return False
    
    response_text = generate_ai_response(message, post_id, user_name)
    if response_text and len(response_text) > 0:
        # Utiliser le token du compte qui a publié le post (fallback global)
        post_info = get_post_info(post_id)
        account_token = (post_info or {}).get("access_token") or PAGE_ACCESS_TOKEN
        account_page_id = (post_info or {}).get("page_id") or PAGE_ID
        success = reply_to_comment(comment_id, response_text, access_token=account_token, page_id=account_page_id)
        if success:
            if "ai_sent" not in sent_log:
                sent_log["ai_sent"] = []
            sent_log["ai_sent"].append(sent_key)
            save_sent_log(sent_log)
            logger.info(f"Réponse IA envoyée au commentaire {comment_id} (page {account_page_id}): {response_text[:50]}...")
            return True
    return False


def has_manual_reply(post_id, comment_id, access_token=None):
    """Vérifie si une réponse manuelle a déjà été postée sur ce commentaire."""
    try:
        post_info = get_post_info(post_id)
        token = access_token or (post_info or {}).get("access_token") or PAGE_ACCESS_TOKEN
        page_id = (post_info or {}).get("page_id") or PAGE_ID
        url = f"{GRAPH_API_URL}/{comment_id}/comments"
        params = {"access_token": token, "fields": "from,id", "limit": 10}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for reply in data:
                from_info = reply.get("from", {})
                if from_info.get("id") == page_id:
                    return True
    except Exception as e:
        logger.warning(f"Erreur vérification réponse manuelle: {e}")
    return False

def check_and_send_resource(comment_id, message, post_id, access_token=None, user_id=""):
    """Vérifie si le message contient un trigger et applique la stratégie hybride.

    Ordre d'exécution :
    1. Tenter le DM en premier (private_reply).
    2. Poster le commentaire public SELON le résultat réel.

    Retourne True si le flow CTA a été déclenché (trigger trouvé), False sinon.
    """
    if not get_setting("trigger_dm_enabled", True):
        return False

    message_upper = message.upper().strip()

    resource_data = get_trigger_for_post(post_id)
    if not resource_data:
        logger.debug(f"Pas de trigger configuré pour le post {post_id}")
        return False

    trigger_word = resource_data.get("trigger_word", "").upper()
    if not trigger_word or trigger_word not in message_upper:
        logger.debug(f"Trigger '{trigger_word}' non trouvé dans le commentaire: '{message_upper[:50]}'")
        return False

    # ── Vérifier le délai d'expiration ────────────────────────────────────────
    expires_at_str = resource_data.get("expires_at", "")
    if expires_at_str:
        try:
            expires_dt = datetime.fromisoformat(expires_at_str)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_dt:
                # Délai expiré — on répond à chaque personne (pas de dédup global)
                sent_log = load_sent_log()
                expired_key = f"expired_{post_id}_{comment_id}"
                if expired_key not in sent_log.get("expired", []):
                    expired_msg = (
                        "The sharing period has ended 😔\n"
                        "Follow the page so you don't miss upcoming resources! "
                        "If you really want it, send me a direct message 🙏"
                    )
                    reply_to_comment(comment_id, expired_msg, access_token=access_token)
                    if "expired" not in sent_log:
                        sent_log["expired"] = []
                    sent_log["expired"].append(expired_key)
                    save_sent_log(sent_log)
                    logger.info(f"CTA expiré — réponse envoyée au commentaire {comment_id}")
                return True  # trigger trouvé → bloquer l'IA dans tous les cas
        except Exception as e:
            logger.warning(f"Impossible de parser expires_at '{expires_at_str}': {e}")

    # Anti-doublons (envoi normal)
    sent_log = load_sent_log()
    sent_key = f"comment_{post_id}_{comment_id}"
    if sent_key in sent_log.get("sent", []):
        logger.info(f"Déjà traité: {sent_key}")
        return True  # déjà géré → bloquer l'IA quand même


    # ── Construire le corps du DM ─────────────────────────────────────────────
    resource_url   = resource_data.get("resource_url", "")
    resource_text  = resource_data.get("resource_content", "")
    resource_title = resource_data.get("title", "ta ressource")

    if resource_url:
        dm_message = (
            f"🎁 {resource_title}\n\n"
            f"👉 {resource_url}\n\n"
            f"Let me know if you have any questions! 🚀"
        )
    elif resource_text:
        # Fallback legacy : texte brut (anciens posts)
        dm_message = clean_for_messenger(resource_text)
    else:
        logger.warning(f"Post {post_id} a un trigger mais aucune ressource configurée")
        return True  # trigger trouvé mais rien à envoyer → bloquer l'IA

    # ── Étape 1 : tenter le DM EN PREMIER ────────────────────────────────────
    dm_success = False
    if user_id:
        dm_success = send_messenger_resource(user_id, dm_message, access_token=access_token)
    if not dm_success:
        dm_success = send_private_reply(comment_id, dm_message, access_token=access_token)

    # ── Étape 2 : commentaire public selon résultat réel ──────────────────────
    if dm_success:
        public_msg = (
            "It's sent! 🎁 Check your private messages "
            "(look in the \"Message requests\" folder if we're not connected yet)."
        )
    else:
        public_msg = (
            "I can't send you a private message right now — "
            "your privacy settings block messages from people you don't follow. "
            "Send me a quick message first and I'll send you the link right away! 📥"
        )

    reply_to_comment(comment_id, public_msg, access_token=access_token)

    # ── Logger comme traité ───────────────────────────────────────────────────
    if "sent" not in sent_log:
        sent_log["sent"] = []
    sent_log["sent"].append(sent_key)
    save_sent_log(sent_log)
    logger.info(f"CTA traité — dm_success={dm_success} — commentaire {comment_id}")
    return True


def check_and_send_dm_resource(user_id, message):
    """Envoie la ressource CTA uniquement si le MP contient un trigger word.
    Utilise 'dm_sent' (séparé de 'sent' utilisé par les commentaires) pour éviter
    les race conditions quand webhook reçoit comment + DM en parallèle.
    """
    message_upper = message.upper().strip()
    resources = load_post_resources()
    sent_log = load_sent_log()
    dm_sent = sent_log.get("dm_sent", [])

    def _already_sent_dm(uid, post_id):
        """Checks if the resource has already been sent via DM to this user."""
        key_new = f"dm_{uid}_{post_id}"
        return key_new in dm_sent

    # Chercher un match par trigger_word — sinon ne rien faire
    matched_post_id = None
    matched_data = None
    for post_id, resource_data in resources.items():
        if post_id.startswith("_"):
            continue
        trigger_word = resource_data.get("trigger_word", "").upper()
        if trigger_word and trigger_word in message_upper:
            if _already_sent_dm(user_id, post_id):
                logger.info(f"[DM] Déjà envoyé à {user_id} pour post {post_id} (trigger={trigger_word})")
                return False
            matched_post_id = post_id
            matched_data = resource_data
            logger.info(f"[DM] Trigger '{trigger_word}' trouvé dans message de {user_id}")
            break

    # Pas de trigger → pas de réponse automatique
    if not matched_data:
        logger.debug(f"[DM] Pas de trigger dans message de {user_id}: '{message_upper[:30]}'")
        return False

    trigger_word = matched_data.get("trigger_word", "general")

    # Construire le message
    resource_url   = matched_data.get("resource_url", "")
    resource_text  = matched_data.get("resource_content", "")
    resource_title = matched_data.get("title", "ta ressource")

    if resource_url:
        dm_body = (
            f"🎁 {resource_title}\n\n"
            f"👉 {resource_url}\n\n"
            f"Enjoy! Let me know if you have any questions 🚀"
        )
    elif resource_text:
        dm_body = clean_for_messenger(resource_text)
    else:
        logger.warning(f"[DM] Ressource {matched_post_id} sans contenu")
        return False

    # Optimistic lock : sauvegarder la clé AVANT l'envoi pour bloquer les appels suivants
    dedup_key = f"dm_{user_id}_{matched_post_id}"
    if "dm_sent" not in sent_log:
        sent_log["dm_sent"] = []
    sent_log["dm_sent"].append(dedup_key)
    try:
        save_sent_log(sent_log)
        logger.info(f"[DM] Clé dedup '{dedup_key}' sauvegardée (avant envoi)")
    except Exception as e:
        logger.error(f"[DM] Erreur sauvegarde sent_log: {e}")
        return False

    # Envoyer
    ok = send_messenger_resource(user_id, dm_body)
    if ok:
        logger.info(f"[DM] Ressource envoyée à {user_id} (post={matched_post_id}, trigger={trigger_word})")
        return True
    else:
        # Échec : retirer la clé pour permettre un retry ultérieur
        sent_log["dm_sent"].remove(dedup_key)
        try:
            save_sent_log(sent_log)
            logger.info(f"[DM] Clé dedup '{dedup_key}' retirée (envoi échoué, retry possible)")
        except Exception as e:
            logger.error(f"[DM] Erreur retrait clé dedup: {e}")
        return False

def _mask_secret(value, keep=4):
    """Masque un secret (token/clé) en ne gardant que les derniers caractères."""
    if not value:
        return "<vide>"
    value = str(value)
    if len(value) <= keep:
        return "***"
    return value[:keep] + "..." + value[-4:]

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Vérification du webhook Meta."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    logger.info(f"Webhook verification: mode={mode}, token_present={bool(token)}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook vérifié avec succès")
        return PlainTextResponse(content=challenge, status_code=200)
    else:
        logger.warning(
            f"Webhook verification failed: token={_mask_secret(token)}, expected={_mask_secret(VERIFY_TOKEN)}"
        )
        raise HTTPException(status_code=403, detail="Token invalide")

@app.post("/webhook")
async def receive_webhook(request: Request):
    """Reçoit les événements Facebook."""
    try:
        raw_body = await request.body()
        content_type = request.headers.get("content-type", "")
        logger.info(f"RAW webhook ({content_type}): {raw_body[:200]} (length={len(raw_body)})")

        # Parse JSON (Meta peut envoyer application/json ou form data)
        try:
            body = json.loads(raw_body)
        except Exception as parse_err:
            logger.error(f"JSON parse error: {parse_err} — raw: {raw_body[:200]}")
            return {"status": "ok"}

        logger.info(f"Webhook reçu: {json.dumps(body)[:200]}...")

        if "entry" not in body:
            return {"status": "ok"}
        
        for entry in body.get("entry", []):
            if "messaging" in entry:
                for message_event in entry["messaging"]:
                    user_id = message_event.get("sender", {}).get("id")
                    message_text = message_event.get("message", {}).get("text", "")
                    page_id = message_event.get("recipient", {}).get("id")

                    if user_id and message_text and user_id != PAGE_ID:
                        logger.info(f"DM de {user_id}: {message_text[:50]}")
                        check_and_send_dm_resource(user_id, message_text)
            
            if "changes" in entry:
                for change in entry["changes"]:
                    field = change.get("field")
                    if field == "feed":
                        value = change.get("value", {})
                        comment_id = value.get("comment_id")
                        message = value.get("message", "")
                        post_id = value.get("post_id")
                        user_id = value.get("from", {}).get("id") if isinstance(value.get("from"), dict) else value.get("from")

                        # Résoudre la page du post (multi-comptes) pour éviter l'auto-réponse à soi-même
                        post_info = get_post_info(post_id) if post_id else None
                        owner_page_id = (post_info or {}).get("page_id") or PAGE_ID

                        if comment_id and message and post_id and user_id and str(user_id) != str(owner_page_id):
                            logger.info(f"Commentaire sur {post_id} (page {owner_page_id}): {message[:50]}")
                            user_name = value.get("from", {}).get("name", "quelqu'un") if isinstance(value.get("from"), dict) else "quelqu'un"
                            # Logique d'exclusion mutuelle CTA vs IA :
                            # Si le post est CTA et que le commentaire contient le trigger
                            # → CTA flow (invite DM). Sinon → IA flow.
                            handled_as_cta = check_and_send_resource(comment_id, message, post_id, access_token=(post_info or {}).get("access_token") or PAGE_ACCESS_TOKEN, user_id=user_id or "")
                            if not handled_as_cta:
                                check_and_send_ai_response(comment_id, message, post_id, user_name)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Erreur webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/privacy")
async def privacy_policy():
    """Page de politique de confidentialité."""
    html = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Politique de confidentialité</title>
<style>body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6}</style>
</head>
<body>
<h1>Politique de confidentialité</h1>
<p><strong>Dernière mise à jour : 28 mars 2026</strong></p>
<h2>1. Collecte des données</h2>
<p>Cette application collecte uniquement les données nécessaires à son fonctionnement : identifiants de commentaires Facebook et messages publics sur la page Jean-Marc Emmanuel DANSI.</p>
<h2>2. Utilisation des données</h2>
<p>Les données collectées sont utilisées exclusivement pour répondre automatiquement aux commentaires publics contenant un mot-clé spécifique, en envoyant une ressource gratuite en message privé.</p>
<h2>3. Stockage</h2>
<p>Les données sont stockées localement sur un serveur privé. Aucune donnée n'est partagée avec des tiers.</p>
<h2>4. Droits</h2>
<p>Conformément au RGPD, vous pouvez demander la suppression de vos données en contactant : jeanmarc@mjautomation.shop</p>
<h2>5. Contact</h2>
<p>Jean-Marc Emmanuel DANSI — mjautomation.shop</p>
</body></html>"""
    return HTMLResponse(content=html)

@app.get("/health")
async def health():
    """Vérification santé du serveur."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "page_id": PAGE_ID
    }

@app.get("/resources")
async def list_resources():
    """Liste les ressources disponibles."""
    return load_post_resources()


# ============================================================
# SETTINGS — Paramètres de la pipeline
# ============================================================
@app.get("/api/settings", tags=["settings"])
async def api_get_settings():
    """Retourne tous les paramètres de la pipeline."""
    return {"success": True, "settings": load_settings()}


@app.post("/api/settings", tags=["settings"])
async def api_update_settings(request: Request):
    """Met à jour les paramètres de la pipeline (merge partiel)."""
    body = await request.json()
    settings = load_settings()

    allowed_keys = set(DEFAULT_SETTINGS.keys())
    updated = {}
    for key, value in body.items():
        if key in allowed_keys:
            settings[key] = value
            updated[key] = value

    save_settings(settings)
    logger.info(f"Settings mis à jour: {updated}")
    return {"success": True, "settings": settings}


@app.get("/api/settings/{key}", tags=["settings"])
async def api_get_setting(key: str):
    """Retourne un paramètre spécifique."""
    settings = load_settings()
    if key not in DEFAULT_SETTINGS:
        return {"success": False, "error": f"Paramètre inconnu: {key}"}
    return {"success": True, "key": key, "value": settings.get(key)}


@app.put("/api/settings/{key}", tags=["settings"])
async def api_set_setting(key: str, request: Request):
    """Met à jour un paramètre spécifique."""
    if key not in DEFAULT_SETTINGS:
        return {"success": False, "error": f"Paramètre inconnu: {key}"}

    body = await request.json()
    value = body.get("value")

    settings = load_settings()
    settings[key] = value
    save_settings(settings)

    if any(part in key.lower() for part in ("token", "secret", "password", "key", "credential")):
        logger.info(f"Setting '{key}' mis à jour: {_mask_secret(value)}")
    else:
        logger.info(f"Setting '{key}' mis à jour: {value}")
    return {"success": True, "key": key, "value": value}

# ============================================================
# PROXY /prospection/* → localhost:5001
# ============================================================
PROSPECTION_BACKEND = "http://localhost:5001"
PROSPECTION_PREFIX = "/prospection"

def _rewrite_html(html: bytes) -> bytes:
    """Réécrit les URLs absolues en URLs préfixées pour le proxy."""
    try:
        text = html.decode("utf-8")
    except UnicodeDecodeError:
        return html
    import re
    replacements = [
        # Attributs HTML
        (r'(href\s*=\s*["\'])/((?!http|#|data:|mailto:|prospection)[^"\'>\s]*)', rf'\1{PROSPECTION_PREFIX}/\2'),
        (r'(src\s*=\s*["\'])/((?!http|#|data:|prospection)[^"\'>\s]*)', rf'\1{PROSPECTION_PREFIX}/\2'),
        (r"(url\(['\"]?)/((?!http|#|data:|prospection)[^'\")>\s]*)", rf"\1{PROSPECTION_PREFIX}/\2"),
        # JavaScript inline — toute chaîne ou template literal commençant par /api/ ou /static/
        (r"(['\"`])/api/", rf"\1{PROSPECTION_PREFIX}/api/"),
        (r"(['\"`])/static/", rf"\1{PROSPECTION_PREFIX}/static/"),
        # Patterns JS spécifiques (fallback)
        (r"(fetch\(['\"]?)/((?!http|#|data:|prospection)[^'\")>\s]*)", rf"\1{PROSPECTION_PREFIX}/\2"),
        (r"(axios\.(get|post|put|delete)\(['\"]?)/((?!http|#|data:|prospection)[^'\")>\s]*)", rf"\1{PROSPECTION_PREFIX}/\3"),
        (r"(\.open\(['\"]GET['\"],\s*['\"]?)/((?!http|#|data:|prospection)[^\"\'>\s]*)", rf"\1{PROSPECTION_PREFIX}/\2"),
        (r'(window\.location\.href\s*=\s*["\']?)/((?!http|#|data:|prospection)[^"\'>\s]*)', rf'\1{PROSPECTION_PREFIX}/\2'),
        (r"(onclick\s*=\s*['\"].*?)/(api/)", rf"\1{PROSPECTION_PREFIX}/\2"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text.encode("utf-8")

def _rewrite_js(js: bytes) -> bytes:
    """Réécrit les appels fetch/axios avec chemins absolus dans les fichiers JS."""
    try:
        text = js.decode("utf-8")
    except UnicodeDecodeError:
        return js
    import re
    replacements = [
        # Toute chaîne/template literal commençant par /api/ ou /static/
        (r"(['\"`])/api/", rf"\1{PROSPECTION_PREFIX}/api/"),
        (r"(['\"`])/static/", rf"\1{PROSPECTION_PREFIX}/static/"),
        # Patterns spécifiques fetch/axios (fallback si pas déjà réécrit)
        (r"(fetch\(['\"]?)/((?!http|#|data:|prospection)[^'\")>\s]*)", rf"\1{PROSPECTION_PREFIX}/\2"),
        (r"(axios\.(get|post|put|delete)\(['\"]?)/((?!http|#|data:|prospection)[^'\")>\s]*)", rf"\1{PROSPECTION_PREFIX}/\3"),
        (r"(\.open\(['\"](?:GET|POST|PUT|DELETE)['\"],\s*['\"]?)/((?!http|#|data:|prospection)[^\"\'>\s]*)", rf"\1{PROSPECTION_PREFIX}/\2"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text.encode("utf-8")

@app.get("/prospection")
async def prospection_root_redirect():
    """Redirige /prospection vers /prospection/ pour que les chemins relatifs fonctionnent."""
    return RedirectResponse(url="/prospection/", status_code=302)

@app.api_route("/prospection/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_prospection(path: str, request: Request):
    """Reverse proxy vers le dashboard Prospection sur localhost:5001"""
    target = f"{PROSPECTION_BACKEND}/{path}"
    hop_by_hop = {"host", "connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer", "proxy-authorization"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop}
    headers["host"] = "localhost:5001"

    try:
        body = await request.body()
        resp = await shared_httpx_client.request(
            method=request.method,
            url=target,
            headers=headers,
            content=body if body else None,
            follow_redirects=False,
        )

        # Réécrit les URLs selon le type de contenu
        content_type = resp.headers.get("content-type", "")
        response_content = resp.content
        rewritten = False
        if "text/html" in content_type:
            response_content = _rewrite_html(resp.content)
            rewritten = True
        elif "javascript" in content_type:
            response_content = _rewrite_js(resp.content)
            rewritten = True

        # Supprime content-length si le contenu a été réécrit (taille peut avoir changé)
        exclude = hop_by_hop | {"content-encoding"}
        if rewritten:
            exclude.add("content-length")
        resp_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in exclude
        }

        return PlainTextResponse(
            content=response_content,
            status_code=resp.status_code,
            headers=resp_headers,
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Prospection backend unreachable (localhost:5001)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def check_all_tokens():
    """Vérifie la validité de tous les tokens Facebook et tente un refresh si nécessaire.
    
    Appelé au démarrage du serveur. Envoie une notification Telegram si un token
    est expiré ou sur le point d'expirer (< 7 jours).
    """
    try:
        from core.db import SessionLocal, Account
        from core.notifier import send_telegram_message

        db = SessionLocal()
        accounts = db.query(Account).filter(
            Account.platform == "facebook",
            Account.status == "active"
        ).all()

        for acc in accounts:
            creds = acc.credentials or {}
            page_id = creds.get("page_id", "")
            access_token = creds.get("access_token", "")
            user_token = creds.get("user_token", "")

            if not page_id or not access_token:
                continue

            # Vérifier la validité du page token
            try:
                r = requests.get(
                    f"https://graph.facebook.com/v18.0/{page_id}",
                    params={"access_token": access_token, "fields": "id,name"},
                    timeout=10,
                )
                token_valid = r.status_code == 200 and "id" in r.json()
            except Exception:
                token_valid = False

            if not token_valid and user_token:
                # Tenter un refresh automatique
                logger.warning(f"Token expiré pour {acc.name} (page {page_id}), tentative de refresh...")
                infinite_token = _exchange_for_infinite_page_token(page_id, user_token)
                if infinite_token:
                    creds["access_token"] = infinite_token
                    creds["expires_at"] = None
                    acc.credentials = creds
                    db.commit()
                    logger.info(f"Token régénéré automatiquement pour {acc.name}")
                    send_telegram_message(
                        f"✅ Token Facebook régénéré automatiquement\n"
                        f"Page: {acc.name} ({page_id})"
                    )
                    continue

            if not token_valid:
                logger.error(f"Token expiré et non rafraîchissable pour {acc.name} (page {page_id})")
                send_telegram_message(
                    f"⚠️ Token Facebook EXPIRÉ\n"
                    f"Page: {acc.name} ({page_id})\n"
                    f"Action requise: ré-authentifiez via /api/facebook/auth"
                )

        db.close()
    except Exception as e:
        logger.error(f"Erreur vérification tokens: {e}")


def repair_content_metadata():
    """Répare automatiquement les meta.json incohérents.
    Corrige les dossiers où le reel existe mais has_reel/reel_generated sont à false.
    """
    import logging
    logger = get_node_logger("repair")
    
    content_dir = Config.CONTENT_DIR
    if not content_dir.exists():
        return
    
    fixed_count = 0
    checked_count = 0
    
    for folder in content_dir.iterdir():
        if not folder.is_dir():
            continue
        
        checked_count += 1
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except:
            continue
        
        reel_dir = folder / "reel"
        reel_file = reel_dir / "reel.mp4"
        
        has_reel_in_folder = reel_file.exists()
        has_reel_in_meta = meta.get("has_reel", False)
        reel_generated = meta.get("reel_generated", False)
        
        needs_fix = has_reel_in_folder and not (has_reel_in_meta or reel_generated)
        
        if needs_fix:
            meta["has_reel"] = True
            meta["reel_generated"] = True
            meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed_count += 1
            logger.info(f"Réparé: {folder.name} -> has_reel=True, reel_generated=True")
    
    logger.info(f"Repair terminé: {fixed_count}/{checked_count} dossiers corrigés")
    print(f"[REPAIR] Meta.json répare: {fixed_count}/{checked_count} dossiers")


if __name__ == "__main__":
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description="Facebook Webhook Server")
    parser.add_argument("--poll", action="store_true", help="Mode polling (compte par défaut)")
    parser.add_argument("--poll-all", action="store_true", help="Mode polling multi-comptes (trigger + auto-dm)")
    parser.add_argument("--no-repair", action="store_true", help="Désactiver la réparation auto au démarrage")
    
    args = parser.parse_args()
    
    if not args.no_repair:
        repair_content_metadata()
    
    if args.poll:
        poll_comments()
    elif args.poll_all:
        poll_all_accounts_dm()
    else:
        print(f"[INFO] Serveur webhook sur http://localhost:8000")
        print(f"[INFO] Page ID: {PAGE_ID}")
        print(f"[INFO] Vérifier token configuré: {bool(VERIFY_TOKEN and VERIFY_TOKEN != 'default_token')}")
        uvicorn.run(app, host="0.0.0.0", port=8000)
