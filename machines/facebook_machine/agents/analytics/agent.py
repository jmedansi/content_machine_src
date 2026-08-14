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


def analyze_content() -> dict:
    """Analyse le contenu généré et retourne des statistiques."""
    if not CONTENT_DIR.exists():
        return {}

    stats = {
        "total": 0,
        "published": 0,
        "unpublished": 0,
        "by_persona": Counter(),
        "by_type": Counter(),
        "word_counts": [],
        "with_images": 0,
        "with_resources": 0,
    }

    for folder in sorted(CONTENT_DIR.iterdir(), reverse=True):
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
            if meta.get("image_url"):
                stats["with_images"] += 1
            if meta.get("trigger_word"):
                stats["with_resources"] += 1
        except Exception:
            continue

    if stats["word_counts"]:
        stats["avg_word_count"] = round(sum(stats["word_counts"]) / len(stats["word_counts"]))
        stats["min_word_count"] = min(stats["word_counts"])
        stats["max_word_count"] = max(stats["word_counts"])

    return stats


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
    for persona, count in stats["by_persona"].most_common():
        print(f"   {persona}: {count}")
    print("\nPar type:")
    for ptype, count in stats["by_type"].most_common():
        print(f"   {ptype}: {count}")
    if stats.get("avg_word_count"):
        print(f"\nMots — Moy: {stats['avg_word_count']} / Min: {stats['min_word_count']} / Max: {stats['max_word_count']}")
    print(f"\nImages: {stats['with_images']}  |  Ressources: {stats['with_resources']}\n")


if __name__ == "__main__":
    print_report()
