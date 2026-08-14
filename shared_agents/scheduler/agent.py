# agent.py — Orchestrateur / Pipeline principal partagé
import sys
import io
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (ValueError, AttributeError):
        pass
import logging
import json
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from shared_agents.models import AgentResult
from core.config import Config
from core.logger import get_node_logger
from lib.content_io import atomic_write_json

logger = get_node_logger("scheduler")

PLATFORM_BASES = {
    "facebook": Path("d:/Content_Machine/machines/facebook_machine"),
    "linkedin": Path("d:/Content_Machine/machines/linkedin_machine"),
    "twitter": Path("d:/Content_Machine/machines/twitter_machine"),
    "instagram": Path("d:/Content_Machine/machines/facebook_machine"),
}


def _make_bar(current: int, total: int, width: int = 30) -> str:
    filled = int(width * current / total) if total > 0 else 0
    bar = "|" + "/" * filled + "." * (width - filled - 1)
    return f"[{bar}]"


def _update_progress(task_id: str, current: int, total: int, step: str, log_msg: str = None):
    if not task_id:
        return
    progress = int((current / total) * 100)
    msg = f"{step} ({current}/{total})"
    if log_msg:
        msg += f" -- {log_msg}"
    from core.task_tracker import update_task
    update_task(task_id, progress=progress, status="running", message=msg, log=log_msg)
    bar = _make_bar(current, total)
    logger.info(f"[{current}/{total}] {bar} {progress}% -- {step}")


def _get_account_llm_model(platform: str, account_id) -> str:
    if not account_id:
        return Config.DEFAULT_LLM_MODEL
    db_path = Path(f"d:/Content_Machine/machines/{platform}_machine/data/leads_station.db")
    if not db_path.exists():
        return Config.DEFAULT_LLM_MODEL
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT settings FROM accounts WHERE id=?", (account_id,))
        row = cursor.fetchone()
        if row and row["settings"]:
            try:
                settings = json.loads(row["settings"])
                if settings.get("llm_model"):
                    return settings.get("llm_model")
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if platform == "linkedin":
        return getattr(Config, "LINKEDIN_LLM_MODEL", None) or Config.DEFAULT_LLM_MODEL
    if platform == "twitter":
        return getattr(Config, "TWITTER_LLM_MODEL", None) or Config.DEFAULT_LLM_MODEL
    return getattr(Config, "FACEBOOK_LLM_MODEL", None) or Config.DEFAULT_LLM_MODEL


def _get_account_llm_config(platform: str, account_id) -> dict:
    """Retourne la config LLM du compte : {model, api_key, base_url}.

    Priorité : settings du compte (llm_model/llm_api_key/llm_base_url) ->
    modèle par défaut global (settings.json) -> Config.DEFAULT_LLM_MODEL.
    La clé API / base_url du compte prennent le dessus sur les valeurs .env
    (gérées en interne par core.llm_router en fallback)."""
    try:
        from core.llm_router import get_account_llm_config as _acc_cfg, get_default_model
    except Exception:
        _acc_cfg = None
        get_default_model = None
    config = {"model": None, "api_key": None, "base_url": None}
    if _acc_cfg:
        config.update(_acc_cfg(platform, account_id) or {})
    if not config["model"]:
        if get_default_model:
            try:
                config["model"] = get_default_model()
            except Exception:
                config["model"] = Config.DEFAULT_LLM_MODEL
        else:
            config["model"] = Config.DEFAULT_LLM_MODEL
    return config


def _resolve_folder(platform: str, account_id, content_id: str, date: str, persona: str) -> Path:
    base_dir = PLATFORM_BASES.get(platform, Config.BASE_DIR)
    if account_id:
        return base_dir / "accounts" / str(account_id) / "content" / content_id
    return Config.CONTENT_DIR / f"{date}_{persona}"


def _run_publisher(platform: str, folder_path, account_id=None):
    """Route vers le bon publisher selon la plateforme."""
    if platform == "linkedin":
        from machines.linkedin_machine.agents.agent_publisher import post_linkedin
        result = post_linkedin(str(folder_path), account_id=account_id)
        if bool(result):
            return AgentResult.ok()
        return AgentResult.fail("Publication LinkedIn échouée")
    elif platform == "twitter":
        from machines.twitter_machine.agents.agent_publisher import post_twitter
        result = post_twitter(str(folder_path), account_id=account_id)
        if bool(result):
            return AgentResult.ok()
        return AgentResult.fail("Publication Twitter échouée")
    else:
        from machines.facebook_machine.agents.publisher.agent import run_publisher
        return run_publisher(str(folder_path), account_id=account_id)


def process_single_post(plan_entry: dict, date: str, publish: bool, task_id: str = None,
                        current: int = 0, total: int = 1, account_id=None,
                        platform: str = "facebook", folder_path: str = None) -> AgentResult:
    """Traite un post standard (texte + image potentielle)."""
    persona = plan_entry.get("persona", "expert_ia")
    content_id = str(uuid.uuid4())

    # ── ROUTAGE LINKEDIN ──────────────────────────────────────────
    if platform == "linkedin":
        _update_progress(task_id, current, total, f"[TXT] {persona}", "Rédaction LinkedIn...")

        # Construire le topic pour write_linkedin_post
        topic_for_writer = {
            "titre": plan_entry.get("topic") or plan_entry.get("sujet", ""),
            "angle": plan_entry.get("context", ""),
            "format_id": plan_entry.get("persona", "poste_routine"),
            "variables": plan_entry.get("variables", {}),
        }

        if folder_path:
            target_folder = folder_path
        else:
            target_folder = str(_resolve_folder(platform, account_id, content_id, date, persona))

        try:
            li_machine = str(PLATFORM_BASES.get("linkedin", ROOT_DIR / "machines" / "linkedin_machine"))
            if li_machine not in sys.path:
                sys.path.insert(0, li_machine)
            from agents.agent_writer import write_linkedin_post
            result_folder = write_linkedin_post(
                topic_for_writer,
                account_id=account_id,
                folder_path=target_folder,
            )
            if not result_folder:
                return AgentResult.fail(f"LinkedIn writer a retourné None pour {persona}")

            folder_path = Path(result_folder)

            # ── IMAGE GENERATION ──
            image_success = True
            if Config.POST_IMAGE_ENABLED:
                _update_progress(task_id, current, total, f"[IMG] {persona}", "Génération image LinkedIn...")
                try:
                    from machines.facebook_machine.agents.image_creator.agent import run_image_creator
                    img_res = run_image_creator(str(folder_path), platform="linkedin", account_id=account_id)
                    if not img_res.success:
                        logger.warning(f"Echec Image Creator (non-bloquant) LinkedIn pour {persona}: {getattr(img_res, 'error_cause', 'Erreur')}")
                        image_success = False
                    else:
                        logger.info(f"Image Creator terminé pour LinkedIn {persona}.")
                except Exception as img_err:
                    logger.warning(f"Image Creator exception LinkedIn pour {persona}: {img_err}")
                    image_success = False

            # Publication si demandée
            if publish:
                _update_progress(task_id, current, total, f"[PUB] {persona}", "Publication LinkedIn...")
                pub_res = _run_publisher(platform, folder_path, account_id)
                if not pub_res.success:
                    logger.error(f"Echec Publisher LinkedIn pour {persona}: {pub_res.error_cause}")
                    return pub_res
                logger.info(f"Publisher LinkedIn terminé pour {persona}")

            return AgentResult.ok({
                "folder": folder_path,
                "published": publish,
                "image_success": image_success,
            })

        except Exception as e:
            logger.exception(f"Erreur pipeline LinkedIn pour {persona}: {e}")
            return AgentResult.fail(str(e))

    # ── ROUTAGE FACEBOOK / AUTRES ─────────────────────────────────
    if folder_path:
        folder_path = Path(folder_path)
    else:
        folder_path = _resolve_folder(platform, account_id, content_id, date, persona)
        folder_path.mkdir(parents=True, exist_ok=True)

        meta_data = {
            "content_id": content_id,
            "account_id": account_id,
            "platform": platform,
            "persona": persona,
            "topic": plan_entry.get("topic") or plan_entry.get("sujet", ""),
            "status": "written",
            "created_at": datetime.now().isoformat(),
            "folder_path": str(folder_path),
            "scheduled_time": plan_entry.get("scheduled_time", "")
                              or plan_entry.get("date_prevue", ""),
        }
        atomic_write_json(folder_path / "meta.json", meta_data)

        if account_id:
            try:
                from lib.db_utils import init_db, insert_content
                db_path = Path("d:/Content_Machine/data/content_machine.db")
                conn = init_db(str(db_path))
                insert_content(conn, content_id, account_id, platform, "folder",
                               str(folder_path), meta_data, "written")
                conn.close()
            except Exception as e:
                logger.error(f"Error saving content DB: {e}")

    _update_progress(task_id, current, total, f"[INIT] {persona}", "Analyse du persona...")

    # Détection Visual-First
    is_photography = False
    platform_base = PLATFORM_BASES.get(platform, Path("d:/Content_Machine/machines/facebook_machine"))
    config_path = platform_base / "accounts" / str(account_id or "2") / "persona" / persona / "config.md"
    if config_path.exists() and "Type: photography" in config_path.read_text(encoding="utf-8"):
        is_photography = True

    if is_photography:
        logger.info(f"Routage VISUAL-FIRST activé pour le persona {persona}")
        _update_progress(task_id, current, total, f"[IMG] {persona}", "Shooting photo IA en cours...")
        from shared_agents.photographer.agent import run_photographer
        photographer_res = run_photographer(str(folder_path))
        if not photographer_res.success:
            logger.error(f"Echec Photographer pour {persona}: {getattr(photographer_res, 'error_cause', 'Erreur')}")
            return photographer_res
        post_path = folder_path / f"{platform}_post.txt"
        post_path.write_text(f"📸 Visuel généré avec le style: {persona}. Prêt pour validation.", encoding="utf-8")
        image_success = True
        logger.info(f"Photographer terminé pour {persona}.")
    else:
        _update_progress(task_id, current, total, f"[TXT] {persona}", "Rédaction en cours...")
        from agents.copywriter.agent import run_copywriter
        llm_cfg = _get_account_llm_config(platform, account_id)
        copywriter_res = run_copywriter(
            str(folder_path), plan_entry,
            task_id=task_id, account_id=account_id,
            platform=platform, model=llm_cfg.get("model"), llm_config=llm_cfg,
        )
        if not copywriter_res.success:
            logger.error(f"Echec Copywriter pour {persona}: {getattr(copywriter_res, 'error_cause', 'Erreur')}")
            return copywriter_res
        logger.info(f"Copywriter terminé pour {persona}.")

        image_success = True
        if Config.POST_IMAGE_ENABLED:
            _update_progress(task_id, current, total, f"[IMG] {persona}", "Génération image...")
            from agents.image_creator.agent import run_image_creator
            img_res = run_image_creator(str(folder_path))
            if not img_res.success:
                logger.warning(f"Echec Image Creator (non-bloquant) pour {persona}: {getattr(img_res, 'error_cause', 'Erreur')}")
                image_success = False
            else:
                logger.info(f"Image Creator terminé pour {persona}.")

    if publish:
        _update_progress(task_id, current, total, f"[PUB] {persona}", "Publication...")
        pub_res = _run_publisher(platform, folder_path, account_id)
        if not pub_res.success:
            logger.error(f"Echec Publisher pour {persona}: {getattr(pub_res, 'error_cause', 'Erreur')}")
            return pub_res
        logger.info(f"Publisher terminé pour {persona}: {pub_res.data}")

    return AgentResult.ok({"folder": folder_path, "published": publish, "image_success": image_success})


def process_reel(reel_entry: dict, date: str, publish: bool, task_id: str = None,
                 current: int = 0, total: int = 1, account_id=None,
                 platform: str = "facebook") -> AgentResult:
    """Traite la génération d'un reel."""
    persona = reel_entry.get("persona", "reel")
    content_id = str(uuid.uuid4())

    folder_path = _resolve_folder(platform, account_id, content_id, date, persona)
    folder_path.mkdir(parents=True, exist_ok=True)

    if account_id:
        try:
            from core.db import SessionLocal, Post
            db = SessionLocal()
            folder_name = folder_path.name
            if not db.query(Post).filter(Post.folder_name == folder_name).first():
                post = Post(account_id=account_id, folder_name=folder_name, persona=persona,
                            topic=reel_entry.get("topic") or reel_entry.get("sujet", ""), status="pending", has_reel=True)
                db.add(post)
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Error saving Post DB: {e}")

    _update_progress(task_id, current, total, f"[REEL] {persona}", "Génération vidéo...")

    brief_content = f"SUJET: {reel_entry.get('topic') or reel_entry.get('sujet', '')}\nPERSONA: {persona}\nCONTEXT: {reel_entry.get('context', '')}"
    (folder_path / "reel_brief.txt").write_text(brief_content, encoding="utf-8")

    post_content = f"Reel: {reel_entry.get('topic') or reel_entry.get('sujet', '')}"
    (folder_path / "facebook_post.txt").write_text(post_content, encoding="utf-8")

    meta = {
        "persona": persona,
        "topic": reel_entry.get("topic") or reel_entry.get("sujet", ""),
        "created_at": datetime.now().isoformat(),
        "status": "pending",
        "has_reel": True,
        "published": False,
    }
    (folder_path / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    from shared_agents.video_maker.agent import run_video_maker

    reel_res = run_video_maker(str(folder_path))
    if not reel_res.success:
        logger.error(f"Echec Reel Maker pour {folder_path.name}: {getattr(reel_res, 'error_cause', 'Erreur')}")
        meta["image_failed"] = True
        (folder_path / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return reel_res

    logger.info(f"Reel Maker terminé pour {folder_path.name}.")

    if publish:
        _update_progress(task_id, current, total, f"[PUB] Reel {persona}", "Publication...")
        pub_res = _run_publisher(platform, folder_path, account_id)
        if not pub_res.success:
            logger.error(f"Echec Publisher pour Reel: {getattr(pub_res, 'error_cause', 'Erreur')}")
            return pub_res

    if task_id:
        from core.task_tracker import update_task
        update_task(task_id, progress=100, status="completed",
                    message="Génération du reel terminée avec succès", log="Terminé!")

    return AgentResult.ok({"folder": str(folder_path), "published": publish})


def _run_pipeline_for_account(account_id, platform: str, post_type: str, publish: bool,
                              date: str, task_id: str) -> AgentResult:
    logger.info("=" * 50)
    logger.info(f">>> PIPELINE BATCH -- {date} -- ACCOUNT {account_id} ({platform})")
    logger.info("=" * 50)

    from shared_agents.topic_finder.agent import generate_daily_plan
    topic_res = generate_daily_plan(date=date, force=False, account_id=account_id, platform=platform)
    if not topic_res.success:
        logger.error(f"Echec Topic Finder: {getattr(topic_res, 'error_cause', 'Erreur')}")
        return topic_res

    plan_data = topic_res.data
    posts = plan_data.get("posts", [])
    reels = plan_data.get("reels", [])

    logger.info(f"Plan chargé : {len(posts)} posts + {len(reels)} reels")

    all_items = posts + reels
    total_items = len(all_items)

    generated_folders = []
    success_count = 0
    fail_count = 0
    consecutive_image_fails = 0

    if post_type == "all" or not post_type:
        for idx, p in enumerate(posts):
            res = process_single_post(p, date, publish, task_id, idx + 1, total_items, account_id, platform)
            if res.success:
                generated_folders.append(res.data.get("folder"))
                success_count += 1
                if res.data.get("image_success"):
                    consecutive_image_fails = 0
                else:
                    consecutive_image_fails += 1
                if consecutive_image_fails >= 3:
                    msg = "ARRÊT CRITIQUE : 3 échecs images consécutifs. Vérifiez Chrome/Gemini."
                    logger.error(msg)
                    _update_progress(task_id, idx + 1, total_items, "STOP", msg)
                    return AgentResult.fail(msg)
                logger.info(f"Post terminé: {p.get('persona', 'unknown')} ({idx + 1}/{total_items})")
            else:
                fail_count += 1
                logger.warning(f"Post échoué: {p.get('persona', 'unknown')} ({idx + 1}/{total_items})")

            if idx < len(posts) - 1 or reels:
                delay = 70
                logger.info(f"Pause {delay}s avant le prochain post...")
                time.sleep(delay)

        for idx, r in enumerate(reels):
            res = process_reel(r, date, publish, task_id, len(posts) + idx + 1, total_items, account_id, platform)
            if res.success:
                generated_folders.append(res.data.get("folder"))
                success_count += 1
                logger.info(f"Reel terminé: {r.get('persona', 'reel')}")
            else:
                fail_count += 1
                logger.warning("Reel échoué")
            if idx < len(reels) - 1:
                delay = getattr(Config, "BATCH_MIN_DELAY_SECONDS", 70)
                logger.info(f"Pause {delay}s avant le reel suivant...")
                time.sleep(delay)

    elif post_type == "reel":
        if reels:
            res = process_reel(reels[0], date, publish, task_id, 1, 1, account_id, platform)
            if res.success:
                generated_folders.append(res.data.get("folder"))
        else:
            return AgentResult.fail("Aucun reel trouvé dans le plan du jour.")
    else:
        target = None
        for p in posts:
            if p.get("persona") == post_type:
                target = p
                break
        if target:
            res = process_single_post(target, date, publish, task_id, 1, 1, account_id, platform)
            if res.success:
                generated_folders.append(res.data.get("folder"))
        else:
            logger.warning(f"Persona '{post_type}' introuvable dans le plan.")
            return AgentResult.fail(f"Persona '{post_type}' non trouvé dans le plan du jour.")

    logger.info("=" * 50)
    logger.info(f">>> PIPELINE TERMINÉ -- Succès: {success_count}/{total_items}")
    if fail_count > 0:
        logger.warning(f"Échecs: {fail_count}/{total_items}")
    logger.info("=" * 50)

    return AgentResult.ok({
        "folders": generated_folders,
        "published": publish,
        "success": success_count,
        "total": total_items,
    })


def run_pipeline(post_type: str = "all", publish: bool = False,
                 date: str = None, task_id: str = None) -> AgentResult:
    """Exécute l'intégralité du pipeline pour tous les comptes actifs."""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    try:
        from core.db import SessionLocal, Account
        db = SessionLocal()
        accounts = db.query(Account).filter(Account.status == "active").all()
        db.close()
    except Exception as e:
        logger.error(f"Error fetching accounts for pipeline: {e}")
        accounts = []

    if not accounts:
        logger.info("Aucun compte en base, fallback sur l'exécution standard")
        return _run_pipeline_for_account(None, "facebook", post_type, publish, date, task_id)

    overall_res = {"folders": [], "success": 0, "total": 0, "published": publish}
    for acc in accounts:
        if acc.settings and not acc.settings.get("scheduler_active", False):
            logger.info(f"Scheduler désactivé pour le compte {acc.id} ({acc.platform}).")
            continue
        res = _run_pipeline_for_account(acc.id, acc.platform, post_type, publish, date, task_id)
        if res.success:
            overall_res["folders"].extend(res.data.get("folders", []))
            overall_res["success"] += res.data.get("success", 0)
            overall_res["total"] += res.data.get("total", 0)

    return AgentResult.ok(overall_res)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", default="all", help="all, reel ou le nom d'un persona")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()

    res = run_pipeline(post_type=args.type, publish=not args.no_publish, date=args.date)
    if res.success:
        print(f"\n[OK] Pipeline terminé: {res.data.get('folders', [])}")
    else:
        print(f"\n[ERREUR] Pipeline échec: {getattr(res, 'error_cause', 'Erreur inconnue')}")
