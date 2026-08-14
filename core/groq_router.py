# groq_router.py — Rotation automatique des clés Groq en cas de quota 429
# Usage: from core.groq_router import call_groq
#
# Principe :
#   1. Charge GROQ_API_KEY, GROQ_API_KEY_2 ... GROQ_API_KEY_9 depuis .env
#   2. À chaque appel, essaie les clés disponibles dans l'ordre
#   3. Si 429 → marque la clé en cooldown, passe à la clé suivante
#   4. Si toutes les clés sont épuisées → retourne None
#   5. Pas de fallback entre modèles (même modèle, rotation de clés)

import os
import time
import logging
import re
import json
from pathlib import Path
from typing import Optional


def _clean_reasoning(text: str) -> str:
    """Supprime les balises de reasoning (Qwen3, DeepSeek, etc.)."""
    if not text:
        return text
    # Supprime tout ce qui ressemble à du reasoning en balises
    patterns = [
        r'<think[^>]*>.*?</think[^>]*>',
        r'<thinking[^>]*>.*?</thinking[^>]*>',
        r'<reasoning[^>]*>.*?</reasoning[^>]*>',
        r'<think>.*?',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.DOTALL | re.IGNORECASE)
    # Supprime les balises d'ouverture seules
    text = re.sub(r'<(think|reasoning)[^>]*>', '', text, flags=re.IGNORECASE)
    # Supprime les balises XML restantes
    text = re.sub(r'</?[\w-]+>', '', text)
    # Nettoie les espaces multiples et lignes vides
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r' +', ' ', text).strip()
    return text

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Modèles utilisés (pas de fallback - si quota, on change de clé)
MODEL_POSTS = "llama-3.3-70b-versatile"                      # Rédaction posts (Llama 3.3 70B)
MODEL_IMAGE = "llama-3.1-8b-instant"                          # Prompt images (plus rapide)


def _post_with_retry_transient(key: str, model: str, messages: list,
                               temperature: float, max_tokens: int,
                               attempts: int = 3, base_delay: float = 1.0,
                               max_delay: float = 15.0) -> Optional[str]:
    """Retry/backoff sur une même clé Groq pour les erreurs transitoires
    (429, 5xx, timeout réseau) avant de déléguer à la rotation de clés."""
    import requests
    import time as _time
    retry_statuses = {429, 500, 502, 503, 504}
    delay = base_delay
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=45,
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                return _clean_reasoning(content)
            if r.status_code not in retry_statuses:
                return None
            last_status = r.status_code
            last_text = r.text[:200]
        except Exception as e:
            last_status = "network"
            last_text = str(e)
        if attempt < attempts:
            logging.warning(f"[GROQ_ROUTER] retry {attempt}/{attempts - 1} (clé {key[:14]}..., {last_status}), backoff {delay:.1f}s")
            _time.sleep(delay)
            delay = min(delay * 2, max_delay)
        else:
            if last_status is None:
                raise
            logging.error(f"[GROQ_ROUTER] HTTP {last_status} ({model}, clé {key[:14]}...): {last_text}")
            return None
    return None


def call_groq_posts(prompt: str, **kwargs) -> Optional[str]:
    """Appel Groq pour rédaction posts."""
    return call_groq(prompt, model=MODEL_POSTS, **kwargs)


def call_groq_image(prompt: str, **kwargs) -> Optional[str]:
    """Appel Groq pour génération prompt images."""
    return call_groq(prompt, model=MODEL_IMAGE, **kwargs)

# ─── Persistance fichier JSON (partagé entre tous les processus) ───
_COOLDOWN_FILE: Path = None

def _get_cooldown_path() -> Path:
    global _COOLDOWN_FILE
    if _COOLDOWN_FILE is None:
        p = Path(__file__).resolve()
        # Trouve Content_Machine dans le path
        try:
            idx = p.parts.index("Content_Machine")
            root = Path(*p.parts[:idx+1])
        except ValueError:
            root = p.parent.parent  # fallback
        _COOLDOWN_FILE = root / "data" / "groq_cooldowns.json"
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _COOLDOWN_FILE

def _load_cooldowns() -> dict[str, float]:
    """Lit les cooldowns depuis le fichier JSON partagé."""
    path = _get_cooldown_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in raw.items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}

def _save_cooldowns(data: dict[str, float]):
    """Écrit les cooldowns dans le fichier JSON partagé."""
    _get_cooldown_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

# Chargé depuis le fichier au démarrage du module
_exhausted_until: dict[str, float] = _load_cooldowns()


def _load_keys() -> list[str]:
    """Charge toutes les clés Groq disponibles depuis les variables d'environnement."""
    keys = []
    # Clé principale
    if key := os.getenv("GROQ_API_KEY", "").strip():
        keys.append(key)
    # Clés supplémentaires : GROQ_API_KEY_2 → GROQ_API_KEY_9
    for i in range(2, 10):
        if key := os.getenv(f"GROQ_API_KEY_{i}", "").strip():
            keys.append(key)
    return keys


def _is_available(key: str) -> bool:
    """True si la clé n'est pas en cooldown quota."""
    return time.time() >= _exhausted_until.get(key, 0)


def _mark_exhausted(key: str, cooldown_s: int = 3600):
    """Marque une clé comme épuisée (cooldown par défaut 1h)."""
    _exhausted_until[key] = time.time() + cooldown_s
    _save_cooldowns(_exhausted_until)
    logging.warning(
        f"[GROQ_ROUTER] Clé {key[:14]}... quota atteint — "
        f"réactivation dans {cooldown_s // 60} min"
    )


def call_groq(
    prompt: str,
    model: str = None,
    temperature: float = 0.85,
    max_tokens: int = 2048,
    system: str = None,
) -> Optional[str]:
    """
    Appel Groq avec rotation automatique de clés (pas de fallback modèle).

    Paramètres
    ----------
    prompt       : message utilisateur
    model        : modèle à utiliser (defaut: MODEL_POSTS)
    temperature  : créativité (0-1)
    max_tokens   : limite tokens réponse
    system       : message système optionnel

    Retourne le contenu texte ou None si toutes les clés épuisées.
    """
    import requests

    # Modèle par défaut si non spécifié
    if model is None:
        model = MODEL_POSTS

    keys = _load_keys()
    if not keys:
        logging.error("[GROQ_ROUTER] Aucune GROQ_API_KEY configurée dans .env")
        return None

    # Recharge les cooldowns depuis le fichier (partagé entre processus)
    _exhausted_until.update(_load_cooldowns())

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Clés disponibles (non en cooldown)
    available = [k for k in keys if _is_available(k)]
    if not available:
        # Forcer quand même un essai (le cooldown a peut-être expiré)
        available = keys

    for key in available:
        try:
            r = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=45,
            )

            if r.status_code == 200:
                nb_keys = len(keys)
                key_idx = keys.index(key) + 1
                logging.info(
                    f"[GROQ_ROUTER] OK — modèle={model}, "
                    f"clé {key_idx}/{nb_keys} ({key[:14]}...)"
                )
                content = r.json()["choices"][0]["message"]["content"]
                return _clean_reasoning(content)

            # Retry/backoff sur erreurs transitoires (429 et 5xx) pour la même clé
            if r.status_code in (429, 500, 502, 503, 504):
                retried = _post_with_retry_transient(
                    key=key, model=model, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                )
                if retried is not None:
                    return retried
            # sinon on redescend dans la rotation de clés ci-dessous
            if r.status_code == 429:
                # Extraire le cooldown suggéré si disponible
                try:
                    msg = r.json()["error"]["message"]
                    # Cherche "Please try again in Xm Ys"
                    import re
                    m_match = re.search(r"(\d+)m", msg)
                    s_match = re.search(r"(\d+(?:\.\d+)?)s", msg)
                    
                    cooldown = 0
                    if m_match: cooldown += int(m_match.group(1)) * 60
                    if s_match: cooldown += float(s_match.group(1))
                    
                    if cooldown == 0:
                        cooldown = 60  # Défaut 1 min
                    else:
                        cooldown += 5  # Petite marge de sécu
                except Exception:
                    cooldown = 60
                _mark_exhausted(key, cooldown_s=int(cooldown))
                continue  # Essayer la clé suivante

            else:
                logging.error(
                    f"[GROQ_ROUTER] HTTP {r.status_code} ({model}, "
                    f"clé {key[:14]}...): {r.text[:200]}"
                )
                _mark_exhausted(key, cooldown_s=3600)
                continue

        except Exception as e:
                logging.error(
                    f"[GROQ_ROUTER] Exception ({model}, clé {key[:14]}...): {e}"
                )
                _mark_exhausted(key, cooldown_s=3600)
                continue

    logging.error(f"[GROQ_ROUTER] Toutes les clés Groq ont échoué (modèle: {model}).")
    return None


def get_available_keys_status() -> list[dict]:
    """Retourne l'état de toutes les clés (pour le monitoring)."""
    keys = _load_keys()
    now = time.time()
    # Recharge depuis le fichier pour voir les cooldowns des autres processus
    cooldowns = _load_cooldowns()
    result = []
    for i, key in enumerate(keys):
        until = cooldowns.get(key, 0)
        remaining = max(0, int(until - now))
        result.append({
            "index": i + 1,
            "key_preview": key[:14] + "...",
            "available": remaining == 0,
            "cooldown_remaining_s": remaining,
        })
    return result
