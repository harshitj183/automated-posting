"""
Pydantic models for request validation and response serialization.
"""

import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


# ── URL extraction helper ─────────────────────────────────────────────────────

# Matches http:// or https:// URLs, stopping at whitespace.
# Strips common trailing punctuation so "visit https://example.com." works.
_URL_PATTERN = re.compile(r"https?://[^\s]+")
_TRAILING_PUNCT = re.compile(r"[.,;:!?)]+$")


def _extract_urls(text: str) -> list[str]:
    """Return every URL found in *text*, with trailing punctuation stripped."""
    raw = _URL_PATTERN.findall(text)
    return [_TRAILING_PUNCT.sub("", u) for u in raw]


def _is_valid_url(url: str) -> bool:
    """Return True if *url* has both a valid scheme and a network location."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in {"http", "https"} and parsed.netloc)
    except Exception:
        return False


# ── Request model ─────────────────────────────────────────────────────────────

class PostRequest(BaseModel):
    """
    Incoming request body for POST /posting.

    Validation rules
    ----------------
    - message must not be empty
    - message must not exceed 200 characters
    - message must contain exactly one URL (http:// or https://)
    - that URL must be valid (has a scheme and a network location)
    """

    message: str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("message must not be empty.")

        if len(v) > 200:
            raise ValueError(
                f"message must not exceed 200 characters "
                f"(current length: {len(v)})."
            )

        urls = _extract_urls(v)

        if len(urls) == 0:
            raise ValueError(
                "message must contain exactly one CTA link "
                "(starting with http:// or https://)."
            )

        if len(urls) > 1:
            raise ValueError(
                f"message must contain exactly one CTA link, "
                f"but {len(urls)} were found."
            )

        if not _is_valid_url(urls[0]):
            raise ValueError(
                f"The URL '{urls[0]}' is not valid. "
                "Make sure it starts with http:// or https:// and has a domain."
            )

        return v


# ── Per-platform result ───────────────────────────────────────────────────────

class PlatformResult(BaseModel):
    """Result for a single platform posting attempt."""

    platform: str
    status: str                         # "success" | "failed"
    posted_url: Optional[str] = None    # public URL of the created content
    public_access: bool = False         # whether the content is publicly viewable
    date: Optional[str] = None          # ISO date, e.g. "2026-11-20"
    time: Optional[str] = None          # HH:MM:SS UTC, e.g. "10:30:00"
    error: Optional[str] = None         # error description when status == "failed"


# ── Aggregated response ───────────────────────────────────────────────────────

class PostingSummary(BaseModel):
    """High-level statistics about a posting run."""

    total: int
    succeeded: int
    failed: int
    duration_ms: Optional[float] = None  # total wall-clock time in milliseconds


class PostResponse(BaseModel):
    """Aggregated response returned by POST /posting."""

    request_id: str                     # unique ID for this request (for log tracing)
    success: bool                       # True if at least one platform succeeded
    summary: PostingSummary
    results: list[PlatformResult]
