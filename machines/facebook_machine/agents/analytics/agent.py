"""
agents/analytics/agent.py — Analytique des posts générés
Migré depuis agents/agent_analytics.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from core.config import Config

CONTENT_DIR = Config.CONTENT_DIR


def analyze_content(content_dir: Path = None) -> dict:
    """Analyse le contenu généré et retourne des statistiques.

    content_dir: dossier content à analyser (par plateforme/account).
    Par défaut: Config.CONTENT_DIR (compatibilité avec l'appel CLI existant).
    """
    target = Path(content_dir) if content_dir else CONTENT_DIR
    if not target.exists():
        return {}

    stats = {
        "total": 0,
        "published": 0,
        "unpublished": 0,
        "by_persona": Counter(),
        "by_type": Counter(),
        "word_counts": [],
        "with_images": 0,
        "with_reels": 0,
        "with_resources": 0,
        "compliance": Counter(),
    }

    for folder in sorted(target.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            stats["total"] += 1
            if meta.get("published"):
                stats["published"] += 1
            else:
                stats["unpublished"] += 1
            stats["by_persona"][meta.get("persona", "unknown")] += 1
            stats["by_type"][meta.get("post_type", "unknown")] += 1
            wc = meta.get("word_count", 0)
            if wc > 0:
                stats["word_counts"].append(wc)
            if meta.get("has_image") or meta.get("image_url"):
                stats["with_images"] += 1
            if meta.get("has_reel"):
                stats["with_reels"] += 1
            if meta.get("trigger_word"):
                stats["with_resources"] += 1
            if wc > 0:
                stats["compliance"][_compliance_bucket(meta)] += 1
        except Exception:
            continue

    if stats["word_counts"]:
        stats["avg_word_count"] = round(sum(stats["word_counts"]) / len(stats["word_counts"]))
        stats["min_word_count"] = min(stats["word_counts"])
        stats["max_word_count"] = max(stats["word_counts"])

    stats["by_persona"] = dict(stats["by_persona"])
    stats["by_type"] = dict(stats["by_type"])
    stats["compliance"] = dict(stats["compliance"])
    return stats


def analyze_content_multi(content_dirs) -> dict:
    """Agrège les statistiques sur plusieurs dossiers content (multi-comptes/client).

    Fusionne analyze_content() sur chaque dossier : totaux additionnés,
    Counter fusionnés, word_counts concaténés.
    """
    merged = {
        "total": 0,
        "published": 0,
        "unpublished": 0,
        "by_persona": Counter(),
        "by_type": Counter(),
        "word_counts": [],
        "with_images": 0,
        "with_reels": 0,
        "with_resources": 0,
        "compliance": Counter(),
    }
    for d in (content_dirs or []):
        s = analyze_content(Path(d)) if d else {}
        if not s:
            continue
        merged["total"] += s.get("total", 0)
        merged["published"] += s.get("published", 0)
        merged["unpublished"] += s.get("unpublished", 0)
        merged["with_images"] += s.get("with_images", 0)
        merged["with_reels"] += s.get("with_reels", 0)
        merged["with_resources"] += s.get("with_resources", 0)
        merged["word_counts"] += s.get("word_counts", [])
        for k, v in s.get("by_persona", {}).items():
            merged["by_persona"][k] += v
        for k, v in s.get("by_type", {}).items():
            merged["by_type"][k] += v
        for k, v in s.get("compliance", {}).items():
            merged["compliance"][k] += v
    if merged["word_counts"]:
        merged["avg_word_count"] = round(sum(merged["word_counts"]) / len(merged["word_counts"]))
        merged["min_word_count"] = min(merged["word_counts"])
        merged["max_word_count"] = max(merged["word_counts"])
    merged["by_persona"] = dict(merged["by_persona"])
    merged["by_type"] = dict(merged["by_type"])
    merged["compliance"] = dict(merged["compliance"])
    return merged


def list_posts_multi(content_dirs, published_only: bool = True) -> list:
    """Liste les posts sur plusieurs dossiers content (concatène list_posts)."""
    result = []
    for d in (content_dirs or []):
        if not d:
            continue
        try:
            result.extend(list_posts(Path(d), published_only=published_only))
        except Exception:
            continue
    return result


def list_posts(content_dir: Path = None, published_only: bool = True) -> list:
    """Retourne la liste des posts publiés (pour les insights engagement).

    Chaque entrée : {folder, persona, message, date, post_id, word_count,
    published_at, created_at}.
    """
    target = Path(content_dir) if content_dir else CONTENT_DIR
    if not target.exists():
        return []
    posts = []
    for folder in sorted(target.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_file = folder / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if published_only and not meta.get("published"):
                continue
            posts.append({
                "folder": folder.name,
                "persona": meta.get("persona", "unknown"),
                "message": meta.get("content", meta.get("text", "")),
                "date": (meta.get("published_at") or meta.get("created_at") or "")[:10],
                "post_id": meta.get("facebook_post_id") or meta.get("post_id") or "",
                "word_count": meta.get("word_count", 0),
                "published_at": meta.get("published_at", ""),
                "created_at": meta.get("created_at", ""),
            })
        except Exception:
            continue
    return posts


def _compliance_bucket(meta: dict) -> str:
    """Classe un post en green/yellow/red selon son respect de la longueur cible.

    Cible = target_words du meta (sinon 500). Tolérance ±25% → yellow,
    au-delà → red, sinon green.
    """
    wc = meta.get("word_count", 0) or 0
    target = meta.get("target_words") or 500
    try:
        target = int(target)
    except Exception:
        target = 500
    if wc <= 0:
        return "yellow"
    low, high = target * 0.75, target * 1.25
    if low <= wc <= high:
        return "green"
    return "yellow" if low * 0.75 <= wc <= high * 1.25 else "red"


def print_report():
    """Affiche le rapport d'analytique dans la console."""
    stats = analyze_content()
    if not stats:
        print("Aucun contenu généré.")
        return

    print(f"\n{'='*50}")
    print("RAPPORT D'ANALYTIQUE — Facebook Machine")
    print(f"{'='*50}\n")
    print(f"[TOTAL]  Posts: {stats['total']}")
    print(f"[OK]     Publiés: {stats['published']}")
    print(f"[...]    Non publiés: {stats['unpublished']}\n")
    print("Par persona:")
    for persona, count in sorted(stats["by_persona"].items(), key=lambda x: -x[1]):
        print(f"   {persona}: {count}")
    print("\nPar type:")
    for ptype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
        print(f"   {ptype}: {count}")
    if stats.get("avg_word_count"):
        print(f"\nMots — Moy: {stats['avg_word_count']} / Min: {stats['min_word_count']} / Max: {stats['max_word_count']}")
    print(f"\nImages: {stats['with_images']}  |  Reels: {stats['with_reels']}  |  Ressources: {stats['with_resources']}")


if __name__ == "__main__":
    print_report()
