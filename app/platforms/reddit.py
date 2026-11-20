"""
Reddit platform connector — OAuth2 password flow.

API documentation : https://www.reddit.com/dev/api
Free tier limits  : 60 OAuth requests per minute.

Credentials
-----------
REDDIT_CLIENT_ID      — from https://www.reddit.com/prefs/apps  (script app)
REDDIT_CLIENT_SECRET  — same page
REDDIT_USERNAME       — your Reddit account username
REDDIT_PASSWORD       — your Reddit account password
REDDIT_SUBREDDIT      — target subreddit without r/, e.g. "test"

Setup
-----
1. Go to https://www.reddit.com/prefs/apps → "create another app".
2. Choose type: script.  Set redirect URI to http://localhost.
3. Copy the Client ID (the short string below the app name) and Client Secret.
4. IMPORTANT: 2FA must be DISABLED on the Reddit account for password flow.
5. Use r/test for testing — it accepts any post.

Notes
-----
- The OAuth password flow is for personal-use scripts only (Reddit's terms).
- Subreddit names are stored without r/ prefix. The normalisation uses
  str.removeprefix("r/") (not lstrip) to avoid stripping subreddit names
  that happen to start with the letters 'r' or '/'.
"""

import logging

import httpx

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)

_TOKEN_URL   = "https://www.reddit.com/api/v1/access_token"
_SUBMIT_URL  = "https://oauth.reddit.com/api/submit"
_USER_AGENT  = "AutomatedPostingSystem/1.0 (by DxoraTechnologies; assignment)"


class RedditPlatform(BasePlatform):
    name = "Reddit"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        subreddit: str,
    ) -> None:
        self._client_id     = client_id
        self._client_secret = client_secret
        self._username      = username
        self._password      = password
        # Normalize: strip "r/" prefix safely (removeprefix, NOT lstrip)
        self._subreddit     = subreddit.removeprefix("r/").strip()

    async def post(self, message: str) -> PlatformResult:
        missing = [
            name
            for name, val in {
                "REDDIT_CLIENT_ID":     self._client_id,
                "REDDIT_CLIENT_SECRET": self._client_secret,
                "REDDIT_USERNAME":      self._username,
                "REDDIT_PASSWORD":      self._password,
                "REDDIT_SUBREDDIT":     self._subreddit,
            }.items()
            if not val
        ]
        if missing:
            return self._failure(
                f"Missing Reddit credentials: {', '.join(missing)}"
            )

        base_headers = {"User-Agent": _USER_AGENT}

        try:
            async with httpx.AsyncClient(timeout=20) as client:

                # ── Step 1: Obtain access token ───────────────────────────────
                token_resp = await client.post(
                    _TOKEN_URL,
                    auth=(self._client_id, self._client_secret),
                    data={
                        "grant_type": "password",
                        "username":   self._username,
                        "password":   self._password,
                    },
                    headers=base_headers,
                )
                token_resp.raise_for_status()
                token_data = token_resp.json()

                access_token = token_data.get("access_token")
                if not access_token:
                    err = token_data.get("error", "unknown")
                    return self._failure(
                        f"Reddit token request failed: {err}"
                    )

                # ── Step 2: Submit the post ───────────────────────────────────
                submit_headers = {
                    **base_headers,
                    "Authorization": f"bearer {access_token}",
                }
                submit_resp = await client.post(
                    _SUBMIT_URL,
                    headers=submit_headers,
                    data={
                        "sr":        self._subreddit,
                        "kind":      "self",
                        "title":     "Dxora Technologies — Business Update",
                        "text":      message,
                        "resubmit":  "true",
                        "nsfw":      "false",
                    },
                )
                submit_resp.raise_for_status()
                submit_data = submit_resp.json()

            # Navigate nested response: {"json": {"data": {"url": "..."}}}
            try:
                posted_url = submit_data["json"]["data"]["url"]
            except (KeyError, TypeError):
                errors = submit_data.get("json", {}).get("errors", [])
                if errors:
                    # Errors is a list of [code, message, field] triples
                    readable = "; ".join(
                        f"{e[0]}: {e[1]}" if len(e) >= 2 else str(e)
                        for e in errors
                    )
                    return self._failure(f"Reddit submission error: {readable}")
                return self._failure(
                    f"Unexpected Reddit response: {str(submit_data)[:200]}"
                )

            return self._success(posted_url=posted_url, public_access=True)

        except httpx.TimeoutException:
            return self._failure("Reddit request timed out after 20 s.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                return self._failure(
                    "Reddit authentication failed (HTTP 401). "
                    "Check your REDDIT_CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD."
                )
            if status == 403:
                return self._failure(
                    "Reddit returned HTTP 403 — the account may lack permission "
                    "to post in that subreddit."
                )
            return self._failure(
                f"HTTP {status} from Reddit: {exc.response.text[:200]}"
            )
        except Exception as exc:
            return self._failure(f"Unexpected error: {exc}")
