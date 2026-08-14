# gemini_router.py — Routeur Google AI Studio (Gemini) avec rate limiter
# Limite : 8 requêtes/minute (marge de sécurité sous le quota gratuit de 10 RPM)
#
# Usage:
#   from core.gemini_router import call_gemini
#   result = call_gemini(prompt, system="...", model="gemini-2.0-flash")

import os
import re
import time
import logging
import threading
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────
GEMINI_MODELS = [
    "models/gemini-2.5-flash",      # Meilleure qualité disponible
    "models/gemini-2.0-flash",      # Fallback rapide
    "models/gemini-2.0-flash-lite", # Fallback léger
]

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# ─── Rate Limiter (token bucket sliding window) ──────────────────────────────
_RATE_LOCK = threading.Lock()
_REQUEST_TIMESTAMPS: deque = deque()
MAX_RPM = 8           # requêtes max par minute (sous le quota 10-15 RPM gratuit)
WINDOW_SECONDS = 60

# ─── Cooldown par modèle (évite de re-tenter un modèle bloqué par 429) ───────
_MODEL_COOLDOWN: dict[str, float] = {}
_MODEL_LOCK = threading.Lock()


def _wait_for_rate_limit():
    """
    Bloque si nécessaire pour ne pas dépasser MAX_RPM.
    Implémente une fenêtre glissante de 60 secondes.
    """
    while True:
        with _RATE_LOCK:
            now = time.time()
            while _REQUEST_TIMESTAMPS and now - _REQUEST_TIMESTAMPS[0] > WINDOW_SECONDS:
                _REQUEST_TIMESTAMPS.popleft()

            if len(_REQUEST_TIMESTAMPS) < MAX_RPM:
                _REQUEST_TIMESTAMPS.append(now)
                return

            oldest = _REQUEST_TIMESTAMPS[0]
            wait_s = WINDOW_SECONDS - (now - oldest) + 0.5

        logger.info(f"[GEMINI_ROUTER] Rate limit atteint ({MAX_RPM} RPM). Pause {wait_s:.1f}s...")
        time.sleep(wait_s)


def _mark_model_cooldown(model: str, seconds: int = 65):
    """Marque un modèle en cooldown après un 429."""
    with _MODEL_LOCK:
        _MODEL_COOLDOWN[model] = time.time() + seconds
    logger.warning(f"[GEMINI_ROUTER] Modèle {model} en cooldown {seconds}s")


def _model_available(model: str) -> bool:
    """True si le modèle n'est pas en cooldown."""
    with _MODEL_LOCK:
        return time.time() >= _MODEL_COOLDOWN.get(model, 0)


def _load_key() -> Optional[str]:
    """Charge la clé Google AI Studio depuis .env / variables d'environnement."""
    return (
        os.getenv("GOOGLE_AI_STUDIO_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or None
    )


def call_gemini(
    prompt: str,
    system: Optional[str] = None,
    model: str = "models/gemini-2.5-flash",
    temperature: float = 0.85,
    max_tokens: int = 4096,
) -> Optional[str]:
    """
    Appel à l'API Google AI Studio avec rate limiting automatique.

    Paramètres
    ----------
    prompt       : message utilisateur
    system       : instruction système (optionnel)
    model        : modèle préféré — accepte avec ou sans le préfixe 'models/'
    temperature  : créativité (0-1)
    max_tokens   : limite tokens réponse

    Retourne le texte généré, ou None si tout échoue.
    """
    import requests

    api_key = _load_key()
    if not api_key:
        logger.error("[GEMINI_ROUTER] Aucune GOOGLE_AI_STUDIO_KEY ni GEMINI_API_KEY dans .env")
        return None

    # Normaliser : ajouter 'models/' si absent
    def _norm(m: str) -> str:
        return m if m.startswith("models/") else f"models/{m}"

    preferred = _norm(model)
    models_to_try = [preferred] + [m for m in GEMINI_MODELS if m != preferred]

    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    for current_model in models_to_try:
        if not _model_available(current_model):
            logger.info(f"[GEMINI_ROUTER] {current_model} en cooldown — on passe.")
            continue

        _wait_for_rate_limit()

        url = f"{GEMINI_API_BASE}/{current_model}:generateContent?key={api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}

        # Retry/backoff sur erreurs transitoires (429, 5xx, timeout réseau)
        delay = 2.0
        last_resp = None
        for attempt in range(1, 4):
            try:
                resp = requests.post(url, json=payload, timeout=90)

                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            logger.info(f"[GEMINI_ROUTER] OK — modèle={current_model}")
                            return text

                if resp.status_code in (429, 500, 502, 503, 504):
                    last_resp = resp
                    if attempt < 3:
                        logger.warning(f"[GEMINI_ROUTER] {resp.status_code} ({current_model}) — retry {attempt}/2, backoff {delay:.1f}s")
                        time.sleep(delay)
                        delay = min(delay * 2, 16.0)
                        continue
                # Hors statuts transitoires, on sort du retry et on gère le statut
                break
            except Exception as e:
                logger.error(f"[GEMINI_ROUTER] Exception ({current_model}): {e}")
                if attempt < 3:
                    time.sleep(delay)
                    delay = min(delay * 2, 16.0)
                    continue
                break

        # --- Gestion du statut final hors 200 ---
        if last_resp is None:
            logger.error("[GEMINI_ROUTER] Échec réseau après retries — modèle suivant")
            continue
        try:
            if last_resp.status_code == 429:
                # Extraire le délai suggéré dans la réponse si disponible
                try:
                    err_msg = last_resp.json().get("error", {}).get("message", "")
                    sec_match = re.search(r"(\d+)\s*second", err_msg)
                    cooldown = int(sec_match.group(1)) + 5 if sec_match else 65
                except Exception:
                    cooldown = 65
                _mark_model_cooldown(current_model, cooldown)
                continue

            elif last_resp.status_code == 503:
                logger.warning(f"[GEMINI_ROUTER] 503 surchargé ({current_model}) — pause 20s puis modèle suivant")
                time.sleep(20)
                continue

            elif last_resp.status_code == 400:
                logger.error(f"[GEMINI_ROUTER] 400 Bad Request ({current_model}): {last_resp.text[:300]}")
                continue

            else:
                logger.error(f"[GEMINI_ROUTER] HTTP {last_resp.status_code} ({current_model}): {last_resp.text[:200]}")
                continue
        except Exception as e:
            logger.error(f"[GEMINI_ROUTER] Exception ({current_model}): {e}")
            continue

    logger.error("[GEMINI_ROUTER] Tous les modèles Gemini ont échoué.")
    return None


def get_rate_status() -> dict:
    """Retourne l'état courant du rate limiter (pour monitoring)."""
    with _RATE_LOCK:
        now = time.time()
        recent = [t for t in _REQUEST_TIMESTAMPS if now - t <= WINDOW_SECONDS]
        cooldowns = {m: round(v - now, 1) for m, v in _MODEL_COOLDOWN.items() if v > now}
        return {
            "requests_last_60s": len(recent),
            "max_rpm": MAX_RPM,
            "slots_available": MAX_RPM - len(recent),
            "models_in_cooldown": cooldowns,
        }
