"""
Telegram Bot platform connector.

API documentation : https://core.telegram.org/bots/api#sendmessage
Free tier limits  : No rate limit for normal use (<30 msg/s to different chats).

Credentials
-----------
TELEGRAM_BOT_TOKEN         — token from @BotFather  (create with /newbot)
TELEGRAM_CHAT_ID           — numeric ID or @username of the target channel/group
TELEGRAM_CHANNEL_USERNAME  — public channel username WITHOUT @, e.g. "mychannel"
                              Leave empty if the channel is private.

Setup
-----
1. Message @BotFather on Telegram → /newbot → copy token.
2. Create a public channel → Settings → Administrators → add your bot as Admin.
3. Set TELEGRAM_CHAT_ID to @channel_username or the numeric channel ID.
4. Set TELEGRAM_CHANNEL_USERNAME to the same username without the @.
"""

import logging

import httpx

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)


class TelegramPlatform(BasePlatform):
    name = "Telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        channel_username: str = "",
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        # Remove a leading @ if the user accidentally included it
        self._channel_username = channel_username.lstrip("@")

    async def post(self, message: str) -> PlatformResult:
        missing = {
            k: v for k, v in {
                "TELEGRAM_BOT_TOKEN": self._bot_token,
                "TELEGRAM_CHAT_ID": self._chat_id,
            }.items() if not v
        }
        if missing:
            return self._failure(
                f"Missing Telegram credentials: {', '.join(missing)}"
            )

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            if not data.get("ok"):
                desc = data.get("description", "Unknown error from Telegram")
                return self._failure(f"Telegram API error: {desc}")

            # Use .get() to avoid KeyError when message_id is absent
            message_id = data.get("result", {}).get("message_id")
            if not message_id:
                return self._failure(
                    "Telegram returned success but no message_id in response."
                )

            if self._channel_username:
                # Public channel — direct link works for anyone
                posted_url = f"https://t.me/{self._channel_username}/{message_id}"
                public_access = True
            else:
                # Private group/channel — link requires membership to view.
                # The numeric channel ID format is -100XXXXXXXXXX.
                # Strip the -100 prefix with removeprefix (Python 3.9+), not lstrip.
                raw_id = str(self._chat_id)
                stripped_id = (
                    raw_id.removeprefix("-100")
                    if raw_id.startswith("-100")
                    else raw_id.lstrip("-")
                )
                posted_url = f"https://t.me/c/{stripped_id}/{message_id}"
                public_access = False

            return self._success(posted_url=posted_url, public_access=public_access)

        except httpx.TimeoutException:
            return self._failure("Request to Telegram timed out after 15 s.")
        except httpx.HTTPStatusError as exc:
            return self._failure(
                f"HTTP {exc.response.status_code} from Telegram: "
                f"{exc.response.text[:200]}"
            )
        except Exception as exc:
            return self._failure(f"Unexpected error: {exc}")
