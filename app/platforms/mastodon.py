"""
Mastodon platform connector.

API documentation : https://docs.joinmastodon.org/methods/statuses/
Free tier limits  : 300 posts per 3 hours (default; varies by instance).

Credentials
-----------
MASTODON_INSTANCE      — your Mastodon instance domain, e.g. mastodon.social
MASTODON_ACCESS_TOKEN  — OAuth access token

Setup
-----
1. Register at https://mastodon.social (or any Mastodon instance).
2. Go to Preferences → Development → New Application.
3. Enable scope: write:statuses
4. Click Submit, then copy "Your access token".
"""

import logging

import httpx

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)


class MastodonPlatform(BasePlatform):
    name = "Mastodon"

    def __init__(self, instance: str, access_token: str) -> None:
        # Normalize: strip protocol and trailing slash so callers can pass
        # either "mastodon.social" or "https://mastodon.social/"
        self._instance = (
            instance
            .removeprefix("https://")
            .removeprefix("http://")
            .rstrip("/")
        )
        self._access_token = access_token

    async def post(self, message: str) -> PlatformResult:
        if not self._access_token:
            return self._failure(
                "MASTODON_ACCESS_TOKEN is not configured. "
                "Create one at https://<your-instance>/settings/applications"
            )
        if not self._instance:
            return self._failure("MASTODON_INSTANCE is not configured.")

        url = f"https://{self._instance}/api/v1/statuses"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "status": message,
            "visibility": "public",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            posted_url = data.get("url")
            if not posted_url:
                return self._failure(
                    "Mastodon returned a success response but included no post URL."
                )

            return self._success(posted_url=posted_url, public_access=True)

        except httpx.TimeoutException:
            return self._failure("Request to Mastodon timed out after 15 s.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                return self._failure(
                    "Mastodon authentication failed (HTTP 401). "
                    "Check your MASTODON_ACCESS_TOKEN."
                )
            if status == 422:
                return self._failure(
                    "Mastodon rejected the post (HTTP 422 — content policy or duplicate)."
                )
            return self._failure(
                f"HTTP {status} from Mastodon: {exc.response.text[:200]}"
            )
        except Exception as exc:
            return self._failure(f"Unexpected error: {exc}")
