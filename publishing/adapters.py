"""
Stub publisher adapters — production-safe placeholders.

Does not call Instagram Graph API or LinkedIn UGC POST in production.
Implement real OAuth + API calls behind these interfaces when ready.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    ok: bool
    platform: str
    external_id: str | None
    detail: str


class LinkedInPublisher:
    """Stub: logs intent; replace with LinkedIn Marketing / UGC API."""

    def publish(self, payload: dict[str, Any]) -> PublishResult:
        topic = (payload.get("topic") or "")[:80]
        logger.info("[LinkedIn stub] Would publish post topic=%r", topic)
        return PublishResult(
            ok=True,
            platform="linkedin",
            external_id="stub_li_" + str(hash(topic))[-8:],
            detail="Stub publish — no network call. Wire LinkedIn UGC API here.",
        )


class InstagramPublisher:
    """
    Stub only — full consumer posting automation is intentionally out of scope.
    """

    def publish(self, payload: dict[str, Any]) -> PublishResult:
        topic = (payload.get("topic") or "")[:80]
        logger.info("[Instagram stub] Skipping automated Graph API publish topic=%r", topic)
        return PublishResult(
            ok=True,
            platform="instagram",
            external_id=None,
            detail="Stub — Instagram posting not automated. Export assets or use Meta Business Suite manually.",
        )


def get_adapter(platform: str):
    p = (platform or "").lower().strip()
    if p == "linkedin":
        return LinkedInPublisher()
    if p == "instagram":
        return InstagramPublisher()
    raise ValueError(f"Unknown platform: {platform}")
