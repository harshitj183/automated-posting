"""
Automated Multi-Platform Posting System
Dxora Technologies — Python Practical Test

FastAPI application entry point.
  Server  : http://localhost:4000
  Docs    : http://localhost:4000/docs
  Health  : http://localhost:4000/health
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.platforms.mastodon import MastodonPlatform
from app.platforms.pastebin import PastebinPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.wordpress import WordPressPlatform
from app.schemas import PostRequest, PostResponse, PostingSummary
from app.services.posting_service import PostingService

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Build platform connectors and attach the PostingService to app.state
    so the endpoint can access it without relying on a module-level global.
    """
    logger.info("Starting Automated Multi-Platform Posting System …")

    platforms = [
        PastebinPlatform(
            api_key=settings.pastebin_api_key,
        ),
        TelegramPlatform(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            channel_username=settings.telegram_channel_username,
        ),
        MastodonPlatform(
            instance=settings.mastodon_instance,
            access_token=settings.mastodon_access_token,
        ),
        RedditPlatform(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            username=settings.reddit_username,
            password=settings.reddit_password,
            subreddit=settings.reddit_subreddit,
        ),
        WordPressPlatform(
            site=settings.wordpress_site,
            token=settings.wordpress_token,
        ),
    ]

    app.state.posting_service = PostingService(platforms)
    logger.info(
        "PostingService ready with platforms: %s",
        ", ".join(p.name for p in platforms),
    )

    yield

    logger.info("Shutting down …")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description=(
        "A FastAPI service that publishes a short message with a CTA link "
        "simultaneously across **Pastebin**, **Telegram**, **Mastodon**, "
        "**Reddit**, and **WordPress.com** via their official REST APIs.\n\n"
        "**Assignment:** Dxora Technologies — Python Practical Test"
    ),
    version="1.0.0",
    contact={
        "name": "Dxora Technologies",
        "url": "https://crest.dxora.com",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
)


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {exc}"},
    )


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"], summary="Server and platform configuration status")
async def health(request: Request) -> dict[str, Any]:
    """
    Returns the server status and shows which platforms have credentials
    configured (without exposing the credential values themselves).
    """
    svc: PostingService = request.app.state.posting_service
    configured = {
        "Pastebin":      bool(settings.pastebin_api_key),
        "Telegram":      bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "Mastodon":      bool(settings.mastodon_access_token),
        "Reddit":        bool(settings.reddit_client_id and settings.reddit_username),
        "WordPress.com": bool(settings.wordpress_token and settings.wordpress_site),
    }
    return {
        "status": "ok",
        "version": "1.0.0",
        "platforms_registered": svc.platform_names,
        "platforms_configured": configured,
        "docs": "/docs",
    }


@app.get("/", tags=["Health"], include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse(
        {"service": "Automated Multi-Platform Posting System", "docs": "/docs"}
    )


# ── Main endpoint ─────────────────────────────────────────────────────────────

@app.post(
    "/posting",
    response_model=PostResponse,
    summary="Publish a message to all platforms",
    description=(
        "Validates the message, then simultaneously posts it to all 5 platforms. "
        "Returns a detailed result per platform plus a summary.\n\n"
        "**Validation rules:**\n"
        "- `message` must not be empty\n"
        "- `message` must not exceed 200 characters\n"
        "- `message` must contain exactly one URL (http:// or https://)\n"
        "- That URL must be syntactically valid\n\n"
        "A platform that fails does **not** prevent posting to the others."
    ),
    tags=["Posting"],
    status_code=status.HTTP_200_OK,
)
async def post_message(body: PostRequest, request: Request) -> PostResponse:
    """
    Publish a message to all configured platforms concurrently.
    """
    request_id = str(uuid.uuid4())
    logger.info("[%s] POST /posting — message length=%d", request_id, len(body.message))

    svc: PostingService = request.app.state.posting_service
    results, summary = await svc.post_all(body.message)
    overall_success = any(r.status == "success" for r in results)

    logger.info(
        "[%s] done — success=%s  %d/%d platforms",
        request_id,
        overall_success,
        summary.succeeded,
        summary.total,
    )

    return PostResponse(
        request_id=request_id,
        success=overall_success,
        summary=summary,
        results=results,
    )
