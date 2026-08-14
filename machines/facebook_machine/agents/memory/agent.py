import json
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from core.config import Config

CONTENT_DIR = Config.CONTENT_DIR


def get_recent_topics(days=30):
    """Retourne les sujets des posts créés dans les N derniers jours."""
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for meta_file in sorted(CONTENT_DIR.glob("*/meta.json")):
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
    return recent


def get_recent_personas(days=7):
    """Retourne le décompte des personas utilisés dans les N derniers jours."""
    cutoff = datetime.now() - timedelta(days=days)
    counts = {}
    for meta_file in CONTENT_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            created = meta.get("created_at", "")
            if not created:
                continue
            if datetime.fromisoformat(created) < cutoff:
                continue
            persona = meta.get("persona", "unknown")
            counts[persona] = counts.get(persona, 0) + 1
        except Exception:
            continue
    return counts


def format_recent_for_planner(days=30):
    """Formate les sujets récents pour injection dans le prompt du planificateur."""
    recent = get_recent_topics(days)
    if not recent:
        return ""
    lines = [f"SUJETS DÉJÀ TRAITÉS (derniers {days} jours — NE PAS répéter) :"]
    for r in recent[-40:]:
        lines.append(f"- [{r['date']}] {r['persona']} : {r['topic'][:80]}")
    return "\n".join(lines)


def mark_as_published(folder_path: str) -> bool:
    """Marque un post comme publié (status → published)."""
    meta_file = Path(folder_path) / "meta.json"
    if not meta_file.exists():
        return False
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["status"] = "published"
    meta["published_at"] = datetime.now().isoformat()
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def approve_post(folder_path: str) -> bool:
    """Approuve un post pour publication (status pending → approved).
    
    Corrige automatiquement les incohérences de meta.json :
    - Si reel/reel.mp4 existe mais has_reel=false → corrige à True
    """
    folder = Path(folder_path)
    meta_file = folder / "meta.json"
    if not meta_file.exists():
        return False
    
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    
    # Auto-repair: vérifier si le reel existe physiquement
    reel_file = folder / "reel" / "reel.mp4"
    if reel_file.exists():
        meta["has_reel"] = True
        meta["reel_generated"] = True
    
    meta["status"] = "approved"
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def list_pending(content_dir=None) -> list:
    """Liste tous les posts en attente (status=pending ou approved non publiés).
    
    Inclut:
    - status == 'pending' : post généré, pas encore validé
    - status == 'approved' et published != True : validé mais pas encore publié
    """
    base = Path(content_dir) if content_dir else CONTENT_DIR
    pending = []
    for meta_file in sorted(base.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            status = meta.get("status", "")
            published = meta.get("published", False)
            
            # Inclure: pending OU (approved ET pas encore publié)
            if status not in ("pending", "approved"):
                continue
            if published:
                continue
            if not (meta_file.parent / "facebook_post.txt").exists():
                continue
                
            topic = meta.get("topic", "")
            if isinstance(topic, dict):
                topic = topic.get("sujet", str(topic))
            pending.append({
                "folder": meta_file.parent.name,
                "path": str(meta_file.parent),
                "persona": meta.get("persona", ""),
                "topic": str(topic)[:70],
                "created_at": meta.get("created_at", "")[:16],
                "word_count": meta.get("word_count", 0),
                "image_url": meta.get("image_url", ""),
                "image_failed": meta.get("image_failed", False) and not meta.get("image_url"),
                "has_reel": meta.get("has_reel", False) or meta.get("reel_generated", False),
                "has_pinned_comment": meta.get("has_pinned_comment", (meta_file.parent / "pinned_comment.txt").exists()),
                "status": status,
                "reel_path": str(meta_file.parent / "reel" / "reel.mp4") if (meta_file.parent / "reel" / "reel.mp4").exists() else ""
            })
        except Exception:
            continue
    return pending


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mémoire des posts générés")
    parser.add_argument("--pending", action="store_true")
    parser.add_argument("--approve", metavar="FOLDER")
    parser.add_argument("--approve-all", action="store_true")
    parser.add_argument("--recent", type=int, default=7)
    args = parser.parse_args()

    if args.pending:
        posts = list_pending()
        if not posts:
            print("Aucun post en attente.")
        else:
            print(f"\n{'─'*72}\n  {len(posts)} POST(S) EN ATTENTE\n{'─'*72}")
            for p in posts:
                print(f"  [{p['created_at']}] {p['persona']:18s} {p['word_count']:4d}m  {p['topic']}")
            print(f"{'─'*72}")
    elif args.approve:
        path = Path(args.approve)
        if not path.is_absolute():
            path = CONTENT_DIR / args.approve
        approve_post(str(path))
    elif args.approve_all:
        posts = list_pending()
        for p in posts:
            approve_post(p["path"])
        print(f"[MEMORY] {len(posts)} post(s) approuvé(s)")
    else:
        recent = get_recent_topics(args.recent)
        print(f"\n{len(recent)} posts créés dans les {args.recent} derniers jours :")
        for r in recent:
            print(f"  [{r['date']}] {r['persona']:18s}  {r['topic'][:65]}")
