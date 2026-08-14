"""Canonical scheduler facade.

This module exposes the canonical pipeline functions (currently implemented
in `shared_agents/scheduler/agent.py`) so other parts of the codebase can
import a single, stable API.
"""
from datetime import datetime
from typing import List, Any, Optional

from shared_agents.scheduler.agent import (
    process_single_post as _process_single_post,
    process_reel as _process_reel,
    _run_pipeline_for_account as _run_for_account,
    run_pipeline as _run_pipeline,
)


def run_pipeline(post_type: str = "all", publish: bool = False, date: Optional[str] = None, task_id: Optional[str] = None) -> Any:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return _run_pipeline(post_type=post_type, publish=publish, date=date, task_id=task_id)


def run_pipeline_for_account(account_id: int, platform: str = "facebook", post_type: str = "all", publish: bool = False, date: Optional[str] = None, task_id: Optional[str] = None) -> Any:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return _run_for_account(account_id, platform, post_type, publish, date, task_id)


def process_single_post(plan_entry: dict, date: Optional[str] = None, publish: bool = False, task_id: Optional[str] = None, current: int = 0, total: int = 1, account_id: Optional[int] = None, platform: str = "facebook", folder_path: Optional[str] = None) -> Any:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return _process_single_post(plan_entry, date, publish, task_id=task_id, current=current, total=total, account_id=account_id, platform=platform, folder_path=folder_path)


def process_reel(reel_entry: dict, date: Optional[str] = None, publish: bool = False, task_id: Optional[str] = None, current: int = 0, total: int = 1, account_id: Optional[int] = None, platform: str = "facebook", folder_path: Optional[str] = None) -> Any:
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return _process_reel(reel_entry, date, publish, task_id=task_id, current=current, total=total, account_id=account_id, platform=platform)


__all__ = ["run_pipeline", "run_pipeline_for_account", "process_single_post", "process_reel"]
