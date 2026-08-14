import os
import re
import json
import requests
import sys
import io
import argparse
import requests
from typing import Dict, Any, Optional
# if sys.platform == "win32":
#     try:
#         if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
#             sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
#         if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
#             sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
#     except (ValueError, AttributeError):
#         pass
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger
from core.task_tracker import create_task, update_task, get_task

logger = get_node_logger("copywriter")

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

def clean_for_facebook(text: str) -> str:
    # 1. Nettoyer les balises au début du texte
    text = re.sub(r'^\s*(?:---+\s*POST\s*---+|\[POST\]|POST\s*:|(?i:voici le post)[:\s]*)\s*\n*', '', text)
    
    # 2. Nettoyer le formatage Markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text) 
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    
    # 3. Nettoyer agressivement le compte de mots à la fin (ex: "400 mots", "(Environ 400 mots)", "Note: 400 mots")
    pattern_words = r'\n*[\(\[\*\_]?\s*(?i:environ|note\s*:|mot|nombre de mots|word count|mots)?\s*[:=]?\s*\d+\s*(?i:mots?|words?)\.?\s*[\)\]\*\_]?\s*$'
    text = re.sub(pattern_words, '', text, flags=re.MULTILINE)
    text = re.sub(pattern_words, '', text, flags=re.MULTILINE) # Deux passes au cas où
    
    # 4. Nettoyer les blocs méta à la fin (ex: "Structure respectée", "Améliorations", "Ce post respecte")
    text = re.sub(r'\n---+\n(?:Structure|Améliorations|Note|Explications|Ce post).*$', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 5. Supprimer les préfixes type "Post :" ou "Contenu :"
    text = re.sub(r'^(?:Post|Contenu|Texte)\s*:\s*', '', text, flags=re.IGNORECASE)
    
    # 6. Normaliser l'espacement entre paragraphes
    lines = text.split('\n')
    result = []
    prev_was_empty = True
    for line in lines:
        stripped = line.strip()
        if stripped == '':
            if not prev_was_empty:
                result.append('')
                prev_was_empty = True
            continue
        if not prev_was_empty:
            result.append('')
        result.append(stripped)
        prev_was_empty = False
    
    return '\n'.join(result).strip().strip('"')

def _load_persona_part(shared_dir: Path, filename: str) -> str:
    path = shared_dir / filename
    return path.read_text(encoding="utf-8") if path.exists() else ""

def load_persona(persona_name: str, account_id: int = None, platform: str = "facebook") -> dict:
    if account_id:
        # On utilise le PLATFORM_BASE si possible
        platform_bases = {
            "facebook": Path("d:/Content_Machine/machines/facebook_machine"),
            "linkedin": Path("d:/Content_Machine/machines/linkedin_machine"),
            "twitter":  Path("d:/Content_Machine/machines/twitter_machine"),
            "instagram": Path("d:/Content_Machine/machines/facebook_machine")
        }
        base_dir = platform_bases.get(platform, Config.BASE_DIR)
        persona_dir = base_dir / "accounts" / str(account_id) / "persona" / persona_name
        shared_dir = base_dir / "accounts" / str(account_id) / "persona" / "_shared"
    else:
        persona_dir = Config.PERSONAS_DIR / persona_name
        shared_dir = Config.PERSONAS_DIR / "_shared"
    
    if not persona_dir.exists():
        return None
        
    config_file = persona_dir / "config.json"
    config = DEFAULT_CONFIG.copy()
    if config_file.exists():
        config.update(json.loads(config_file.read_text(encoding="utf-8")))
        
    system_prompt_file = persona_dir / "system_prompt.md"
    system_prompt = system_prompt_file.read_text(encoding="utf-8") if system_prompt_file.exists() else ""
    
    examples = ""
    examples_file = persona_dir / "examples.md"
    if examples_file.exists():
        content = examples_file.read_text(encoding="utf-8")
        if "à remplacer" not in content.lower() and content.strip():
            examples = content
            
    return {
        "system": system_prompt,
        "accroches": _load_persona_part(shared_dir, "accroches.md"),
        "anti_ai": _load_persona_part(shared_dir, "anti_ai_rules.md"),
        "examples": examples,
        "config": config,
        "persona_name": persona_name
    }

def build_system_prompt(persona: dict) -> str:
    parts = []
    for k in ["accroches", "anti_ai", "system"]:
        if persona.get(k): parts.append(persona[k])
        
    config = persona.get("config", DEFAULT_CONFIG)
    format_type = config.get("format", "long")
    
    brand_rules = """
INTERDICTIONS ABSOLUES DE MARQUE :
- IDENTITÉ : Tu es Jean-Marc DANSI, "Le Taximan du Digital". Tu partages ton expertise en IA et automatisation pour aider les business à scaler.
- GÉNÉRALISATION OBLIGATOIRE : NE JAMAIS inventer d'anecdotes personnelles spécifiques (ex: "Hier j'ai vu un gars", "J'ai vu une boîte").
- UTILISE TOUJOURS : "Il n'est pas rare de voir...", "Tu connais sûrement quelqu'un qui...", "Ils sont nombreux à...".
- PAS DE VILLES : Ne cite jamais Dakar, Abidjan ou toute autre ville spécifique.
- BÉNÉFICES > FONCTIONS : Ne liste pas ce que fait un outil. Dis ce que l'utilisateur y gagne concrètement.
- N'invente jamais de détails personnels sur Jean-Marc (enfants, conjoint, ville précise, etc.).
- Si tu n'as pas l'information -> parle à la 2ème personne ("tu") ou en général, jamais en "je" pour des faits inventés.
"""
    # Pour le format formation, on ne force pas "Retourne UNIQUEMENT le contenu final"
    # car le format nécessite un JSON de sortie.
    if format_type not in ("formation",):
        brand_rules += "- Retourne UNIQUEMENT le contenu final, sans aucun commentaire, explication, métadonnées ou bloc de type \"Structure respectée\" ou \"Note de l'IA\" à la fin.\n"
    
    # Règles de lisibilité pour tous les formats sauf formation (qui a sa propre structure)
    if format_type not in ("formation",):
        brand_rules += """
RÈGLES DE LISIBILITÉ :
- Ajoute des émojis (stickers) dans le post : 🚀 💡 ⚡ ✅ 🔥 📊 🎯 📈 🤖 💻 👨‍💻 ⏱️ 🧠 (1 émoji par paragraphe max).
- Chaque paragraphe doit faire MAXIMUM 2-3 phrases. Découpe les longs blocs.
- Saute une ligne ENTRE chaque paragraphe pour aérer le texte.
- Varie la longueur des phrases : courtes pour percuter, plus longues pour développer.
"""
    
    parts.append(brand_rules)
    if persona.get("examples"):
        parts.append(f"## EXEMPLES DE TON STYLE\n{persona['examples']}")
    return "\n\n---\n\n".join(parts)

def call_kimi(system_prompt: str, user_prompt: str, model: str) -> str:
    if not getattr(Config, "KIMI_API_KEY", None):
        return None
    base_url = getattr(Config, "KIMI_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.KIMI_API_KEY}",
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
    result, metadata = router_call_llm(
        system_prompt, user_prompt,
        model=model, api_key=api_key, base_url=base_url,
        temperature=0.8, max_tokens=3000,
    )
    if result:
        logger.info(f"[COPYWRITER] Génération réussie via {metadata.get('provider')} ({metadata.get('model')})")
    else:
        errors = ", ".join([p.get("error", "unknown") for p in metadata.get("providers_tried", [])])
        logger.error(f"[COPYWRITER] Toutes les IA ont échoué: {errors}")
    return result, metadata


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
    """Parse les commentaires numérotés 1., 2., 3., etc. depuis le texte généré."""
    comments = []
    # Trouve tous les commentaires au format "1. texte" ou "1) texte" ou "1 texte"
    pattern = r'^\s*(\d+)[.)]\s*(.+?)(?=^\s*\d+[.)]|\s*$)'
    matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
    for num, content in matches:
        clean_content = content.strip()
        if len(clean_content) > 20:  # Filtre les commentaire trop courts
            comments.append({
                "number": int(num),
                "content": clean_content
            })
    # Trier par numéro décroissant pour publication dernier→premier
    return sorted(comments, key=lambda x: x["number"], reverse=True)

def humanize_pass(text: str, system_prompt: str, model: str = None,
                  api_key: str = None, base_url: str = None) -> str:
    """Relance une boucle pour humaniser le texte et supprimer les tics d'IA."""
    if not text or not text.strip():
        return text
    prompt = f"Relis ce texte. Supprime toute tournure qui semble générée par une IA. Reste authentique, direct et humain. Ne change pas le sens ni la longueur. Retourne UNIQUEMENT le texte final, sans aucun commentaire, explication ou balise.\n\nTexte:\n{text}"
    try:
        result_text, _ = call_llm(system_prompt, prompt, model=model, api_key=api_key, base_url=base_url)
        return result_text if result_text and result_text.strip() else text
    except Exception as e:
        logger.warning(f"Humanize pass failed: {e}")
        return text

def _add_section(lines: list, header: str, need_sep: bool):
    """Ajoute une section avec ═════ + header + ═════, optionnellement précédée de ✧ ✧ ✧."""
    # Nettoyer les lignes vides et ═════ en fin de result
    while lines and (lines[-1].strip() == '' or lines[-1].strip().startswith('═════')):
        lines.pop()
    while lines and lines[-1].strip() == '':
        lines.pop()
    if need_sep:
        lines.append('')
        lines.append('✧ ✧ ✧')
        lines.append('')
    lines.append('════════════════════')
    lines.append(header)
    lines.append('════════════════════')

def post_process_formation_text(text: str) -> str:
    """Ajoute les émojis et séparateurs manquants dans un post formation."""
    result = []
    sections_seen = set()
    
    for line in text.split('\n'):
        stripped = line.strip()
        plain = re.sub(r'[^\w\s]', '', stripped).strip().upper()
        
        # 🧠 SÉANCE X/120
        m = re.search(r'(SÉANCE\s+\d+/\d+)', plain)
        if m:
            result.append(f'🧠 {m.group(1)}')
            sections_seen.add('seance')
            continue

        # 📋 AU PROGRAMME
        if plain in ('AU PROGRAMME',):
            _add_section(result, '📋 AU PROGRAMME', False)
            sections_seen.add('programme')
            continue

        # 📖 LE COURS
        if plain in ('LE COURS',):
            _add_section(result, '📖 LE COURS', True)
            sections_seen.add('cours')
            continue

        # ✍️ EXERCICE
        if plain in ('EXERCICE',):
            _add_section(result, '✍️ EXERCICE', True)
            sections_seen.add('exercice')
            continue

        # Ignorer les lignes ═════ et ✧ hors contexte (seront gérées par _add_section)
        if stripped.startswith('═════') or stripped == '✧ ✧ ✧':
            continue

        if stripped == '' and result and result[-1].strip() == '':
            continue
        result.append(line)

    full = '\n'.join(result)
    if '#JM' not in full:
        full = full.rstrip() + '\n\n#JM'
    
    return full


def _break_long_paragraphs(text: str, max_sentences: int = 3) -> str:
    """Découpe les paragraphes trop longs en paragraphes plus courts."""
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        # Compter et découper par phrase
        sentences = re.split(r'(?<=[.!?])\s+', stripped)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) > max_sentences:
            for i in range(0, len(sentences), max_sentences):
                chunk = ' '.join(sentences[i:i + max_sentences])
                result.append(chunk)
        else:
            result.append(stripped)
    # Re-normaliser l'espacement
    final = []
    prev_was_empty = True
    for line in result:
        stripped = line.strip()
        if stripped == '':
            if not prev_was_empty:
                final.append('')
                prev_was_empty = True
            continue
        if not prev_was_empty:
            final.append('')
        final.append(stripped)
        prev_was_empty = False
    return '\n'.join(final)


_STICKER_POOL = ['🚀', '💡', '⚡', '✅', '🔥', '🎯', '📈', '🧠', '💻', '⏱️', '🤖', '🎯', '📊', '👨‍💻', '💪', '🔑', '🎓', '💎']

def _add_stickers(text: str) -> str:
    """Ajoute un sticker au début de chaque paragraphe qui n'en a pas déjà un."""
    lines = text.split('\n')
    result = []
    sticker_idx = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        if stripped[0] in ('#', '@'):
            result.append(line)
            continue
        # Vérifie si la ligne commence déjà par un emoji
        if re.match(r'[\U0001F300-\U0001FFFF\U0000200D\uFE0F]', stripped):
            result.append(line)
            continue
        # Vérifie si c'est une signature-type
        if 'Jean-Marc' in stripped:
            result.append(line)
            continue
        sticker = _STICKER_POOL[sticker_idx % len(_STICKER_POOL)]
        sticker_idx += 1
        result.append(f'{sticker} {stripped}')
    return '\n'.join(result)


def _extract_formation_lessons(text: str) -> list:
    """Extrait les points d'apprentissage depuis la section AU PROGRAMME."""
    lessons = []
    in_programme = False
    for line in text.split('\n'):
        raw = line.strip()
        stripped = raw.lstrip('● ').lstrip('▸ ').lstrip('- ')
        clean = re.sub(r'^[^\w\s]+', '', raw).strip().upper()
        if 'AU PROGRAMME' in raw.upper():
            in_programme = True
            continue
        if in_programme:
            if 'LE COURS' in clean:
                break
            if raw.startswith('✧') or raw.startswith('════'):
                continue
            if stripped and len(stripped) > 5 and len(stripped) < 100:
                lessons.append(stripped)
    return lessons[:4]


def run_copywriter(folder_path: str, plan_entry: Dict[str, Any], task_id: str = None, account_id: int = None, platform: str = "facebook", model: str = None, llm_config: dict = None) -> AgentResult:
    """Génère le texte et le sauvegarde dans le dossier ciblé.

    llm_config: dict optionnel {"model", "api_key", "base_url"} — permet de
    fournir la clé API / URL de base du provider directement (ex: depuis le compte)."""
    api_key = (llm_config or {}).get("api_key") or None
    base_url = (llm_config or {}).get("base_url") or None
    try:
        # Créer une tâche si pas d'ID fourni
        if not task_id:
            task_id = create_task("copywriter", folder_path, "Génération du texte en cours...")
        else:
            update_task(task_id, progress=10, status="running", log="Démarrage de la génération...")
        
        content_dir = Path(folder_path)
        content_dir.mkdir(parents=True, exist_ok=True)
        
        persona_name = plan_entry.get("persona", "expert_ia")
        topic = plan_entry.get("topic") or plan_entry.get("sujet", "")
        audience = plan_entry.get("audience", "tous")
        objectif = plan_entry.get("objectif", "engagement")
        format_hint = plan_entry.get("format", "")
        context_anchor = plan_entry.get("context", "") or plan_entry.get("story", "") or ""
        
        update_task(task_id, progress=20, log=f"Chargement du persona: {persona_name}")
        persona = load_persona(persona_name, account_id, platform)
        if not persona:
            update_task(task_id, status="failed", message=f"Persona introuvable: {persona_name}")
            return AgentResult.fail(f"Persona introuvable: {persona_name}")
            
        config = persona.get("config", DEFAULT_CONFIG)
        system_prompt = build_system_prompt(persona)
        format_type = config.get("format", "long")
        
        user_prompt = f"Audience: {audience}\nObjectif: {objectif}\n"
        if format_hint: user_prompt += f"Format imposé: {format_hint}\n"
        user_prompt += f"Sujet: {topic}\n"
        if context_anchor: user_prompt += f"Contexte factuel à utiliser: {context_anchor}\n"
        # Ajouter le contexte supplémentaire si présent
        if plan_entry.get("context"):
            user_prompt += f"Context: {plan_entry.get('context')}\n"
        if plan_entry.get("story"):
            user_prompt += f"Histoire: {plan_entry.get('story')}\n"
            
        if format_type == "formation":
            user_prompt += """
Écris un post de formation complet et DÉTAILLÉ (200 à 500 mots) avec EXACTEMENT cette structure. Recopie les emojis et le formatage :

🧠 SÉANCE X/120 : [TITRE]

════════════════════
📋 AU PROGRAMME
════════════════════

● Objectif 1
● Objectif 2
● Objectif 3

✧ ✧ ✧

📖 LE COURS

[Au moins 4 paragraphes. Développe avec des ◈ ▸ ●. Utilise des analogies.]

✧ ✧ ✧

✍️ EXERCICE

[Exercice simple + exemple. Termine par:]
Abonne-toi pour ne rien rater des prochaines séances et partage ta réponse en commentaire.

#JM

---IMAGE PROMPT---
[prompt technique en anglais pour générer l'image]

RÈGLES : zéro jargon, public débutant, ton pratique et encourageant, exemples 2026, jamais de chiffres précis non sourcés. Écris DIRECTEMENT le post, pas de JSON."""
        else:
            user_prompt += f"""Cible: {config.get('target_words', 500)} mots.

IMPORTANT: Ta réponse DOIT ÊTRE UN OBJET JSON VALIDE contenant exactement deux clés:
1. "post_content": Le texte du post.
2. "image_prompt": Le prompt en français pour générer l'image. CE PROMPT DOIT RESPECTER SCRUPULEUSEMENT LES "DIRECTIVES DE GÉNÉRATION D'IMAGE" DU SYSTEM PROMPT (Si le système interdit les humains, N'INCLUS AUCUNE PERSONNE. Respecte le style demandé : mockup, 3D, etc)."""
        # ── Indication utilisateur (régénération guidée) ──
        indication = plan_entry.get("indication", "")
        if indication:
            user_prompt += f"\n\nINSTRUCTION SPÉCIALE POUR CETTE RÉGÉNÉRATION :\n{indication}\nPrends cette remarque en compte IMPÉRATIVEMENT."
            logger.info(f"[COPYWRITER] Indication utilisateur injectée: {indication[:80]}")
        
        update_task(task_id, progress=30, log="Appel IA en cours...")
        raw_text, llm_metadata = call_llm(system_prompt, user_prompt, model=model, api_key=api_key, base_url=base_url)
        
        if not raw_text:
            update_task(task_id, status="failed", message="Toutes les clés API ont échoué")
            error_details = ", ".join([p.get("error", "unknown") for p in llm_metadata.get("providers_tried", [])])
            logger.error(f"[COPYWRITER] ÉCHEC copywriter: {error_details}")
            return AgentResult.fail(f"Les APIs IA ont échoué après retry. Errors: {error_details}")
        
        # --- PARSING DU CONTENU (JSON pour trigger/cta, markers pour formation) ---
        retry_system_prompt = None
        if format_type == "formation":
            # Format formation: extraire ---IMAGE PROMPT--- depuis le texte brut
            img_marker = "---IMAGE PROMPT---"
            post_content = raw_text
            image_prompt = ""
            if img_marker in raw_text:
                parts = raw_text.split(img_marker, 1)
                post_content = parts[0].strip()
                image_prompt = parts[1].strip()
            raw_text = post_content
            
            # Sauver l'image_prompt dans meta.json
            meta_file = content_dir / "meta.json"
            meta = {}
            if meta_file.exists():
                try: meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except: pass
            if image_prompt:
                meta["image_prompt"] = image_prompt
            elif not meta.get("image_prompt"):
                meta["image_prompt"] = ""
            meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            # Parsing JSON pour les autres formats
            clean_json = raw_text.strip()
            import re as _re
            _json_match = _re.search(r'\{[\s\S]*\}', clean_json)
            if _json_match:
                clean_json = _json_match.group(0)
            elif clean_json.startswith("```json"):
                clean_json = clean_json.split("```json", 1)[1]
                if clean_json.endswith("```"):
                    clean_json = clean_json.rsplit("```", 1)[0]
            clean_json = clean_json.strip()

            try:
                parsed_data = json.loads(clean_json)
                post_content = parsed_data.get("post_content", "")
                image_prompt = parsed_data.get("image_prompt", "")

                # ── Mise à jour du meta.json (préservation du image_prompt existant) ──
                meta_file = content_dir / "meta.json"
                meta = {}
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                existing_prompt = meta.get("image_prompt", "")
                if image_prompt:
                    meta["image_prompt"] = image_prompt
                elif existing_prompt:
                    meta["image_prompt"] = existing_prompt
                meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

                # On remplace raw_text par le vrai texte pour le reste de la pipeline
                raw_text = post_content if post_content else raw_text
            except json.JSONDecodeError as e:
                logger.error(f"[COPYWRITER] Échec du parsing JSON ({e}). On continue avec raw_text comme fallback.")
                logger.error(f"Valeur de clean_json : {clean_json[:500]}...")

        # Modifier le system_prompt pour les retries (pour éviter qu'il renvoie du JSON)
        if not retry_system_prompt:
            retry_system_prompt = system_prompt.split("## FORMAT DE SORTIE (JSON OBLIGATOIRE)")[0]
        
        update_task(task_id, progress=60, log="Vérification du contenu...")
            
        meta_trigger = ""

        if format_type == "trigger" or format_type == "formation":
            final_text = raw_text
            word_count = len(raw_text.split())
        elif format_type == "cta":
            parsed = parse_cta_response(raw_text)
            final_text = parsed.get("post", raw_text)
            final_text, word_count = verify_and_retry(final_text, config, retry_system_prompt, model=model, api_key=api_key, base_url=base_url)
            
            res_data = {
                "type": "cta",
                "content": parsed.get("resource", ""),
                "trigger_word": parsed.get("trigger_word", "")
            }
            (content_dir / "resource.json").write_text(json.dumps(res_data, indent=2, ensure_ascii=False), encoding="utf-8")
            meta_trigger = parsed.get("trigger_word", "")
        else:
            final_text, word_count = verify_and_retry(raw_text, config, retry_system_prompt, model=model, api_key=api_key, base_url=base_url)
            meta_trigger = ""
            
        if config.get("humanize_pass") and format_type != "formation":
            logger.info("Application de la passe d'humanisation...")
            humanize_sys = "Tu es un expert en réécriture. Ton but est de rendre le texte suivant plus humain, direct et sans tics d'IA. Supprime les répétitions, les structures trop parfaites et le jargon inutile. Garde le même sens et la même longueur."
            final_text = humanize_pass(final_text, humanize_sys, model=model, api_key=api_key, base_url=base_url)
            
        final_text = clean_for_facebook(final_text)
        
        if format_type != "formation":
            final_text = _break_long_paragraphs(final_text)
            final_text = _add_stickers(final_text)
        
        if format_type == "formation":
            final_text = post_process_formation_text(final_text)
        
        signature = config.get("signature") or ""
        # Vérification très souple : on ignore les hashtags, sauts de ligne et espaces
        sig_norm = re.sub(r'[^a-zA-Z0-9]', '', signature).upper()
        text_norm = re.sub(r'[^a-zA-Z0-9]', '', final_text).upper()
        
        if signature and sig_norm not in text_norm:
            final_text += f"\n\n{signature}"
        
        # Créer le fichier selon la plateforme
        if platform == "linkedin":
            # LinkedIn: limiter à 4000 caractères
            linkedin_text = final_text[:4000] if len(final_text) > 4000 else final_text
            (content_dir / "linkedin_post.txt").write_text(linkedin_text, encoding="utf-8")
        elif platform == "twitter":
            # Twitter: limiter à 280 caractères
            twitter_text = final_text[:280] if len(final_text) > 280 else final_text
            (content_dir / "tweet_post.txt").write_text(twitter_text, encoding="utf-8")
        else:
            # Facebook
            (content_dir / "facebook_post.txt").write_text(final_text, encoding="utf-8")
        
        # Gestion des commentaires
        if format_type == "formation":
            # Format formation: 2 commentaires fixes
            lessons = _extract_formation_lessons(final_text)
            lessons_text = "\n\n".join([f"● {l}" for l in lessons])
            
            comment2 = f"Tu as appris à :\n\n{lessons_text}" if lessons else "Tu as appris à suivre cette formation complète."
            comment1 = "Je t'offre une formation complète pour devenir expert en utilisation de l'IA dans ton domaine. Rejoins la communauté pour recevoir l'intégralité en inbox."
            
            # Ordre de publication: commentaire 1 en premier (haut) puis commentaire 2 (bas)
            comments = [
                {"number": 1, "content": comment1},
                {"number": 2, "content": comment2}
            ]
            (content_dir / "trigger_comments.json").write_text(json.dumps(comments, indent=2, ensure_ascii=False), encoding="utf-8")
            
        elif format_type in ("court", "trigger"):
            if format_type == "trigger":
                # Le format trigger génère plusieurs commentaires numérotés
                sys_comment = """Tu es Jean-Marc DANSI. Reçois ce post trigger et génère les commentaires de développement.
Chaque commentaire doit être numéroté (1., 2., 3., etc.) et apporter une information concrète, technique et actionnable.
DÉVELOPPE CHAQUE POINT : Chaque commentaire doit faire au moins 3 à 5 phrases détaillées.
Ne fais JAMAIS de liste de titres. Je veux de la substance technique.
Suis exactement le style "Value Loop" : punchy, technique, utile.
Maximum 10 commentaires. Chaque commentaire: 80-150 mots.
Retourne uniquement les commentaires au format:
1. Texte long et détaillé du premier point expliquant le quoi, le comment et le résultat.
2. Texte long et détaillé du deuxième point avec des conseils précis.
..."""
                usr_comment = f"Post:\n{final_text}\n\nGénère les commentaires de développement."
            else:
                # Format court : un seul commentaire épinglé de 300 mots
                sys_comment = "Tu es Jean-Marc DANSI. Reçois ce post court et rédige le commentaire épinglé (300 mots) plein de détails actionnables qui le complète. Pas de markdown."
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
        
        final_meta = {}
        if (content_dir / "meta.json").exists():
            try:
                final_meta = json.loads((content_dir / "meta.json").read_text(encoding="utf-8"))
            except Exception:
                pass
                
        final_meta.update({
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
        })
        if meta_trigger:
            final_meta["trigger_word"] = meta_trigger
            
        (content_dir / "meta.json").write_text(json.dumps(final_meta, indent=2, ensure_ascii=False), encoding="utf-8")
        
        update_task(task_id, progress=100, status="completed", message="Génération terminée avec succès", log="Terminé!")
        
        return AgentResult.ok(final_meta)
        
    except Exception as e:
        logger.exception("Erreur Copywriter")
        if task_id:
            update_task(task_id, status="failed", message=str(e))
        return AgentResult.fail(str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Copywriter Agent")
    parser.add_argument("--persona", type=str, required=True, help="Persona name")
    parser.add_argument("--folder", type=str, required=True, help="Output folder")
    parser.add_argument("--topic", type=str, help="Topic for the post", default="Opportunités du digital en Afrique")
    
    parser.add_argument("--audience", type=str, help="Target audience", default="tous")
    parser.add_argument("--context", type=str, help="Additional context", default="")
    
    args = parser.parse_args()
    
    plan_entry = {
        "persona": args.persona,
        "sujet": args.topic,
        "audience": args.audience,
        "context": args.context or "Génération de test pour validation de qualité"
    }
    
    res = run_copywriter(args.folder, plan_entry)
    if res.success:
        print(f"SUCCÈS: Post généré dans {args.folder}")
        print(f"Fichier: {Path(args.folder) / 'facebook_post.txt'}")
    else:
        print(f"ERREUR: {res.error_cause}")
