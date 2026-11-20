"""
WordPress.com platform connector.

API documentation : https://developer.wordpress.com/docs/api/1.1/post/sites/%24site/posts/new/
Free tier limits  : No hard rate limit for the REST API on free plans.

Credentials
-----------
WORDPRESS_SITE   — your site domain, e.g. yoursite.wordpress.com
WORDPRESS_TOKEN  — OAuth2 bearer token

Setup
-----
1. Go to https://developer.wordpress.com/apps/ → Create New Application.
2. Set Redirect URL to http://localhost (for manual token retrieval).
3. Retrieve a bearer token via the Implicit OAuth2 flow:
   Open this URL in your browser (replace YOUR_CLIENT_ID):

   https://public-api.wordpress.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost&response_type=token

4. After authorizing, the browser redirects to something like:
   http://localhost/#access_token=TOKEN_HERE&token_type=bearer&...
   Copy the value after access_token= and use it as WORDPRESS_TOKEN.
5. Set WORDPRESS_SITE to your WordPress.com site domain.
"""

import logging

import httpx

from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)


class WordPressPlatform(BasePlatform):
    name = "WordPress.com"

    def __init__(self, site: str, token: str) -> None:
        self._site  = site.strip().rstrip("/")
        self._token = token

    async def post(self, message: str) -> PlatformResult:
        if not self._token:
            return self._failure(
                "WORDPRESS_TOKEN is not configured. "
                "See https://developer.wordpress.com/docs/oauth2/"
            )
        if not self._site:
            return self._failure("WORDPRESS_SITE is not configured.")

        url = (
            f"https://public-api.wordpress.com/rest/v1.1/sites/"
            f"{self._site}/posts/new"
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "title":   "Dxora Technologies — Business Update",
            "content": message,
            "status":  "publish",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            # WordPress.com returns "URL" (uppercase) for the public post URL
            posted_url = data.get("URL") or data.get("url")
            if not posted_url:
                return self._failure(
                    "WordPress.com returned success but no post URL in response."
                )

            return self._success(posted_url=posted_url, public_access=True)

        except httpx.TimeoutException:
            return self._failure("Request to WordPress.com timed out after 20 s.")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                return self._failure(
                    "WordPress.com authentication failed (HTTP 401). "
                    "Check your WORDPRESS_TOKEN."
                )
            if status == 403:
                return self._failure(
                    "WordPress.com refused the request (HTTP 403). "
                    "Ensure your token has permission to publish posts."
                )
            return self._failure(
                f"HTTP {status} from WordPress.com: {exc.response.text[:200]}"
            )
        except Exception as exc:
            return self._failure(f"Unexpected error: {exc}")
