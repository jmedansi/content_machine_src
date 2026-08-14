# llm_router.py — Routeur LLM multi-provider unifié pour la rédaction de contenus
#
# Principe :
#   1. Un catalogue de modèles est pré-configuré (MODEL_CATALOG), groupé par fournisseur.
#      Les IDs suivent la convention `{provider}/{model}` (ex: "openai/gpt-4o").
#   2. L'utilisateur choisit un modèle par compte et renseigne sa clé API / URL de base
#      (stockées dans accounts.settings, lues par le copywriter/scheduler).
#   3. call_llm() route vers le bon adaptateur :
#        - API OpenAI-compatible (/chat/completions) : OpenAI, Gemini, DeepSeek,
#          OpenRouter, Mistral, Kimi (Moonshot)
#        - Anthropic : API Messages (/v1/messages)
#        - Ollama (local) : /api/chat, sans clé
#        - Groq : réutilise core.groq_router (rotation de clés existante)
#   4. Rétro-compatibilité : les IDs nus "llama-*" -> groq, "kimi-*" -> kimi.
#   5. Fallback en cascade : provider demandé -> modèle par défaut global -> Groq.

import os
import re
import json
import logging
from pathlib import Path

# ─── Presets fournisseurs ────────────────────────────────────────────────
PROVIDERS = {
    "openai":      {"label": "OpenAI",         "api_type": "openai",    "base_url": "https://api.openai.com/v1",                         "env_key": "OPENAI_API_KEY",       "default_max_tokens": 3000},
    "anthropic":   {"label": "Anthropic Claude","api_type": "anthropic","base_url": "https://api.anthropic.com/v1",                     "env_key": "ANTHROPIC_API_KEY",    "default_max_tokens": 4096},
    "gemini":      {"label": "Google Gemini",   "api_type": "openai",    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "env_key": "GEMINI_API_KEY", "default_max_tokens": 3000},
    "deepseek":    {"label": "DeepSeek",        "api_type": "openai",    "base_url": "https://api.deepseek.com/v1",                      "env_key": "DEEPSEEK_API_KEY",     "default_max_tokens": 3000},
    "openrouter":  {"label": "OpenRouter",      "api_type": "openai",    "base_url": "https://openrouter.ai/api/v1",                     "env_key": "OPENROUTER_API_KEY",   "default_max_tokens": 3000},
    "mistral":     {"label": "Mistral",         "api_type": "openai",    "base_url": "https://api.mistral.ai/v1",                        "env_key": "MISTRAL_API_KEY",      "default_max_tokens": 3000},
    "groq":        {"label": "Groq",            "api_type": "groq",      "base_url": "https://api.groq.com/openai/v1/chat/completions", "env_key": "GROQ_API_KEY",         "default_max_tokens": 3000},
    "kimi":        {"label": "Kimi (Moonshot)", "api_type": "openai",    "base_url": "https://api.moonshot.ai/v1",                      "env_key": "KIMI_API_KEY",         "default_max_tokens": 1450},
    "ollama":      {"label": "Ollama (local)",  "api_type": "ollama",    "base_url": "http://localhost:11434",                          "env_key": "",                     "default_max_tokens": 3000},
}

# ─── Catalogue des modèles (pré-configurés) ─────────────────────────────
MODEL_CATALOG = [
    # OpenAI
    {"id": "openai/gpt-4o",                  "label": "GPT-4o",                 "provider": "openai"},
    {"id": "openai/gpt-4o-mini",             "label": "GPT-4o mini",            "provider": "openai"},
    {"id": "openai/gpt-4.1",                 "label": "GPT-4.1",                "provider": "openai"},
    {"id": "openai/o3-mini",                 "label": "o3-mini",                "provider": "openai"},
    # Anthropic Claude
    {"id": "anthropic/claude-sonnet-4-5",    "label": "Claude Sonnet 4.5",      "provider": "anthropic"},
    {"id": "anthropic/claude-opus-4-5",      "label": "Claude Opus 4.5",        "provider": "anthropic"},
    {"id": "anthropic/claude-3-7-sonnet",    "label": "Claude 3.7 Sonnet",      "provider": "anthropic"},
    # Google Gemini
    {"id": "gemini/gemini-2.5-pro",          "label": "Gemini 2.5 Pro",         "provider": "gemini"},
    {"id": "gemini/gemini-2.5-flash",        "label": "Gemini 2.5 Flash",       "provider": "gemini"},
    # DeepSeek
    {"id": "deepseek/deepseek-chat",         "label": "DeepSeek Chat",          "provider": "deepseek"},
    {"id": "deepseek/deepseek-reasoner",     "label": "DeepSeek Reasoner",      "provider": "deepseek"},
    # OpenRouter
    {"id": "openrouter/auto",                "label": "OpenRouter Auto",        "provider": "openrouter"},
    {"id": "openrouter/openai/gpt-4o",       "label": "GPT-4o (OpenRouter)",    "provider": "openrouter"},
    {"id": "openrouter/anthropic/claude-sonnet-4-5", "label": "Claude (OpenRouter)", "provider": "openrouter"},
    # Mistral
    {"id": "mistral/mistral-large-latest",   "label": "Mistral Large",          "provider": "mistral"},
    {"id": "mistral/mistral-small-latest",   "label": "Mistral Small",          "provider": "mistral"},
    # Groq (IDs historiques enregistrés en DB)
    {"id": "groq/llama-3.3-70b-versatile",   "label": "Llama 3.3 70B",          "provider": "groq"},
    {"id": "groq/llama-3.1-8b-instant",      "label": "Llama 3.1 8B Instant",   "provider": "groq"},
    {"id": "groq/llama-3.1-70b-versatile",   "label": "Llama 3.1 70B",          "provider": "groq"},
    {"id": "groq/llama-2-70b-chat",          "label": "Llama 2 70B Chat",       "provider": "groq"},
    # Kimi
    {"id": "kimi/kimi-k3",                   "label": "Kimi K3 (recommandé)",   "provider": "kimi"},
    {"id": "kimi/kimi-k2.6",                 "label": "Kimi K2.6",              "provider": "kimi"},
    {"id": "kimi/kimi-k2.5",                 "label": "Kimi K2.5 (déprécié)",   "provider": "kimi"},
    # Ollama (local)
    {"id": "ollama/llama3.1",                "label": "Llama 3.1 (local)",      "provider": "ollama"},
    {"id": "ollama/llama3",                  "label": "Llama 3 (local)",        "provider": "ollama"},
]

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def _clean_reasoning(text: str) -> str:
    """Supprime les balises de reasoning (Qwen3, DeepSeek, Claude think, etc.)."""
    if not text:
        return text
    patterns = [
        r'<think[^>]*>.*?</think[^>]*>',
        r'<thinking[^>]*>.*?</thinking[^>]*>',
        r'<reasoning[^>]*>.*?</reasoning[^>]*>',
        r'<think>.*?',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<(think|reasoning)[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?[\w-]+>', '', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    text = re.sub(r' +', ' ', text).strip()
    return text


def parse_model(model_id: str):
    """Parse un ID de modèle en (provider, model). Rétro-compatible :
    "llama-*" -> groq, "kimi-*" -> kimi, tout ID nu -> groq."""
    if not model_id:
        return "groq", DEFAULT_GROQ_MODEL
    model_id = str(model_id).strip()
    if "/" in model_id:
        provider, model = model_id.split("/", 1)
        provider = provider.strip().lower()
        model = model.strip()
        return (provider, model) if model else (provider, DEFAULT_GROQ_MODEL)
    if model_id.startswith("kimi-"):
        return "kimi", model_id
    return "groq", model_id


def normalize_model_id(model_id: str) -> str:
    """Normalise un ID (nul → préfixé) pour les comparaisons."""
    if not model_id:
        return f"groq/{DEFAULT_GROQ_MODEL}"
    model_id = str(model_id).strip()
    if "/" in model_id:
        return model_id
    if model_id.startswith("kimi-"):
        return f"kimi/{model_id}"
    return f"groq/{model_id}"


def get_default_model() -> str:
    """Modèle par défaut global : settings.json (dashboard) -> .env -> Groq."""
    try:
        from core.config import Config
    except Exception:
        return DEFAULT_GROQ_MODEL
    try:
        p = Path(Config.BASE_DIR) / "data" / "settings.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("default_llm_model"):
                return data["default_llm_model"]
    except Exception:
        pass
    return getattr(Config, "DEFAULT_LLM_MODEL", None) or DEFAULT_GROQ_MODEL


def get_account_llm_config(platform: str, account_id) -> dict:
    """Retourne la config LLM du compte depuis accounts.settings :
    {model, api_key, base_url}. Les valeurs absentes restent None (le routeur
    retombe alors sur le modèle par défaut et les clés .env)."""
    config = {"model": None, "api_key": None, "base_url": None}
    if not account_id:
        return config
    try:
        from core.paths import PLATFORM_DB
        db_path = Path(PLATFORM_DB.get(platform, ""))
    except Exception:
        db_path = Path(f"d:/Content_Machine/machines/{platform}_machine/data/leads_station.db")
    if not db_path.exists():
        return config
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT settings FROM accounts WHERE id=?", (account_id,))
        row = cursor.fetchone()
        if row and row["settings"]:
            try:
                settings = json.loads(row["settings"])
                if settings.get("llm_model"):
                    config["model"] = settings.get("llm_model")
                if settings.get("llm_api_key"):
                    config["api_key"] = settings.get("llm_api_key")
                if settings.get("llm_base_url"):
                    config["base_url"] = settings.get("llm_base_url")
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return config


def _resolve_credentials(provider: str, api_key: str, base_url: str):
    """Retourne (key, url). Priorité : valeurs fournies -> .env -> preset."""
    info = PROVIDERS.get(provider, {})
    if not api_key:
        env_key = info.get("env_key")
        if env_key:
            api_key = os.getenv(env_key, "").strip()
    if not base_url:
        base_url = info.get("base_url", "")
    return api_key, base_url


# ─── Retry / backoff ─────────────────────────────────────────────────────
def _post_with_retry(url, *, headers=None, json=None, timeout=10,
                     attempts=4, base_delay=1.0, max_delay=15.0):
    """POST HTTP avec retry + backoff exponentiel sur erreurs transitoires.

    Retente sur : timeout, erreur de connexion et status 429/500/502/503/504.
    Retourne la dernière réponse (ou None si échec réseau après tous les essais).
    """
    import time
    import requests
    retry_statuses = {429, 500, 502, 503, 504}
    delay = base_delay
    last = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=json, timeout=timeout)
            if resp.status_code not in retry_statuses:
                return resp
            last = resp
            msg = f"HTTP {resp.status_code}"
        except requests.exceptions.HTTPError as e:
            last = None
            msg = f"http: {e}"
        except requests.exceptions.Timeout as e:
            last = None
            msg = f"timeout: {e}"
        except requests.exceptions.ConnectionError as e:
            last = None
            msg = f"connection error: {e}"
        except requests.exceptions.RequestException as e:
            last = None
            msg = str(e)
        if attempt < attempts:
            logging.warning(f"[LLM_ROUTER] retry {attempt}/{attempts - 1} ({msg}), backoff {delay:.1f}s")
            time.sleep(delay)
            delay = min(delay * 2, max_delay)
        else:
            return last
    return None


# ─── Adaptateurs ─────────────────────────────────────────────────────────
def _call_openai_compatible(provider: str, model: str, system: str, prompt: str,
                            api_key: str, base_url: str, temperature: float,
                            max_tokens: int, timeout: int = 90):
    key, url = _resolve_credentials(provider, api_key, base_url)
    if not key:
        logging.error(f"[LLM_ROUTER] {provider}: clé API manquante (renseignez-la ou mettez {PROVIDERS.get(provider, {}).get('env_key', '...')} dans .env)")
        return None
    url = url.rstrip("/")
    endpoint = f"{url}/chat/completions"
    if "chat/completions" in url:
        endpoint = url
    import requests
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/incidenx/content_machine"
        headers["X-Title"] = "Content Machine"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        r = _post_with_retry(
            endpoint,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if r is None:
            logging.error(f"[LLM_ROUTER] {provider} ({model}): échec réseau après retries")
            return None
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            return _clean_reasoning(content)
        logging.error(f"[LLM_ROUTER] {provider} ({model}) HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        logging.error(f"[LLM_ROUTER] Exception {provider} ({model}): {e}")
    return None


def _call_anthropic(model: str, system: str, prompt: str, api_key: str,
                    base_url: str, temperature: float, max_tokens: int, timeout: int = 120):
    key, url = _resolve_credentials("anthropic", api_key, base_url)
    if not key:
        logging.error("[LLM_ROUTER] anthropic: clé API manquante")
        return None
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = url if url.endswith("/messages") else f"{url}/v1"
    endpoint = f"{url}/messages" if not url.endswith("/messages") else url
    import requests
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    try:
        r = _post_with_retry(
            endpoint,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if r is None:
            logging.error("[LLM_ROUTER] anthropic: échec réseau après retries")
            return None
        if r.status_code == 200:
            data = r.json()
            content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return _clean_reasoning(content)
        logging.error(f"[LLM_ROUTER] anthropic ({model}) HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        logging.error(f"[LLM_ROUTER] Exception anthropic ({model}): {e}")
    return None


def _call_ollama(model: str, system: str, prompt: str, base_url: str,
                 temperature: float, max_tokens: int, timeout: int = 120):
    _, url = _resolve_credentials("ollama", "", base_url)
    url = url.rstrip("/")
    import requests
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        r = _post_with_retry(
            f"{url}/api/chat",
            headers={},
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        if r is None:
            logging.error(f"[LLM_ROUTER] ollama ({model}): échec réseau après retries")
            return None
        if r.status_code == 200:
            content = r.json().get("message", {}).get("content", "")
            return _clean_reasoning(content)
        logging.error(f"[LLM_ROUTER] ollama ({model}) HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        logging.error(f"[LLM_ROUTER] Exception ollama ({model}): {e}")
    return None


def _call_groq(model: str, system: str, prompt: str, temperature: float, max_tokens: int):
    try:
        from core.groq_router import call_groq
    except Exception as e:
        logging.error(f"[LLM_ROUTER] Import groq_router échoué: {e}")
        return None
    return call_groq(
        prompt=prompt,
        system=system,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_provider(provider: str, model: str, system: str, prompt: str,
                   api_key: str = None, base_url: str = None,
                   temperature: float = 0.8, max_tokens: int = None):
    info = PROVIDERS.get(provider, {})
    if not info:
        logging.error(f"[LLM_ROUTER] Provider inconnu: {provider}")
        return None
    if max_tokens is None:
        max_tokens = info.get("default_max_tokens", 3000)
    api_type = info.get("api_type", "openai")
    if api_type == "groq":
        return _call_groq(model, system, prompt, temperature, max_tokens)
    if api_type == "anthropic":
        return _call_anthropic(model, system, prompt, api_key, base_url, temperature, max_tokens)
    if api_type == "ollama":
        return _call_ollama(model, system, prompt, base_url, temperature, max_tokens)
    return _call_openai_compatible(provider, model, system, prompt, api_key, base_url, temperature, max_tokens)


# ─── Fonction principale ─────────────────────────────────────────────────
def call_llm(system_prompt: str, user_prompt: str, model: str = None,
             api_key: str = None, base_url: str = None,
             temperature: float = 0.8, max_tokens: int = None,
             fallback: bool = True) -> tuple:
    """Appelle le modèle demandé avec fallback en cascade.

    Retourne (text, metadata). metadata contient provider/model + providers_tried.
    """
    logger = logging.getLogger("llm_router")
    metadata = {"stage": "call_llm", "providers_tried": []}

    provider, resolved_model = parse_model(model)
    logger.info(f"[LLM_ROUTER] Génération via {provider} ({resolved_model}).")
    result = _call_provider(provider, resolved_model, system_prompt, user_prompt,
                            api_key=api_key, base_url=base_url,
                            temperature=temperature, max_tokens=max_tokens)
    if result:
        metadata["provider"] = provider
        metadata["model"] = resolved_model
        return result, metadata
    metadata["providers_tried"].append({"provider": provider, "model": resolved_model, "error": "no response"})

    if not fallback:
        return None, metadata

    # Fallback 1 : modèle par défaut global
    default_model = get_default_model()
    if normalize_model_id(default_model) != normalize_model_id(model):
        p2, m2 = parse_model(default_model)
        logger.warning(f"[LLM_ROUTER] {provider} a échoué, fallback sur modèle par défaut ({p2}/{m2}).")
        result = _call_provider(p2, m2, system_prompt, user_prompt,
                                api_key=api_key, base_url=base_url,
                                temperature=temperature, max_tokens=max_tokens)
        if result:
            metadata["provider"] = p2
            metadata["model"] = m2
            metadata["fallback_from"] = f"{provider}/{resolved_model}"
            return result, metadata
        metadata["providers_tried"].append({"provider": p2, "model": m2, "error": "no response"})

    # Fallback 2 : Groq par défaut (résilience maximale)
    if provider != "groq" or resolved_model != DEFAULT_GROQ_MODEL:
        logger.warning("[LLM_ROUTER] Fallback final sur Groq (llama-3.3-70b-versatile).")
        result = _call_groq(DEFAULT_GROQ_MODEL, system_prompt, user_prompt, temperature, 3000)
        if result:
            metadata["provider"] = "groq"
            metadata["model"] = DEFAULT_GROQ_MODEL
            metadata["fallback_from"] = f"{provider}/{resolved_model}"
            return result, metadata
        metadata["providers_tried"].append({"provider": "groq", "model": DEFAULT_GROQ_MODEL, "error": "no response"})

    logger.error("[LLM_ROUTER] Toutes les IA ont échoué.")
    return None, metadata


# ─── Introspection (UI / dashboard) ──────────────────────────────────────
def list_models() -> list:
    """Catalogue groupé par fournisseur, pour le dropdown des comptes."""
    groups = {}
    for entry in MODEL_CATALOG:
        provider = entry["provider"]
        if provider not in groups:
            info = PROVIDERS.get(provider, {})
            groups[provider] = {"provider": provider, "label": info.get("label", provider), "models": []}
        groups[provider]["models"].append({"id": entry["id"], "label": entry["label"]})
    return list(groups.values())


def get_status() -> dict:
    """État des fournisseurs : clé .env configurée ?"""
    status = {}
    for provider, info in PROVIDERS.items():
        env_key = info.get("env_key")
        key = os.getenv(env_key, "").strip() if env_key else None
        status[provider] = {
            "label": info.get("label", provider),
            "configured_env": bool(key),
            "api_type": info.get("api_type"),
        }
    return status
