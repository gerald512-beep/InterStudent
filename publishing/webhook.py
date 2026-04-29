"""Optional webhook notification after manual or scheduled publish attempts."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def notify_webhook(url: str | None, event: str, payload: dict[str, Any]) -> bool:
    if not url or not str(url).strip():
        return False
    body = {"event": event, "payload": payload}
    try:
        r = requests.post(url.strip(), json=body, timeout=15)
        ok = 200 <= r.status_code < 300
        if not ok:
            logger.warning("Webhook returned %s: %s", r.status_code, r.text[:500])
        return ok
    except Exception as exc:
        logger.warning("Webhook failed: %s", exc)
        return False
