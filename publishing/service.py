"""
Local publish queue: JSON persistence, stubs, optional webhook, scheduled processing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .adapters import PublishResult, get_adapter
from .storage import load_queue, save_queue
from .webhook import notify_webhook


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def list_queue() -> list[dict[str, Any]]:
    return list(load_queue().get("items", []))


def get_item(item_id: str) -> dict[str, Any] | None:
    for it in list_queue():
        if it.get("id") == item_id:
            return it
    return None


def _write_items(items: list[dict[str, Any]]) -> None:
    data = load_queue()
    data["items"] = items
    save_queue(data)


def save_draft(
    *,
    topic: str,
    platform_primary: str,
    post_snapshot: dict[str, Any],
    audience_persona: dict[str, Any] | None = None,
    video_path: str | None = None,
) -> str:
    """Persist a draft row (queued=False until enqueue)."""
    data = load_queue()
    items = data.get("items", [])
    item_id = str(uuid.uuid4())
    row = {
        "id": item_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "draft",
        "scheduled_at": None,
        "platforms": [platform_primary],
        "topic": topic,
        "post_snapshot": post_snapshot,
        "audience_persona": audience_persona or {},
        "video_path": video_path,
        "publish_attempts": 0,
        "last_error": None,
        "publish_log": [],
    }
    items.append(row)
    data["items"] = items
    save_queue(data)
    return item_id


def enqueue(
    item_id: str,
    *,
    scheduled_at_iso: str | None,
    platforms: list[str],
) -> bool:
    """Move draft to queued with schedule and target platforms."""
    data = load_queue()
    items = data.get("items", [])
    for it in items:
        if it.get("id") != item_id:
            continue
        it["status"] = "queued"
        it["scheduled_at"] = scheduled_at_iso
        it["platforms"] = platforms or it.get("platforms") or ["linkedin"]
        it["updated_at"] = _now_iso()
        data["items"] = items
        save_queue(data)
        return True
    return False


def delete_item(item_id: str) -> bool:
    data = load_queue()
    items = [it for it in data.get("items", []) if it.get("id") != item_id]
    if len(items) == len(data.get("items", [])):
        return False
    data["items"] = items
    save_queue(data)
    return True


def _run_publish(
    item: dict[str, Any],
    *,
    webhook_url: str | None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for plat in item.get("platforms") or []:
        try:
            adapter = get_adapter(plat)
            snapshot = item.get("post_snapshot") or {}
            payload = {
                "topic": item.get("topic"),
                "platform": plat,
                "body": snapshot.get("body") or snapshot.get("caption") or "",
                "hashtags": snapshot.get("hashtags") or "",
                "sources": snapshot.get("sources") or [],
            }
            pr: PublishResult = adapter.publish(payload)
            results.append(
                {
                    "platform": plat,
                    "ok": pr.ok,
                    "external_id": pr.external_id,
                    "detail": pr.detail,
                }
            )
        except Exception as exc:
            results.append({"platform": plat, "ok": False, "detail": str(exc)})

    ok_any = any(r.get("ok") for r in results)
    item["publish_attempts"] = int(item.get("publish_attempts") or 0) + 1
    item["updated_at"] = _now_iso()
    item["last_publish_results"] = results
    if ok_any:
        item["status"] = "published"
        item["last_error"] = None
    else:
        item["status"] = "failed"
        item["last_error"] = "; ".join(
            f"{r.get('platform')}: {r.get('detail')}" for r in results if not r.get("ok")
        ) or "publish failed"

    log = list(item.get("publish_log") or [])
    log.append({"at": _now_iso(), "results": results})
    item["publish_log"] = log[-20:]

    if webhook_url:
        notify_webhook(
            webhook_url,
            "publish_attempt",
            {"item_id": item.get("id"), "results": results, "topic": item.get("topic")},
        )
    return item


def publish_manual(item_id: str, *, webhook_url: str | None = None) -> dict[str, Any] | None:
    data = load_queue()
    items = data.get("items", [])
    for i, it in enumerate(items):
        if it.get("id") != item_id:
            continue
        updated = _run_publish(dict(it), webhook_url=webhook_url)
        items[i] = updated
        data["items"] = items
        save_queue(data)
        return updated
    return None


def process_due(*, webhook_url: str | None = None) -> list[dict[str, Any]]:
    """Process queued items whose scheduled_at is in the past (or null = due immediately)."""
    now = datetime.now(timezone.utc)
    data = load_queue()
    items = data.get("items", [])
    touched: list[dict[str, Any]] = []

    for i, it in enumerate(items):
        if it.get("status") != "queued":
            continue
        sched = _parse_iso(it.get("scheduled_at"))
        due = sched is None or sched <= now
        if not due:
            continue
        items[i] = _run_publish(dict(it), webhook_url=webhook_url)
        touched.append(items[i])

    if touched:
        data["items"] = items
        save_queue(data)
    return touched
