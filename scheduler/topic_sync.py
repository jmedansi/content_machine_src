import json
from pathlib import Path
from datetime import datetime

SYNC_DIR = Path(__file__).resolve().parent / "data"
PENDING_FILE = SYNC_DIR / "pending_topic_changes.json"


def _append_pending(obj: dict) -> None:
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if PENDING_FILE.exists():
        try:
            existing = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    obj["timestamp"] = datetime.utcnow().isoformat()
    existing.append(obj)
    PENDING_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue_topic_change(topic: dict) -> None:
    """Append a topic change for the scheduler to pick up asynchronously.

    This is intentionally lightweight to avoid coupling with the running scheduler instance.
    """
    try:
        _append_pending(topic)
    except Exception:
        # Best-effort only
        pass
