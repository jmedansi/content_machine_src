import os
import re
import json
import requests
import sys
import io
import argparse
import requests
from pathlib import Path
from typing import Dict, Any, Optional

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR / "machines" / "facebook_machine"))
sys.path.insert(0, str(_ROOT_DIR))
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (ValueError, AttributeError):
        pass
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Imports depuis le module partagé
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared_agents.models import AgentResult

# Configuration - sera injectée par le caller
_config = None

def set_config(config_dict: dict):
    """Configure le module avec les paramètres globaux."""
    global _config
    _config = config_dict

def _get_config():
    """Retourne la config, utilise les valeurs par défaut si non définie."""
    if _config:
        return _config
    # Prefer the project's core.config, fallback to facebook_machine legacy config
    try:
        from core.config import Config
        return Config
    except Exception:
        return None

def _get_logger(name: str):
    """Retourne un logger."""
    try:
        from core.logger import get_node_logger
        return get_node_logger(name)
    except Exception:
        import logging
        return logging.getLogger(name)

DEFAULT_CONFIG = {
    "min_words": 400,
    "max_words": 600,
    "target_words": 500,
    "tolerance_percent": 10,
    "retry_max": 2,
    "humanize_pass": False,
    "generates_resource": False,
    "output_format": "text"
}

MODEL_POSTS = "llama-3.3-70b-versatile"

def clean_for_facebook(text: str) -> str:
    text = re.sub(r'^\s*(?:---+\s*POST\s*---+|\[POST\]|POST\s*:|(?i:voici le post)[:\s]*)\s*\n*', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text) 
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    pattern_words = r'\n*[\(\[\*\_]?\s*(?i:environ|note\s*:|mot|pages de mots|word count|mots)?\s*[:=]?\s*\d+\s*(?i:mots?|words?)\.?\s*[\)\]\*\_]?\s*$'
    text = re.sub(pattern_words, '', text, flags=re.MULTILINE)
    text = re.sub(pattern_words, '', text, flags=re.MULTILINE)
    text = re.sub(r'\n---+\n(?:Structure|Améliorations|Note|Explications|Ce post).*$', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'^(?:Post|Contenu|Texte)\s*:\s*', '', text, flags=re.IGNORECASE)
    return text.strip().strip('"')

def _load_persona_part(shared_dir: Path, filename: str) -> str:
    path = shared_dir / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""

def load_persona(persona_name: str, account_id: int = None, platform: str = "facebook") -> dict:
    config = _get_config()
    try:
        from core.paths import PLATFORM_BASE
        platform_bases = PLATFORM_BASE
    except ImportError:
        platform_bases = {
            "facebook": _ROOT_DIR / "machines" / "facebook_machine",
            "linkedin": _ROOT_DIR / "machines" / "linkedin_machine",
            "twitter":  _ROOT_DIR / "machines" / "twitter_machine",
        }
    base_dir = platform_bases.get(platform)
    if not base_dir:
        base_dir = config.BASE_DIR if config else _ROOT_DIR / "machines" / "facebook_machine"
    
    if account_id:
        persona_dir = base_dir / "accounts" / str(account_id) / "persona" / persona_name
        shared_dir = base_dir / "accounts" / str(account_id) / "persona" / "_shared"
        # Fallback to legacy acc_* structure check: try accounts/<id>/persona then fallback to acc_<id>
        if not persona_dir.exists():
            persona_dir = base_dir / "accounts" / str(account_id) / "persona" / persona_name
            shared_dir = base_dir / "accounts" / str(account_id) / "persona" / "_shared"
            if not persona_dir.exists():
                # legacy fallback (will be removed in future)
                persona_dir = base_dir / f"acc_{account_id}" / "persona" / persona_name
                shared_dir = base_dir / f"acc_{account_id}" / "persona" / "_shared"
    else:
        persona_dir = (config.PERSONAS_DIR if config else base_dir / "persona") / persona_name
        shared_dir = (config.PERSONAS_DIR if config else base_dir / "persona") / "_shared"
    
    if not persona_dir.exists():
        return None
        
    config_file = persona_dir / "config.json"
    persona_config = DEFAULT_CONFIG.copy()
    if config_file.exists():
        persona_config.update(json.loads(config_file.read_text(encoding="utf-8")))
        
    system_prompt_file = persona_dir / "system_prompt.md"
    system_prompt = system_prompt_file.read_text(encoding="utf-8") if system_prompt_file.exists() else ""
    
    examples = ""
    examples_file = persona_dir / "examples.md"
    if examples_file.exists():
        content = examples_file.read_text(encoding="utf-8")
        if "à remplacer" not in content.lower() and content.strip():
            examples = content
            
    format_data = None
    format_file = persona_dir / "format.json"
    if format_file.exists():
        try:
            format_data = json.loads(format_file.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    return {
        "system": system_prompt,
        "accroches": _load_persona_part(shared_dir, "accroches.md"),
        "anti_ai": _load_persona_part(shared_dir, "anti_ai_rules.md"),
        "examples": examples,
        "config": persona_config,
        "format": format_data,
        "persona_name": persona_name
    }

def build_system_prompt(persona: dict) -> str:
    parts = []
    for k in ["accroches", "anti_ai", "system"]:
        if persona.get(k): parts.append(persona[k])
        
    config = persona.get("config", DEFAULT_CONFIG)
    parts.append("""
INTERDICTIONS ABSOLUES DE MARQUE :
- IDENTITÉ : Tu es Jean-Marc DANSI, "Le Taximan du Digital". Tu partages ton expertise en IA et automatisation pour aider les business à scaler.
- GÉNÉRALISATION OBLIGATOIRE : NE JAMAIS inventer d'anecdotes personnelles spécifiques.
- UTILISE TOUJOURS : "Il n'est pas rare de voir...", "Tu connais sûrement quelqu'un qui...", "Ils sont nombreux à...".
- PAS DE VILLES : Ne cite jamais Dakar, Abidjan ou toute autre ville spécifique.
- BÉNÉFICES > FONCTIONS : Ne liste pas ce que fait un outil. Dis ce que l'utilisateur y gagne concrètement.
- N'invente jamais de détails personnels sur Jean-Marc.
- Si tu n'as pas l'information -> parle à la 2ème personne ("tu") ou en général, jamais en "je" pour des faits inventés.
- Retourne UNIQUEMENT le contenu final, sans aucun commentaire, explication, métadonnées ou bloc de type "Structure respectée" à la fin.
""")
    if persona.get("examples"):
        parts.append(f"## EXEMPLES DE TON STYLE\n{persona['examples']}")
    return "\n\n---\n\n".join(parts)



def call_kimi(system_prompt: str, user_prompt: str, model: str) -> str:
    config = _get_config()
    logger = _get_logger("copywriter")
    if not config or not getattr(config, "KIMI_API_KEY", None):
        return None
    base_url = getattr(config, "KIMI_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.KIMI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 1,
                "max_tokens": 1450,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    return content
                logger.warning("[COPYWRITER] Kimi: réponse 200 mais contenu vide")
            else:
                logger.warning("[COPYWRITER] Kimi: réponse 200 mais choices vide")
        else:
            logger.error(f"[COPYWRITER] Kimi HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        logger.error(f"[COPYWRITER] Exception Kimi: {e}")
    return None


def call_llm(system_prompt: str, user_prompt: str, model: str = None,
             api_key: str = None, base_url: str = None) -> tuple[str, dict]:
    """Route vers le provider sélectionné via core.llm_router (fallback en cascade)."""
    from core.llm_router import call_llm as router_call_llm
    return router_call_llm(
        system_prompt, user_prompt,
        model=model, api_key=api_key, base_url=base_url,
        temperature=0.8, max_tokens=3000,
    )

def verify_and_retry(text: str, config: dict, system_prompt: str, model: str = None,
                     api_key: str = None, base_url: str = None) -> tuple[str, int]:
    if not text:
        return text, 0
    word_count = len(text.split())
    min_w = config.get("min_words", 400)
    max_w = config.get("max_words", 600)
    retries = config.get("retry_max", 2)
    
    if min_w <= word_count <= max_w:
        return text, word_count
        
    best_text, best_count = text, word_count
    for attempt in range(retries):
        if word_count < min_w:
            msg = f"Développe ce texte pour atteindre {min_w} mots sans changer le sens. Texte:\n{best_text}"
        else:
            msg = f"Réduis ce texte pour atteindre {max_w} mots sans changer le sens. Texte:\n{best_text}"
        
        try:
            new_text, _ = call_llm(system_prompt, msg, model=model, api_key=api_key, base_url=base_url)
            if new_text and len(new_text.strip()) > 0:
                n_count = len(new_text.split())
                if min_w <= n_count <= max_w:
                    return new_text, n_count
                best_text, best_count = new_text, n_count
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
    
    return best_text, best_count

def parse_cta_response(text: str) -> dict:
    result = {"post": text, "resource": "", "trigger_word": ""}
    post_match = re.search(r'---POST---(.*?)---RESSOURCE---', text, re.DOTALL)
    res_match = re.search(r'---RESSOURCE---(.*?)---FIN---', text, re.DOTALL)
    
    if post_match: result["post"] = post_match.group(1).strip()
    if res_match: result["resource"] = res_match.group(1).strip()
    
    triggers = re.findall(r'Commente[sz]?\s*\*\*?(\w+)\*\*?', result["post"], re.IGNORECASE)
    if not triggers:
        triggers = re.findall(r'Commente[sz]?\s+(\w+)', result["post"], re.IGNORECASE)
        
    if triggers:
        result["trigger_word"] = triggers[0].upper()
    return result

def parse_trigger_comments(text: str) -> list:
    comments = []
    pattern = r'^\s*(\d+)[.)]\s*(.+?)(?=^\s*\d+[.)]|\s*$)'
    matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
    for num, content in matches:
        clean_content = content.strip()
        if len(clean_content) > 20:
            comments.append({
                "number": int(num),
                "content": clean_content
            })
    return sorted(comments, key=lambda x: x["number"], reverse=True)

def humanize_pass(text: str, system_prompt: str, model: str = None,
                  api_key: str = None, base_url: str = None) -> str:
    if not text or not text.strip():
        return text
    prompt = f"Relis ce texte. Supprime toute tournure qui semble générée par une IA. Reste authentique, direct et humain. Ne change pas le sens ni la longueur. Retourne UNIQUEMENT le texte final.\n\nTexte:\n{text}"
    try:
        result_text, _ = call_llm(system_prompt, prompt, model=model, api_key=api_key, base_url=base_url)
        return result_text if result_text and result_text.strip() else text
    except Exception as e:
        return text

def run_copywriter(folder_path: str, plan_entry: Dict[str, Any], task_id: str = None, account_id: int = None, platform: str = "facebook", model: str = None, llm_config: dict = None) -> AgentResult:
    """Génère le texte et le sauvegarde dans le dossier ciblé.

    llm_config: dict optionnel {"model", "api_key", "base_url"} — permet de
    fournir la clé API / URL de base du provider directement (ex: depuis le compte)."""
    logger = _get_logger("copywriter")
    api_key = (llm_config or {}).get("api_key") or None
    base_url = (llm_config or {}).get("base_url") or None
    try:
        content_dir = Path(folder_path)
        content_dir.mkdir(parents=True, exist_ok=True)
        
        persona_name = plan_entry.get("persona", "expert_ia")
        topic = plan_entry.get("topic") or plan_entry.get("sujet", "")
        audience = plan_entry.get("audience", "tous")
        objectif = plan_entry.get("objectif", "engagement")
        format_hint = plan_entry.get("format", "")
        context_anchor = plan_entry.get("context", "") or plan_entry.get("story", "") or ""
        
        persona = load_persona(persona_name, account_id, platform)
        if not persona:
            return AgentResult.fail(f"Persona introuvable: {persona_name}")
            
        config = persona.get("config", DEFAULT_CONFIG)
        system_prompt = build_system_prompt(persona)
        
        format_data = persona.get("format")
        variables = plan_entry.get("variables")
        
        if format_data and format_data.get("user_prompt_template") and variables:
            user_prompt = format_data["user_prompt_template"]
            for k, v in variables.items():
                user_prompt = user_prompt.replace(f"{{{k}}}", str(v))
        else:
            user_prompt = f"Audience: {audience}\nObjectif: {objectif}\n"
            if format_hint: user_prompt += f"Format imposé: {format_hint}\n"
            user_prompt += f"Sujet: {topic}\n"
            if context_anchor: user_prompt += f"Contexte factuel à utiliser: {context_anchor}\n"
            if plan_entry.get("context"):
                user_prompt += f"Context: {plan_entry.get('context')}\n"
            if plan_entry.get("story"):
                user_prompt += f"Histoire: {plan_entry.get('story')}\n"
            user_prompt += f"Cible: {config.get('target_words', 500)} mots."
            
        logger.info(f"[COPYWRITER] Génération texte pour {persona_name}")
        raw_text, llm_metadata = call_llm(system_prompt, user_prompt, model=model, api_key=api_key, base_url=base_url)
        
        if not raw_text:
            error_details = ", ".join([p.get("error", "unknown") for p in llm_metadata.get("providers_tried", [])])
            logger.error(f"[COPYWRITER] ÉCHEC: {error_details}")
            return AgentResult.fail(f"Les APIs IA ont échoué. Errors: {error_details}")
        
        format_type = config.get("format", "long")
        meta_trigger = ""

        if format_type == "trigger":
            final_text = raw_text
            word_count = len(raw_text.split())
        elif format_type == "cta":
            parsed = parse_cta_response(raw_text)
            final_text = parsed.get("post", raw_text)
            final_text, word_count = verify_and_retry(final_text, config, system_prompt, model=model, api_key=api_key, base_url=base_url)
            
            res_data = {
                "type": "cta",
                "content": parsed.get("resource", ""),
                "trigger_word": parsed.get("trigger_word", "")
            }
            (content_dir / "resource.json").write_text(json.dumps(res_data, indent=2, ensure_ascii=False), encoding="utf-8")
            meta_trigger = parsed.get("trigger_word", "")
        else:
            final_text, word_count = verify_and_retry(raw_text, config, system_prompt, model=model, api_key=api_key, base_url=base_url)
            meta_trigger = ""
            
        if config.get("humanize_pass"):
            logger.info("Application de la passe d'humanisation...")
            humanize_sys = "Tu es un expert en réécriture. Ton but est de rendre le texte suivant plus humain, direct et sans tics d'IA."
            final_text = humanize_pass(final_text, humanize_sys, model=model, api_key=api_key, base_url=base_url)
            
        final_text = clean_for_facebook(final_text)
        signature = config.get("signature") or ""
        sig_norm = re.sub(r'[^a-zA-Z0-9]', '', signature).upper()
        text_norm = re.sub(r'[^a-zA-Z0-9]', '', final_text).upper()
        
        if signature and sig_norm not in text_norm:
            final_text += f"\n\n{signature}"
        
        # Sauvegarder selon le format de la plateforme
        post_filename = f"{platform}_post.txt"
        (content_dir / post_filename).write_text(final_text, encoding="utf-8")
        
        # Gestion des commentaires épinglés
        if format_type in ("court", "trigger"):
            if format_type == "trigger":
                sys_comment = """Tu es Jean-Marc DANSI. Reçois ce post trigger et génère les commentaires de développement.
Chaque commentaire doit être numéroté (1., 2., 3., etc.) et apporter une information concrète, technique et actionnable.
Développe chaque point avec 3 à 5 phrases détaillées. Maximum 10 commentaires."""
                usr_comment = f"Post:\n{final_text}\n\nGénère les commentaires de développement."
            else:
                sys_comment = "Tu es Jean-Marc DANSI. Rédige le commentaire épinglé (300 mots) plein de détails actionnables."
                usr_comment = f"Post: {final_text}\n\nRédige le commentaire."
            
            pinned_text, _ = call_llm(sys_comment, usr_comment, model=model, api_key=api_key, base_url=base_url)
            if pinned_text:
                if format_type == "trigger":
                    comments = parse_trigger_comments(pinned_text)
                    if comments:
                        (content_dir / "trigger_comments.json").write_text(json.dumps(comments, indent=2, ensure_ascii=False), encoding="utf-8")
                else:
                    (content_dir / "pinned_comment.txt").write_text(clean_for_facebook(pinned_text), encoding="utf-8")
        
        has_pinned_comment = (content_dir / "pinned_comment.txt").exists()
        meta = {
            "topic": topic,
            "persona": persona_name,
            "word_count": word_count,
            "status": "pending",
            "published": False,
            "created_at": datetime.now().isoformat(),
            "llm_provider": llm_metadata.get("provider", "unknown"),
            "llm_model": llm_metadata.get("model", "unknown"),
            "copywriter_stage": "success",
            "has_pinned_comment": has_pinned_comment,
            "platform": platform,
            "account_id": account_id
        }
        if meta_trigger:
            meta["trigger_word"] = meta_trigger
            
        (content_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        
        return AgentResult.ok(meta)
        
    except Exception as e:
        logger.exception("Erreur Copywriter")
        return AgentResult.fail(str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Copywriter Agent")
    parser.add_argument("--persona", type=str, required=True, help="Persona name")
    parser.add_argument("--folder", type=str, required=True, help="Output folder")
    parser.add_argument("--topic", type=str, help="Topic", default="Test")
    parser.add_argument("--platform", type=str, default="facebook", help="Platform")
    parser.add_argument("--account-id", type=int, default=None, help="Account ID")
    
    args = parser.parse_args()
    
    plan_entry = {
        "persona": args.persona,
        "sujet": args.topic,
    }
    
    res = run_copywriter(args.folder, plan_entry, account_id=args.account_id, platform=args.platform)
    print(f"Résultat: {res.success} - {res.error_cause or 'OK'}")