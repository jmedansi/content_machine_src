"""Wrapper for Twitter scheduler delegating to the canonical scheduler
kept in `machines/facebook_machine/agents/scheduler/agent.py`.

The original implementation is preserved in `agent_legacy.py`.
"""
from datetime import datetime
from typing import List

try:
    from scheduler.canonical import process_single_post as canonical_process_single_post
    from scheduler.canonical import run_pipeline_for_account as canonical_run_for_account
except Exception:
    from scheduler.canonical import process_single_post as canonical_process_single_post
    from scheduler.canonical import run_pipeline_for_account as canonical_run_for_account


def process_single_tweet(topic: dict, account_id: str, publish: bool = False):
    date = datetime.now().strftime("%Y-%m-%d")
    plan_entry = {"persona": topic.get("persona"), "sujet": topic.get("titre") or topic.get("topic")}
    plan_entry.update(topic)
    return canonical_process_single_post(plan_entry, date, publish, task_id=None, current=0, total=1, account_id=account_id, platform="twitter")


def run_pipeline(account_id: int, topics: List[dict] = None, publish: bool = False):
    if topics:
        results = []
        for t in topics:
            results.append(process_single_tweet(t, account_id, publish))
        return results
    return canonical_run_for_account(account_id, "twitter", "all", publish, datetime.now().strftime("%Y-%m-%d"), None)


def publish_pending_tweets(account_id: int):
    # Best-effort: use canonical scheduler to publish
    return canonical_run_for_account(account_id, "twitter", "all", True, datetime.now().strftime("%Y-%m-%d"), None)


if __name__ == "__main__":
    print("Twitter scheduler (wrapper) -> delegated to canonical scheduler")
