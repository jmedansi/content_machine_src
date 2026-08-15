# agent.py — Wrapper Instagram qui délègue au scheduler partagé
# Toute la logique est dans shared_agents/scheduler/agent.py
import sys
from pathlib import Path

IG_MACHINE_DIR = Path(__file__).resolve().parent.parent.parent
FB_MACHINE_DIR = Path("d:/Content_Machine/machines/facebook_machine")
ROOT_DIR = IG_MACHINE_DIR.parent.parent

str_ig = str(IG_MACHINE_DIR)
if str_ig in sys.path:
    sys.path.remove(str_ig)
sys.path.insert(0, str_ig)
str_root = str(ROOT_DIR)
if str_root not in sys.path:
    sys.path.insert(1, str_root)
str_fb = str(FB_MACHINE_DIR)
if str_fb not in sys.path:
    sys.path.insert(2, str_fb)

from shared_agents.scheduler.agent import (
    process_single_post,
    process_reel,
    run_pipeline,
    _get_account_llm_model,
    _make_bar,
    _update_progress,
)

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