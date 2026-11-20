"""
Pastebin platform connector.

API documentation : https://pastebin.com/doc_api
Free tier limits  : 25 unlisted pastes per day, 10 private pastes per day.

Credentials
-----------
PASTEBIN_API_KEY  — developer key from https://pastebin.com/doc_api
                    (register → log in → the key is shown at the top of that page)
"""

import logging

import httpx

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)

_API_URL = "https://pastebin.com/api/api_post.php"


class PastebinPlatform(BasePlatform):
    name = "Pastebin"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def post(self, message: str) -> PlatformResult:
        if not self._api_key:
            return self._failure(
                "PASTEBIN_API_KEY is not configured. "
                "Get your key at https://pastebin.com/doc_api"
            )

        payload = {
            "api_dev_key":          self._api_key,
            "api_option":           "paste",
            "api_paste_code":       message,
            "api_paste_private":    "0",        # 0 = public
            "api_paste_name":       "Dxora Technologies — Business Update",
            "api_paste_format":     "text",
            "api_paste_expire_date": "N",       # never expire
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(_API_URL, data=payload)
                response.raise_for_status()

            body = response.text.strip()

            # Pastebin always returns HTTP 200; success is a URL, failure is text.
            if body.startswith("https://pastebin.com/"):
                return self._success(posted_url=body, public_access=True)

            return self._failure(f"Pastebin API error: {body}")

        except httpx.TimeoutException:
            return self._failure("Request to Pastebin timed out after 15 s.")
        except httpx.HTTPStatusError as exc:
            return self._failure(
                f"HTTP {exc.response.status_code} from Pastebin: "
                f"{exc.response.text[:200]}"
            )
        except Exception as exc:
            return self._failure(f"Unexpected error: {exc}")
