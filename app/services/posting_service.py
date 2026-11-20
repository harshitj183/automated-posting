"""
PostingService — concurrent multi-platform orchestration.

Runs all platform connectors in parallel with asyncio.gather and
return_exceptions=True, so a failure (or exception) on one platform
never blocks or cancels the others.

Returns results in the same order platforms were registered.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult, PostingSummary

logger = logging.getLogger(__name__)


class PostingService:
    def __init__(self, platforms: list[BasePlatform]) -> None:
        if not platforms:
            raise ValueError("PostingService requires at least one platform.")
        self._platforms = platforms

    @property
    def platform_names(self) -> list[str]:
        """Names of all registered platforms, in registration order."""
        return [p.name for p in self._platforms]

    async def post_all(self, message: str) -> tuple[list[PlatformResult], PostingSummary]:
        """
        Post *message* to every registered platform concurrently.

        Returns
        -------
        results : list[PlatformResult]
            One result per platform, in registration order.
        summary : PostingSummary
            Aggregate statistics for the run.
        """
        start = time.monotonic()

        raw = await asyncio.gather(
            *[p.post(message) for p in self._platforms],
            return_exceptions=True,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        results: list[PlatformResult] = []

        for platform, outcome in zip(self._platforms, raw):
            if isinstance(outcome, PlatformResult):
                results.append(outcome)
            else:
                # An exception escaped the platform's own error handling.
                # Wrap it into a failed result so the caller always gets a
                # complete list regardless of what went wrong.
                now = datetime.now(timezone.utc)
                logger.error(
                    "[%s] unhandled exception escaped post(): %s",
                    platform.name,
                    outcome,
                    exc_info=outcome if isinstance(outcome, BaseException) else False,
                )
                results.append(
                    PlatformResult(
                        platform=platform.name,
                        status="failed",
                        date=now.strftime("%Y-%m-%d"),
                        time=now.strftime("%H:%M:%S"),
                        error=f"Unhandled error: {outcome}",
                    )
                )

        succeeded = sum(1 for r in results if r.status == "success")
        summary = PostingSummary(
            total=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            duration_ms=round(elapsed_ms, 2),
        )

        logger.info(
            "Posting run complete — %d/%d succeeded in %.0f ms",
            succeeded,
            len(results),
            elapsed_ms,
        )

        return results, summary
