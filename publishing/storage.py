import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
QUEUE_FILENAME = "publish_queue.json"


def _queue_path() -> str:
    return os.path.join(os.environ.get("INTERSTUDENT_QUEUE_DIR", DEFAULT_DATA_DIR), QUEUE_FILENAME)


def ensure_data_dir() -> str:
    path_dir = os.path.dirname(_queue_path())
    os.makedirs(path_dir, exist_ok=True)
    return path_dir


def load_queue() -> dict[str, Any]:
    path = _queue_path()
    if not os.path.isfile(path):
        return {"version": 1, "updated_at": _now_iso(), "items": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "items" not in data:
        data["items"] = []
    data.setdefault("version", 1)
    return data


def save_queue(data: dict[str, Any]) -> None:
    ensure_data_dir()
    path = _queue_path()
    data["updated_at"] = _now_iso()
    tmp = path + ".tmp"
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
