import io
import json
import sys
from pathlib import Path
from datetime import datetime

# Setup sys.path to resolve from project root
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT_DIR / "machines" / "facebook_machine"))
sys.path.insert(0, str(_ROOT_DIR))

from core.models import AgentResult
from core.config import Config
from core.logger import get_node_logger
from core.groq_router import MODEL_POSTS, call_groq

logger = get_node_logger("topic_finder")
GROQ_MODEL = MODEL_POSTS


def get_active_personas(account_id: int = None, platform: str = "facebook") -> list:
    """Retourne la liste des personas actifs (dossiers dans persona/)."""
    platform_dir = _ROOT_DIR / "machines" / f"{platform}_machine"
    if account_id:
        personas_dir = platform_dir / "accounts" / str(account_id) / "persona"
    else:
        personas_dir = platform_dir / "persona"
        
    skip = {"_shared", "_archives", "all.txt"}
    if not personas_dir.exists():
        return []
    return sorted([d.name for d in personas_dir.iterdir() if d.is_dir() and d.name not in skip])


def _load_brand_context(platform: str = "facebook") -> str:
    parts = []
    platform_dir = _ROOT_DIR / "machines" / f"{platform}_machine"
    for fname, label in [
        ("objectives.md", "OBJECTIFS & AUDIENCES"),
        ("accroches.md",  "ACCROCHES (patterns)"),
    ]:
        fpath = platform_dir / "persona" / "_shared" / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8")
            truncated = io.StringIO(content).read(2000)
            parts.append("=== " + label + " ===\n" + truncated)
    return "\n\n".join(parts) + "\n\n" if parts else ""


def get_recent_topics(days: int = 30, platform: str = "facebook", account_id: int = None) -> list:
    """Retourne les sujets des posts créés dans les N derniers jours pour le compte/plateforme spécifié."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    
    platform_dir = _ROOT_DIR / "machines" / f"{platform}_machine"
    if account_id:
        content_dir = platform_dir / "accounts" / str(account_id) / "content"
    else:
        content_dir = platform_dir / "content"
        
    if not content_dir.exists():
        return recent

    # Check meta.json
    for meta_file in sorted(content_dir.glob("*/meta.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            created = meta.get("created_at", "")
            if not created:
                continue
            dt = datetime.fromisoformat(created)
            if dt < cutoff:
                continue
            topic = meta.get("topic", "")
            if isinstance(topic, dict):
                topic = topic.get("sujet", str(topic))
            recent.append({
                "topic": str(topic),
                "persona": meta.get("persona", ""),
                "date": created[:10],
            })
        except Exception:
            continue
            
    # Check metadata.json
    for metadata_file in sorted(content_dir.glob("*/metadata.json")):
        if (metadata_file.parent / "meta.json").exists():
            continue
        try:
            meta = json.loads(metadata_file.read_text(encoding="utf-8"))
            created = meta.get("created_at", "")
            if not created:
                continue
            dt = datetime.fromisoformat(created)
            if dt < cutoff:
                continue
            topic = meta.get("topic", "")
            if isinstance(topic, dict):
                topic = topic.get("sujet", str(topic))
            recent.append({
                "topic": str(topic),
                "persona": meta.get("persona", ""),
                "date": created[:10],
            })
        except Exception:
            continue
            
    return recent


def format_recent_for_planner(days: int = 30, platform: str = "facebook", account_id: int = None) -> str:
    recent = get_recent_topics(days, platform, account_id)
    if not recent:
        return ""
    lines = [f"SUJETS DÉJÀ TRAITÉS (derniers {days} jours — NE PAS répéter) :"]
    for r in recent[-40:]:
        lines.append(f"- [{r['date']}] {r['persona']} : {r['topic'][:80]}")
    return "\n".join(lines)


def generate_daily_plan(date: str = None, force: bool = False, account_id: int = None, platform: str = "facebook") -> AgentResult:
    """Génère (ou charge) le plan du jour pour un compte spécifique et une plateforme spécifique."""
    try:
        ok, msg = Config.validate_node_deps("topic_finder", ["GROQ_API_KEY"])
        if not ok:
            return AgentResult.fail(msg)

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        platform_dir = _ROOT_DIR / "machines" / f"{platform}_machine"
        if account_id:
            plans_dir = platform_dir / "accounts" / str(account_id) / "content" / "plans"
        else:
            plans_dir = platform_dir / "content" / "plans"
            
        plans_dir.mkdir(parents=True, exist_ok=True)
        acc_prefix = f"{account_id}_" if account_id else ""
        plan_file = plans_dir / f"{date}_{acc_prefix}plan.json"

        if plan_file.exists() and not force:
            logger.info(f"Plan du {date} pour {platform} account {account_id} déjà généré — chargement.")
            data = json.loads(plan_file.read_text(encoding="utf-8"))
            return AgentResult.ok(data)

        logger.info(f"Génération du plan pour le {date} (Plateforme: {platform}, Account: {account_id})")
        
        # 1. Tenter de charger les sujets planifiés depuis planned_topics.json
        if account_id:
            acc_dir = platform_dir / "accounts" / str(account_id)
        else:
            acc_dir = platform_dir

        planned_file = acc_dir / "planned_topics.json"
        planned_topics = []
        if planned_file.exists():
            try:
                raw = json.loads(planned_file.read_text(encoding="utf-8"))
                if "version" in raw and "topics" in raw:
                    planned_topics = raw.get("topics", [])
                else:
                    for p_key, items in raw.items():
                        if isinstance(items, list):
                            for t in items:
                                t.setdefault("persona", p_key)
                            planned_topics.extend(items)
            except Exception as e:
                logger.warning(f"Failed to load planned topics: {e}")

        personas = get_active_personas(account_id, platform)
        if not personas:
            return AgentResult.fail(f"Aucun persona configuré pour le compte {account_id} ({platform}).")

        # 2. Construire le plan en piochant UNIQUEMENT dans les sujets planifiés validés
        final_posts = []
        reels = []

        for p_name in personas:
            target_topic = None
            target_idx = None

            # D'abord chercher un topic planifié pour aujourd'hui
            for i, t in enumerate(planned_topics):
                if t.get("persona") == p_name and t.get("validated", False) and not t.get("used", False):
                    topic_date = (t.get("date") or "")[:10]
                    if topic_date == date:
                        target_topic = t
                        target_idx = i
                        break

            # Fallback: prendre le premier topic validé non utilisé pour ce persona
            if not target_topic:
                for i, t in enumerate(planned_topics):
                    if t.get("persona") == p_name and t.get("validated", False) and not t.get("used", False):
                        target_topic = t
                        target_idx = i
                        break

            if target_topic:
                logger.info(f"Utilisation d'un sujet planifié validé pour {p_name}: {target_topic.get('topic', '')}")
                topic_date = target_topic.get("date", date)
                topic_time = target_topic.get("time", "")
                date_prevue = target_topic.get("date_prevue", "")
                if not date_prevue and topic_date:
                    time_str = topic_time if topic_time else "12:00"
                    date_prevue = f"{topic_date[:10]}T{time_str}:00"

                plan_entry = {
                    "persona": p_name,
                    "topic": target_topic.get("topic", ""),
                    "context": target_topic.get("context", ""),
                    "date": topic_date,
                    "time": topic_time,
                    "date_prevue": date_prevue,
                }

                if target_topic.get("media") == "reel" or p_name == "reel":
                    reels.append(plan_entry)
                else:
                    final_posts.append(plan_entry)

                planned_topics[target_idx]["used"] = True
                planned_topics[target_idx]["used_at"] = datetime.now().isoformat()
            else:
                logger.info(f"Aucun sujet planifié validé disponible pour {p_name}.")

        # 3. No Fallback: Only use planned and validated topics
        plan_data = {
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "posts": final_posts,
            "reels": reels
        }

        # Sauvegarder les changements dans planned_topics.json
        if planned_topics:
            save_data = {"version": "1.0", "topics": planned_topics}
            planned_file.write_text(json.dumps(save_data, indent=2, ensure_ascii=False), encoding="utf-8")

        plan_file.write_text(json.dumps(plan_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Plan sauvegardé : {plan_file.name}")
        return AgentResult.ok(plan_data)
        
    except Exception as e:
        logger.exception("Erreur inattendue dans topic_finder")
        return AgentResult.fail(str(e))


def suggest_persona_topics(persona: str, count: int = 10, account_id: int = None, platform: str = "facebook", angle: str = None) -> AgentResult:
    """Suggère une liste de sujets pour un persona spécifique pour la plateforme et le compte donnés."""
    try:
        ok, msg = Config.validate_node_deps("topic_finder", ["GROQ_API_KEY"])
        if not ok:
            return AgentResult.fail(msg)

        # Charger le contexte du persona
        platform_dir = _ROOT_DIR / "machines" / f"{platform}_machine"
        if account_id:
            personas_dir = platform_dir / "accounts" / str(account_id) / "persona"
        else:
            personas_dir = platform_dir / "persona"
        
        p_dir = personas_dir / persona
        if not p_dir.exists():
            return AgentResult.fail(f"Persona '{persona}' introuvable dans {p_dir}.")

        prompt_file = p_dir / "system_prompt.md"
        system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""
        
        examples_file = p_dir / "examples.md"
        examples = examples_file.read_text(encoding="utf-8") if examples_file.exists() else ""

        brand_ctx = _load_brand_context(platform)

        # Read format.json if it exists to get variables_requises
        format_file = p_dir / "format.json"
        variables_requises = []
        if format_file.exists():
            try:
                format_data = json.loads(format_file.read_text(encoding="utf-8"))
                variables_requises = format_data.get("variables_requises", [])
            except Exception as e:
                logger.warning(f"Could not load format.json for persona {persona}: {e}")

        # Construct the variables instructions dynamically
        variables_instr = ""
        variables_json_structure = ""
        if variables_requises:
            variables_instr = f"\nATTENTION CRITIQUE : Ton rôle est UNIQUEMENT de remplir les variables suivantes définies dans le format.json de ce persona : {', '.join(variables_requises)}. Tu ne dois EN AUCUN CAS rédiger le post complet. Ces variables servent de plan et c'est tout ce qui importe.\n"
            variables_json_structure = ",\n      \"variables\": {\n" + ",\n".join([f"        \"{v}\": \"valeur ou idée concise pour définir la variable {v}\"" for v in variables_requises]) + "\n      }"

        angle_instr = f"\nANGLE DE LA SEMAINE / THÈME OBLIGATOIRE :\n{angle}\nTous les sujets suggérés doivent s'inscrire ou s'inspirer de cet angle d'attaque.\n" if angle else ""

        prompt = f"""Tu es un expert en stratégie de contenu pour {platform.upper()}.
Ton but est d'ÉTABLIR LE PLAN de {count} sujets pour le persona "{persona}". TU NE DOIS PAS RÉDIGER LES POSTS EUX-MÊMES !
{angle_instr}
CONTEXTE DE LA MARQUE :
{brand_ctx}

PROFIL DU PERSONA :
{system_prompt}

EXEMPLES DE STYLE :
{examples}

RÈGLES POUR LES SUJETS :
1. NE RÉDIGE PAS LE POST : Fournis uniquement des idées et concepts pour guider le rédacteur.
2. TITRE ULTRA-COURT : Le champ "topic" DOIT être une étiquette de 3 à 6 mots maximum.
3. CONTEXTE BREF : Le champ "context" doit être une seule phrase courte expliquant l'angle.
4. PRÉCISION : Les variables doivent contenir des concepts concrets (chiffres, noms, situations réelles) et non des généralités.{variables_instr}

RÉPONDS UNIQUEMENT avec du JSON valide, sans markdown, au format suivant :
{{
  "topics": [
    {{
      "topic": "Étiquette ultra-courte (max 6 mots)",
      "context": "Une seule phrase courte expliquant l'angle",
      "objectif": "engagement | autorite | notoriete"{variables_json_structure}
    }}
  ]
}}"""

        logger.info(f"[TOPIC_FINDER] Suggestion de {count} sujets pour {persona} ({platform}, account {account_id}) via Groq...")
        raw = call_groq(prompt, model=GROQ_MODEL, temperature=0.8, max_tokens=2500)
        
        if raw is None:
            return AgentResult.fail("Erreur Groq.")

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return AgentResult.ok(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Groq: {raw[:200]}")
            return AgentResult.fail(f"Erreur JSON: {str(e)}")

    except Exception as e:
        logger.exception(f"Erreur dans suggest_persona_topics: {e}")
        return AgentResult.fail(str(e))
