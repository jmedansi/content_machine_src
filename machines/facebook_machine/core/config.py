"""
Re-export from root core.config to avoid duplication.
The canonical implementation is in the root core/config.py
"""
import sys as _sys
from pathlib import Path as _Path

_core_dir = str(_Path(__file__).resolve().parent.parent.parent.parent / "core")
if _core_dir not in _sys.path:
    _sys.path.insert(0, _core_dir)

from core.config import Config

__all__ = ["Config"]
