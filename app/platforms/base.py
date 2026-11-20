"""
Abstract base class that every platform connector must implement.

Design contract
---------------
- `name`  — human-readable platform label used in response objects
- `post(message)` — publish the message; must NEVER raise. Any exception must be
  caught internally and returned as a failed PlatformResult.
- `_success(url, public)` / `_failure(error)` — convenience builders that stamp
  the current UTC timestamp automatically.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.schemas import PlatformResult

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    name: str = "Unknown"

    @abstractmethod
    async def post(self, message: str) -> PlatformResult:
        """
        Publish *message* to this platform and return a :class:`PlatformResult`.

        Implementations must catch all exceptions and return a failure result
        rather than propagating them — the posting service's gather loop is a
        safety net, not a substitute for per-platform error handling.
        """
        ...

    # ── UTC timestamp ─────────────────────────────────────────────────────────

    def _now_utc(self) -> tuple[str, str]:
        """Return (YYYY-MM-DD, HH:MM:SS) for the current UTC moment."""
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")

    # ── Result builders ───────────────────────────────────────────────────────

    def _success(
        self,
        posted_url: str,
        public_access: bool = True,
    ) -> PlatformResult:
        date_str, time_str = self._now_utc()
        logger.info("[%s] posted successfully → %s", self.name, posted_url)
        return PlatformResult(
            platform=self.name,
            status="success",
            posted_url=posted_url,
            public_access=public_access,
            date=date_str,
            time=time_str,
        )

    def _failure(self, error: str) -> PlatformResult:
        date_str, time_str = self._now_utc()
        logger.warning("[%s] posting failed: %s", self.name, error)
        return PlatformResult(
            platform=self.name,
            status="failed",
            public_access=False,
            date=date_str,
            time=time_str,
            error=error,
        )
