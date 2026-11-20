"""
Test suite — Automated Multi-Platform Posting System
=====================================================

Covers
------
1. Input validation  — all 422 cases + happy path
2. PostingService    — concurrent execution, failure isolation, exception wrapping
3. Platform connectors — each platform's success + failure paths (HTTP mocked)
4. Full endpoint     — structure, field presence, summary stats
5. Health endpoint   — basic smoke test
"""

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from app.main import app
from app.platforms.mastodon import MastodonPlatform
from app.platforms.pastebin import PastebinPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.wordpress import WordPressPlatform
from app.schemas import PlatformResult
from app.services.posting_service import PostingService

# ── Shared fixture & constants ─────────────────────────────────────────────────

VALID_MESSAGE = (
    "Check out our latest business platform and grow your visibility. "
    "https://example.com"
)


@pytest.fixture(scope="module")
def client():
    """
    Module-scoped TestClient.  Using `with TestClient(app) as c:` triggers
    the FastAPI lifespan (startup/shutdown) so app.state.posting_service
    is initialised before any test runs.
    """
    with TestClient(app) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# 1.  INPUT VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:

    def test_empty_message_returns_422(self, client):
        resp = client.post("/posting", json={"message": ""})
        assert resp.status_code == 422

    def test_whitespace_only_returns_422(self, client):
        resp = client.post("/posting", json={"message": "   "})
        assert resp.status_code == 422

    def test_message_over_200_chars_returns_422(self, client):
        # 180 chars + a URL = exactly 201+ chars total
        long_msg = "A" * 170 + " https://example.com " + "B" * 20
        assert len(long_msg) > 200
        resp = client.post("/posting", json={"message": long_msg})
        assert resp.status_code == 422
        assert "200" in resp.text

    def test_exactly_200_chars_is_accepted(self, client):
        # Build a message that is exactly 200 characters
        url = "https://example.com"
        prefix = "X" * (200 - len(url) - 1)  # -1 for the space
        msg = f"{prefix} {url}"
        assert len(msg) == 200
        resp = client.post("/posting", json={"message": msg})
        assert resp.status_code == 200

    def test_no_url_returns_422(self, client):
        resp = client.post("/posting", json={"message": "No link here at all"})
        assert resp.status_code == 422
        body = resp.json()
        assert any("CTA link" in str(d) for d in body["detail"])

    def test_two_urls_returns_422(self, client):
        msg = "Visit https://example.com and also https://another.com today"
        resp = client.post("/posting", json={"message": msg})
        assert resp.status_code == 422

    def test_url_without_scheme_returns_422(self, client):
        resp = client.post(
            "/posting",
            json={"message": "Visit example.com for details about us today"},
        )
        assert resp.status_code == 422

    def test_valid_message_returns_200(self, client):
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        assert resp.status_code == 200

    def test_valid_message_response_has_required_top_level_fields(self, client):
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        data = resp.json()
        assert "request_id" in data
        assert "success" in data
        assert "summary" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_response_contains_one_result_per_platform(self, client):
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        assert len(resp.json()["results"]) == 5

    def test_each_result_has_all_required_fields(self, client):
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        for r in resp.json()["results"]:
            for field in ("platform", "status", "posted_url",
                          "public_access", "date", "time", "error"):
                assert field in r, f"Field '{field}' missing from result: {r}"

    def test_summary_fields_are_correct(self, client):
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        summary = resp.json()["summary"]
        assert summary["total"] == 5
        assert summary["succeeded"] + summary["failed"] == summary["total"]
        assert summary["duration_ms"] is not None
        assert summary["duration_ms"] >= 0

    def test_request_id_is_uuid(self, client):
        import uuid
        resp = client.post("/posting", json={"message": VALID_MESSAGE})
        rid = resp.json()["request_id"]
        # Should not raise
        uuid.UUID(rid)

    def test_url_with_trailing_dot_is_handled(self, client):
        # "https://example.com." — the dot should be stripped by the validator
        # and the message should pass validation.
        resp = client.post(
            "/posting",
            json={"message": "See https://example.com. for more info about us"},
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 2.  POSTING SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class _MockPlatform:
    """Fake platform that returns a canned result without HTTP calls."""

    def __init__(self, name: str, success: bool = True) -> None:
        self.name = name
        self._succeed = success

    async def post(self, message: str) -> PlatformResult:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if self._succeed:
            return PlatformResult(
                platform=self.name,
                status="success",
                posted_url=f"https://example.com/{self.name.lower()}/1",
                public_access=True,
                date=now.strftime("%Y-%m-%d"),
                time=now.strftime("%H:%M:%S"),
            )
        return PlatformResult(
            platform=self.name,
            status="failed",
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            error="Simulated failure",
        )


class _ExplodingPlatform:
    """Platform whose post() raises unconditionally."""
    name = "Exploding"

    async def post(self, message: str):
        raise RuntimeError("This platform always explodes")


@pytest.mark.asyncio
async def test_service_returns_result_for_every_platform():
    svc = PostingService([_MockPlatform("A"), _MockPlatform("B"), _MockPlatform("C")])
    results, summary = await svc.post_all(VALID_MESSAGE)
    assert len(results) == 3
    assert summary.total == 3
    assert summary.succeeded == 3
    assert summary.failed == 0


@pytest.mark.asyncio
async def test_service_continues_after_one_platform_fails():
    svc = PostingService([
        _MockPlatform("A", success=True),
        _MockPlatform("B", success=False),
        _MockPlatform("C", success=True),
    ])
    results, summary = await svc.post_all(VALID_MESSAGE)
    assert results[0].status == "success"
    assert results[1].status == "failed"
    assert results[2].status == "success"
    assert summary.succeeded == 2
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_service_wraps_unhandled_exception_into_failed_result():
    svc = PostingService([_ExplodingPlatform()])
    results, summary = await svc.post_all(VALID_MESSAGE)
    assert len(results) == 1
    assert results[0].status == "failed"
    assert "Unhandled error" in results[0].error
    assert summary.failed == 1


@pytest.mark.asyncio
async def test_service_duration_ms_is_positive():
    svc = PostingService([_MockPlatform("X")])
    _, summary = await svc.post_all(VALID_MESSAGE)
    assert summary.duration_ms >= 0


def test_service_requires_at_least_one_platform():
    with pytest.raises(ValueError, match="at least one platform"):
        PostingService([])


# ══════════════════════════════════════════════════════════════════════════════
# 3.  PLATFORM CONNECTORS  (HTTP mocked via pytest-httpx)
# ══════════════════════════════════════════════════════════════════════════════

# ── Pastebin ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pastebin_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pastebin.com/api/api_post.php",
        text="https://pastebin.com/AbCdEfGh",
        status_code=200,
    )
    result = await PastebinPlatform(api_key="test_key").post(VALID_MESSAGE)
    assert result.status == "success"
    assert result.posted_url == "https://pastebin.com/AbCdEfGh"
    assert result.public_access is True
    assert result.error is None


@pytest.mark.asyncio
async def test_pastebin_api_error_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pastebin.com/api/api_post.php",
        text="Bad API request, invalid api_dev_key",
        status_code=200,
    )
    result = await PastebinPlatform(api_key="bad_key").post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "Bad API" in result.error


@pytest.mark.asyncio
async def test_pastebin_missing_key_does_not_call_http():
    # No httpx_mock needed — the guard returns before any HTTP call
    result = await PastebinPlatform(api_key="").post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "PASTEBIN_API_KEY" in result.error


# ── Telegram ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_success_public_channel(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.telegram.org/botTEST_TOKEN/sendMessage",
        json={"ok": True, "result": {"message_id": 42}},
    )
    result = await TelegramPlatform(
        bot_token="TEST_TOKEN",
        chat_id="-1001234567890",
        channel_username="testchannel",
    ).post(VALID_MESSAGE)
    assert result.status == "success"
    assert result.posted_url == "https://t.me/testchannel/42"
    assert result.public_access is True


@pytest.mark.asyncio
async def test_telegram_private_channel_url_correct(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.telegram.org/botTEST_TOKEN/sendMessage",
        json={"ok": True, "result": {"message_id": 7}},
    )
    result = await TelegramPlatform(
        bot_token="TEST_TOKEN",
        chat_id="-1009876543210",
        channel_username="",          # private — no username
    ).post(VALID_MESSAGE)
    assert result.status == "success"
    # removeprefix("-100") on "-1009876543210" → "9876543210"
    assert result.posted_url == "https://t.me/c/9876543210/7"
    assert result.public_access is False


@pytest.mark.asyncio
async def test_telegram_ok_false_returns_failed(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.telegram.org/botTEST_TOKEN/sendMessage",
        json={"ok": False, "description": "Forbidden: bot is not a member"},
    )
    result = await TelegramPlatform(
        bot_token="TEST_TOKEN",
        chat_id="@chan",
        channel_username="chan",
    ).post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "Forbidden" in result.error


@pytest.mark.asyncio
async def test_telegram_missing_credentials():
    result = await TelegramPlatform(
        bot_token="",
        chat_id="",
        channel_username="",
    ).post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "TELEGRAM_BOT_TOKEN" in result.error


# ── Mastodon ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mastodon_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://mastodon.social/api/v1/statuses",
        json={
            "id": "109876543210",
            "url": "https://mastodon.social/@testuser/109876543210",
        },
    )
    result = await MastodonPlatform(
        instance="mastodon.social",
        access_token="test_token",
    ).post(VALID_MESSAGE)
    assert result.status == "success"
    assert result.posted_url == "https://mastodon.social/@testuser/109876543210"
    assert result.public_access is True


@pytest.mark.asyncio
async def test_mastodon_instance_with_https_prefix(httpx_mock: HTTPXMock):
    # Users sometimes copy the full URL; the connector should strip the protocol.
    httpx_mock.add_response(
        url="https://mastodon.social/api/v1/statuses",
        json={"id": "1", "url": "https://mastodon.social/@u/1"},
    )
    result = await MastodonPlatform(
        instance="https://mastodon.social/",
        access_token="tok",
    ).post(VALID_MESSAGE)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_mastodon_401_returns_clear_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://mastodon.social/api/v1/statuses",
        status_code=401,
        json={"error": "The access token is invalid"},
    )
    result = await MastodonPlatform(
        instance="mastodon.social",
        access_token="bad_token",
    ).post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "401" in result.error


# ── Reddit ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reddit_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"access_token": "mocked_token", "token_type": "bearer"},
    )
    httpx_mock.add_response(
        url="https://oauth.reddit.com/api/submit",
        json={
            "json": {
                "errors": [],
                "data": {
                    "url": "https://www.reddit.com/r/test/comments/abc123/dxora_post/"
                },
            }
        },
    )
    result = await RedditPlatform(
        client_id="id",
        client_secret="secret",
        username="user",
        password="pass",
        subreddit="test",
    ).post(VALID_MESSAGE)
    assert result.status == "success"
    assert "reddit.com" in result.posted_url


@pytest.mark.asyncio
async def test_reddit_subreddit_prefix_stripped_correctly(httpx_mock: HTTPXMock):
    """Subreddit names starting with 'r' (e.g. r/rareposts) must not lose their
    first letter — this was the lstrip bug. removeprefix fixes it."""
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"access_token": "tok", "token_type": "bearer"},
    )
    httpx_mock.add_response(
        url="https://oauth.reddit.com/api/submit",
        json={"json": {"errors": [], "data": {"url": "https://reddit.com/r/rareposts/x"}}},
    )
    platform = RedditPlatform("i", "s", "u", "p", subreddit="r/rareposts")
    # The subreddit should be stored as "rareposts", not "areposts"
    assert platform._subreddit == "rareposts"
    result = await platform.post(VALID_MESSAGE)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_reddit_token_failure(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"error": "invalid_grant"},
        status_code=200,
    )
    result = await RedditPlatform("i", "s", "u", "p", "test").post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "invalid_grant" in result.error


@pytest.mark.asyncio
async def test_reddit_submission_errors_array(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"access_token": "tok", "token_type": "bearer"},
    )
    httpx_mock.add_response(
        url="https://oauth.reddit.com/api/submit",
        json={
            "json": {
                "errors": [["SUBREDDIT_NOTALLOWED", "you are not allowed to post here", "sr"]],
                "data": None,
            }
        },
    )
    result = await RedditPlatform("i", "s", "u", "p", "banned").post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "SUBREDDIT_NOTALLOWED" in result.error


# ── WordPress.com ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wordpress_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://public-api.wordpress.com/rest/v1.1/sites/testsite.wordpress.com/posts/new",
        json={
            "ID": 1,
            "URL": "https://testsite.wordpress.com/2026/11/20/dxora-technologies/",
        },
    )
    result = await WordPressPlatform(
        site="testsite.wordpress.com",
        token="test_token",
    ).post(VALID_MESSAGE)
    assert result.status == "success"
    assert result.posted_url == "https://testsite.wordpress.com/2026/11/20/dxora-technologies/"
    assert result.public_access is True


@pytest.mark.asyncio
async def test_wordpress_401_returns_clear_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://public-api.wordpress.com/rest/v1.1/sites/testsite.wordpress.com/posts/new",
        status_code=401,
        json={"error": "unauthorized", "message": "User cannot access this private blog."},
    )
    result = await WordPressPlatform(
        site="testsite.wordpress.com",
        token="bad_token",
    ).post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "401" in result.error


@pytest.mark.asyncio
async def test_wordpress_missing_credentials():
    result = await WordPressPlatform(site="", token="").post(VALID_MESSAGE)
    assert result.status == "failed"
    assert "WORDPRESS_TOKEN" in result.error


# ══════════════════════════════════════════════════════════════════════════════
# 4.  HEALTH ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

def test_health_endpoint_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_endpoint_structure(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert "platforms_registered" in data
    assert "platforms_configured" in data
    assert len(data["platforms_registered"]) == 5


def test_health_platforms_configured_has_all_five(client):
    configured = client.get("/health").json()["platforms_configured"]
    expected = {"Pastebin", "Telegram", "Mastodon", "Reddit", "WordPress.com"}
    assert set(configured.keys()) == expected
