"""Wrapper for LinkedIn scheduler delegating to the canonical scheduler
kept in `machines/facebook_machine/agents/scheduler/agent.py`.

This file replaces the original LinkedIn scheduler implementation with a
thin adapter that calls the canonical scheduler functions. The original
implementation is preserved in `agent_legacy.py`.
"""
from datetime import datetime
from typing import List, Any

# Use the canonical scheduler facade so migration remains centralized
try:
    from scheduler.canonical import process_single_post as canonical_process_single_post
    from scheduler.canonical import run_pipeline_for_account as canonical_run_for_account
except Exception:
    from scheduler.canonical import process_single_post as canonical_process_single_post
    from scheduler.canonical import run_pipeline_for_account as canonical_run_for_account


def process_single_post(topic: dict, account_id: str, publish: bool = False):
    """Delegate LinkedIn single post processing to canonical scheduler.

    The canonical function expects a plan_entry shape; we map common keys.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    plan_entry = {"persona": topic.get("persona") or topic.get("persona_name"),
                  "sujet": topic.get("titre") or topic.get("topic")}
    # Merge rest of topic fields in case the canonical pipeline uses them
    plan_entry.update(topic)
    return canonical_process_single_post(plan_entry, date, publish, task_id=None, current=0, total=1, account_id=account_id, platform="linkedin")


def run_pipeline(account_id: int, topics: List[dict] = None, publish: bool = False):
    """Run pipeline for LinkedIn account.

    If `topics` provided, process them sequentially, otherwise delegate to
    the canonical per-account pipeline runner.
    """
    if topics:
        results = []
        for t in topics:
            results.append(process_single_post(t, account_id, publish))
        return results
    # Delegate to canonical per-account runner
    return canonical_run_for_account(account_id, "linkedin", "all", publish, datetime.now().strftime("%Y-%m-%d"), None)


def publish_pending_posts(account_id: int):
    """Publish pending posts for account using canonical scheduler as fallback."""
    # Best-effort: run the per-account pipeline with publish flag True
    return canonical_run_for_account(account_id, "linkedin", "all", True, datetime.now().strftime("%Y-%m-%d"), None)


if __name__ == "__main__":
    print("LinkedIn scheduler (wrapper) -> delegated to canonical scheduler")
