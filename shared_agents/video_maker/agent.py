import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Dossier video_maker en priorité haute pour que 'engine' soit trouvé en premier
_VIDEO_MAKER_DIR = Path(__file__).resolve().parent
if str(_VIDEO_MAKER_DIR) not in sys.path:
    sys.path.insert(0, str(_VIDEO_MAKER_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from core.models import AgentResult
from core.logger import get_node_logger

logger = get_node_logger("video_maker")


def read_reel_brief(post_path: Path) -> dict | None:
    """Lit reel_brief.txt s'il existe. Robuste face aux encodages Windows (cp1252/utf-8)."""
    brief_file = post_path / "reel_brief.txt"
    if not brief_file.exists():
        return None

    # Essayer UTF-8 puis cp1252 pour compatibilité Windows
    content = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            content = brief_file.read_text(encoding=enc)
            break
        except Exception:
            continue
    if not content:
        return None

    sujet, persona, context = "", "", ""
    for line in content.splitlines():          # splitlines() gère \r\n et \n
        line = line.strip()
        if line.startswith("SUJET:"):
            sujet = line[6:].strip()
        elif line.startswith("PERSONA:"):
            persona = line[8:].strip()
        elif line.startswith("CONTEXT:"):
            context = line[8:].strip()

    if not sujet:
        return None

    # Fallback persona depuis meta.json si absent du brief
    if not persona:
        meta_file = post_path / "meta.json"
        if meta_file.exists():
            try:
                import json as _json
                meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                persona = meta.get("persona", "")
            except Exception:
                pass

    return {"sujet": sujet, "persona": persona, "context": context}


def run_video_maker(folder_path: str, task_id: str = None) -> AgentResult:
    """
    Génère une vidéo Reel à partir d'un post existant ou d'un brief.
    Délègue au Cinema Engine (engine/scene_director.py).

    Retourne AgentResult.ok({"reel_path": str}) ou AgentResult.fail(raison)
    """
    from engine.scene_director import generate_and_render
    import shutil

    post_path = Path(folder_path)
    brief = read_reel_brief(post_path)
    post_file = post_path / "facebook_post.txt"

    if not post_file.exists() and not brief:
        return AgentResult.fail("facebook_post.txt introuvable et pas de reel_brief.txt")

    if brief:
        # topic = sujet pur (sans "Persona: X. Sujet: Y")
        sujet   = brief["sujet"]
        persona = brief["persona"]
        context = brief.get("context", "")
        topic_text = sujet
        if context:
            topic_text += f"\nContexte: {context}"
        logger.info(f"[VIDEO MAKER] Brief: persona={persona!r}, sujet={sujet[:60]!r}")
    else:
        post_content = post_file.read_text(encoding="utf-8").strip()
        # Supprimer le préfixe "Reel:" si présent
        for prefix in ("Reel:", "REEL:", "reel:"):
            if post_content.lower().startswith(prefix.lower()):
                post_content = post_content[len(prefix):].strip()
                break
        topic_text = post_content
        persona = ""
        # Essayer de récupérer le persona depuis meta.json
        meta_file = post_path / "meta.json"
        if meta_file.exists():
            try:
                import json as _json
                meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                persona = meta.get("persona", "")
            except Exception:
                pass
        logger.info(f"[VIDEO MAKER] Depuis facebook_post.txt, persona={persona!r}")

    reel_dir = post_path / "reel"
    reel_dir.mkdir(exist_ok=True)
    output_mp4 = reel_dir / "reel.mp4"

    # ── Nettoyage avant régénération ────────────────────────────────
    # Sur Windows, ffmpeg ne peut pas écraser un fichier ouvert par un autre process.
    if output_mp4.exists():
        try:
            output_mp4.unlink()
            logger.info("Ancien reel.mp4 supprimé avant régénération")
        except Exception as e:
            logger.warning(f"Impossible de supprimer l'ancien reel.mp4 (ignoré): {e}")

    work_dir = reel_dir / "_cinema_work"
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir)
            logger.info("Dossier _cinema_work nettoyé")
        except Exception as e:
            logger.warning(f"Impossible de nettoyer _cinema_work (ignoré): {e}")

    logger.info(f"[VIDEO MAKER] Génération — topic={topic_text[:60]!r} persona={persona!r}")
    print(f"[VIDEO MAKER] topic={topic_text[:60]!r}")

    def progress_cb(pct, msg):
        if task_id:
            try:
                from core.task_tracker import update_task
                update_task(task_id, progress=pct, log=msg)
            except Exception:
                pass

    try:
        success = generate_and_render(
            topic=topic_text,
            output_path=str(output_mp4),
            voice="fr-FR-HenriNeural",
            publish=False,
            persona=persona,           # ← transmis pour choisir les bons REAL_PROOFS
            progress_callback=progress_cb,
        )

        if success and output_mp4.exists():
            meta_file = post_path / "meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["reel_generated"] = True
                meta["has_reel"] = True
                meta["status"] = "pending"
                meta_file.write_text(
                    json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            logger.info(f"Vidéo générée : {output_mp4}")
            return AgentResult.ok({"reel_path": str(output_mp4)})
        else:
            return AgentResult.fail("Cinema Engine n'a pas produit de fichier MP4")

    except Exception as e:
        logger.exception("Erreur dans video_maker -> engine")
        return AgentResult.fail(str(e))




