"""
Re-export from core.github_upload to avoid duplication.
The canonical implementation is in the root core/github_upload.py
"""
import sys as _sys
from pathlib import Path as _Path

_core_dir = str(_Path(__file__).resolve().parent.parent.parent.parent / "core")
if _core_dir not in _sys.path:
    _sys.path.insert(0, _core_dir)

from core.github_upload import upload_image_to_github, resolve_image_url, GITHUB_API_URL, RAW_BASE_URL

__all__ = ["upload_image_to_github", "resolve_image_url", "GITHUB_API_URL", "RAW_BASE_URL"]
