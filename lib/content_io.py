import json
import hashlib
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any, List


def read_meta(meta_path: str) -> Optional[Dict[str, Any]]:
    p = Path(meta_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(p))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def checksum_file(path: str) -> Optional[str]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def scan_accounts(content_root: str) -> List[Dict[str, Any]]:
    root = Path(content_root)
    results = []
    if not root.exists():
        return results
    for acc in root.iterdir():
        if not acc.is_dir():
            continue
        # account folder may be 'accounts/<id>' or 'acc_<id>' style
        meta_path = acc / "meta.json"
        meta = read_meta(str(meta_path))
        results.append({
            "account_folder": str(acc),
            "account_id": acc.name,
            "meta": meta,
        })
    return results


def ensure_meta_fields(meta: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(defaults)
    if meta:
        out.update(meta)
    return out


def account_content_path(base: str, account_id: str, content_id: str) -> str:
    p = Path(base) / account_id / content_id
    p.mkdir(parents=True, exist_ok=True)
    return str(p)
