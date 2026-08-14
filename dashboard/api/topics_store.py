import json
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.config import Config

try:
    from core.paths import PLATFORM_BASE
except ImportError:
    PLATFORM_BASE = {
        "facebook": Path(__file__).resolve().parent.parent.parent / "machines" / "facebook_machine",
        "linkedin": Path(__file__).resolve().parent.parent.parent / "machines" / "linkedin_machine",
        "twitter": Path(__file__).resolve().parent.parent.parent / "machines" / "twitter_machine",
    }

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Config.DATA_DIR
DASHBOARD_DATA_DIR = BASE_DIR / "data"
INDEX_PATH = DASHBOARD_DATA_DIR / "topics_index.json"
CURRENT_VERSION = "1.0"


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _get_planned_topics_file(platform: str, account_id: int) -> Path:
    base = PLATFORM_BASE.get(platform)
    if not base:
        return DATA_DIR / "planned_topics.json"
    acc_dir = base / "accounts" / str(account_id)
    acc_dir.mkdir(parents=True, exist_ok=True)
    return acc_dir / "planned_topics.json"


def _load_index() -> Dict[str, Dict]:
    try:
        if not INDEX_PATH.exists():
            return {}
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: Dict[str, Dict]) -> None:
    _atomic_write(INDEX_PATH, index)


def _update_index_entry(topic_id: str, entry: Dict) -> None:
    idx = _load_index()
    idx[topic_id] = entry
    _save_index(idx)


def _remove_index_entry(topic_id: str) -> None:
    idx = _load_index()
    if topic_id in idx:
        del idx[topic_id]
        _save_index(idx)


def _migrate_old_format(data: dict) -> dict:
    """Convert old persona-keyed format to new flat format.

    Old: { "persona_name": [{ id, topic, context, ... }] }
    New: { "version": "1.0", "topics": [{ id, persona, topic, context, ... }] }
    """
    topics = []
    for persona_key, items in data.items():
        if not isinstance(items, list):
            continue
        for t in items:
            entry = {
                "id": t.get("id") or str(uuid.uuid4()),
                "persona": t.get("persona") or persona_key,
                "topic": t.get("topic") or t.get("titre") or t.get("title") or "",
                "context": t.get("context") or t.get("angle") or "",
                "media": t.get("media", "none"),
                "date": t.get("date") or (t.get("date_prevue", "") or "")[:10] or "",
                "time": t.get("time", ""),
                "variables": t.get("variables", {}),
                "validated": t.get("validated", False),
                "used": t.get("used", False),
            }
            topics.append(entry)
    return {"version": CURRENT_VERSION, "topics": topics}


def load_topics_file(fpath: Path) -> dict:
    """Load planned_topics.json, auto-migrating old format if needed."""
    if not fpath.exists():
        return {"version": CURRENT_VERSION, "topics": []}
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception:
        return {"version": CURRENT_VERSION, "topics": []}

    if "version" in data and "topics" in data:
        return data

    migrated = _migrate_old_format(data)
    _atomic_write(fpath, migrated)
    return migrated


def save_topics_file(fpath: Path, data: dict) -> None:
    data["version"] = CURRENT_VERSION
    _atomic_write(fpath, data)


def find_source_by_id(topic_id: str) -> Optional[Dict]:
    idx = _load_index()
    entry = idx.get(topic_id)
    if entry:
        return entry

    for platform, base in PLATFORM_BASE.items():
        if not base.exists():
            continue
        accounts_dir = base / "accounts"
        if not accounts_dir.exists():
            continue
        for acc in accounts_dir.iterdir():
            try:
                if not acc.is_dir():
                    continue
                account_id = int(acc.name)
            except Exception:
                try:
                    if acc.name.startswith("acc_"):
                        account_id = int(acc.name.split("_")[1])
                    else:
                        continue
                except Exception:
                    continue

            fpath = acc / "planned_topics.json"
            if not fpath.exists():
                continue
            file_data = load_topics_file(fpath)
            for t in file_data.get("topics", []):
                if t.get("id") == topic_id:
                    entry = {"platform": platform, "account_id": account_id, "source": str(fpath)}
                    _update_index_entry(topic_id, entry)
                    return entry

    fallback = DATA_DIR / "planned_topics.json"
    if fallback.exists():
        file_data = load_topics_file(fallback)
        for t in file_data.get("topics", []):
            if t.get("id") == topic_id:
                entry = {"platform": "unknown", "account_id": None, "source": str(fallback)}
                _update_index_entry(topic_id, entry)
                return entry

    return None


def list_topics(platform: str, account_id: int, filters: Dict = None) -> List[Dict]:
    fpath = _get_planned_topics_file(platform, account_id)
    file_data = load_topics_file(fpath)

    out = []
    for t in file_data.get("topics", []):
        tid = t.get("id") or str(uuid.uuid4())
        if "id" not in t:
            t["id"] = tid
        normalized = {
            "id": tid,
            "persona": t.get("persona", ""),
            "topic": t.get("topic", ""),
            "context": t.get("context", ""),
            "media": t.get("media", "none"),
            "date": t.get("date", ""),
            "time": t.get("time", ""),
            "validated": t.get("validated", False),
            "used": t.get("used", False),
            "platform": platform,
            "account_id": account_id,
            "source": str(fpath),
            "raw": t,
        }
        out.append(normalized)
        _update_index_entry(tid, {"platform": platform, "account_id": account_id, "source": str(fpath)})

    return out


def get_topic(topic_id: str, account_id: int) -> Optional[Dict]:
    entry = find_source_by_id(topic_id)
    if not entry:
        return None
    if account_id is not None and entry.get("account_id") is not None and int(entry.get("account_id")) != int(account_id):
        return None

    fpath = Path(entry.get("source"))
    file_data = load_topics_file(fpath)

    for t in file_data.get("topics", []):
        if t.get("id") == topic_id:
            return {
                "id": topic_id,
                "persona": t.get("persona"),
                "platform": entry.get("platform"),
                "account_id": entry.get("account_id"),
                "source": str(fpath),
                "raw": t,
            }

    return None


def create_topic(data: Dict, platform: str, account_id: int) -> Dict:
    fpath = _get_planned_topics_file(platform, account_id)
    file_data = load_topics_file(fpath)

    new_id = data.get("id") or str(uuid.uuid4())
    entry = {
        "id": new_id,
        "persona": data.get("persona", "default"),
        "topic": data.get("topic") or data.get("titre") or "",
        "context": data.get("context", ""),
        "media": data.get("media", "none"),
        "date": data.get("date") or (data.get("date_prevue") or "")[:10] or "",
        "time": data.get("time", ""),
        "variables": data.get("variables", {}),
        "validated": data.get("validated", False),
        "used": data.get("used", False),
    }

    file_data["topics"].append(entry)
    save_topics_file(fpath, file_data)
    _update_index_entry(new_id, {"platform": platform, "account_id": account_id, "source": str(fpath)})
    return {"id": new_id, "persona": entry["persona"], "platform": platform, "account_id": account_id, "source": str(fpath), "raw": entry}


def update_topic(topic_id: str, data: Dict, platform: str, account_id: int) -> Optional[Dict]:
    entry = find_source_by_id(topic_id)
    if not entry:
        return None
    if account_id is not None and entry.get("account_id") is not None and int(entry.get("account_id")) != int(account_id):
        return None

    fpath = Path(entry.get("source"))
    file_data = load_topics_file(fpath)

    updated = None
    for i, t in enumerate(file_data["topics"]):
        if t.get("id") == topic_id:
            allowed = {"persona", "topic", "context", "media", "date", "time", "validated", "used", "used_at", "variables", "date_prevue"}
            for k, v in data.items():
                if k in allowed:
                    t[k] = v
            file_data["topics"][i] = t
            updated = t
            break

    if not updated:
        return None

    save_topics_file(fpath, file_data)
    _update_index_entry(topic_id, {"platform": platform, "account_id": account_id, "source": str(fpath)})
    return {"id": topic_id, "persona": updated.get("persona"), "platform": platform, "account_id": account_id, "source": str(fpath), "raw": updated}


def delete_topic(topic_id: str, platform: str, account_id: int) -> bool:
    entry = find_source_by_id(topic_id)
    if not entry:
        return False
    if account_id is not None and entry.get("account_id") is not None and int(entry.get("account_id")) != int(account_id):
        return False

    fpath = Path(entry.get("source"))
    file_data = load_topics_file(fpath)

    original_len = len(file_data["topics"])
    file_data["topics"] = [t for t in file_data["topics"] if t.get("id") != topic_id]

    if len(file_data["topics"]) == original_len:
        return False

    save_topics_file(fpath, file_data)
    _remove_index_entry(topic_id)
    return True


def _get_existing_personas(platform: str, account_id: int) -> set:
    """Return set of persona names that exist in the account's persona directory."""
    base = PLATFORM_BASE.get(platform)
    if not base:
        return set()
    persona_dir = base / "accounts" / str(account_id) / "persona"
    if not persona_dir.exists():
        return set()
    return {
        p.name for p in persona_dir.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    }


def import_topics(topics_list: List[Dict], platform: str, account_id: int, mode: str = "merge") -> Dict:
    """Import a list of topics into the planned_topics.json file.

    Args:
        topics_list: List of topic dicts with at least { persona, topic, context, media, date, time }
        platform: Target platform
        account_id: Target account
        mode: "merge" (append) or "replace" (overwrite all)

    Returns:
        Dict with imported count and any warnings
    """
    fpath = _get_planned_topics_file(platform, account_id)

    if mode == "replace":
        file_data = {"version": CURRENT_VERSION, "topics": []}
    else:
        file_data = load_topics_file(fpath)

    warnings = []
    imported = 0

    existing_personas = _get_existing_personas(platform, account_id)
    missing_personas = set()

    for t in topics_list:
        if not t.get("persona") or not t.get("topic"):
            warnings.append(f"Topic ignoré: persona ou topic manquant")
            continue

        persona = t["persona"]
        if existing_personas and persona not in existing_personas:
            missing_personas.add(persona)

        entry = {
            "id": t.get("id") or str(uuid.uuid4()),
            "persona": persona,
            "topic": t["topic"],
            "context": t.get("context", ""),
            "media": t.get("media", "none"),
            "date": t.get("date", ""),
            "time": t.get("time", ""),
            "validated": t.get("validated", False),
            "used": t.get("used", False),
        }

        # Mapper date+time → date_prevue pour le unified scheduler
        topic_date = t.get("date", "")
        topic_time = t.get("time", "")
        if topic_date:
            time_str = topic_time if topic_time else "12:00"
            entry["date_prevue"] = f"{topic_date[:10]}T{time_str}:00"
        file_data["topics"].append(entry)
        imported += 1

    if missing_personas:
        warnings.append(
            f"Personas introuvables sur ce compte: {', '.join(sorted(missing_personas))}. "
            f"Créez-les dans accounts/{account_id}/persona/ ou corrigez le champ 'persona' dans le fichier."
        )

    save_topics_file(fpath, file_data)

    for t in file_data["topics"]:
        _update_index_entry(t["id"], {"platform": platform, "account_id": account_id, "source": str(fpath)})

    return {"imported": imported, "warnings": warnings, "total": len(file_data["topics"])}
