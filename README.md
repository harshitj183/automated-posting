# Automated Multi-Platform Posting System

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![Tests](https://img.shields.io/badge/tests-pytest-yellow?logo=pytest)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

A production-quality FastAPI service that publishes a short message with a CTA link **simultaneously across 5 platforms** via their official REST APIs — Pastebin, Telegram, Mastodon, Reddit, and WordPress.com.

Built as the Python Practical Test for **Dxora Technologies**.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Platform Integrations](#platform-integrations)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Setup](#setup)
7. [Platform Credential Guide](#platform-credential-guide)
8. [Running the Server](#running-the-server)
9. [API Reference](#api-reference)
10. [Sample Request & Response](#sample-request--response)
11. [Running Tests](#running-tests)
12. [Error Handling](#error-handling)
13. [Design Decisions](#design-decisions)

---

## What It Does

Send a single HTTP request to `POST /posting` with a message containing a link. The system:

1. **Validates** the message — max 200 characters, exactly one valid URL, correct format.
2. **Posts concurrently** to all 5 platforms using `asyncio.gather` — total time ≈ slowest single platform, not the sum of all.
3. **Returns** a structured result for every platform — success/failure, public URL, UTC timestamp, and error details.
4. **Isolates failures** — a failure on one platform never stops the others.
5. **Tracks requests** — every call gets a unique `request_id` for log tracing.

---

## Architecture

```
Client
  │
  │  POST /posting  {"message": "..."}
  ▼
┌─────────────────────────────────────────────┐
│  FastAPI  (port 4000)                        │
│                                             │
│  Pydantic Validator                         │
│  ├── max 200 chars                          │
│  ├── exactly 1 URL                          │
│  └── URL syntactically valid                │
│                                             │
│  PostingService.post_all(message)           │
│  └── asyncio.gather (all 5 in parallel)     │
│       ├── PastebinPlatform                  │
│       ├── TelegramPlatform                  │
│       ├── MastodonPlatform                  │
│       ├── RedditPlatform                    │
│       └── WordPressPlatform                 │
└─────────────────────────────────────────────┘
  │
  │  {"request_id": "...", "success": true,
  │   "summary": {...}, "results": [...]}
  ▼
Client
```

---

## Platform Integrations

| # | Platform | Integration Method | Public URL on Success | Free |
|---|---|---|---|---|
| 1 | **Pastebin** | REST API (form-data) | `pastebin.com/XXXXX` | ✅ |
| 2 | **Telegram** | Bot API (JSON) | `t.me/channel/msg_id` | ✅ |
| 3 | **Mastodon** | REST API (OAuth2 Bearer) | `mastodon.social/@user/id` | ✅ |
| 4 | **Reddit** | OAuth2 Password Flow | `reddit.com/r/.../` | ✅ |
| 5 | **WordPress.com** | REST API (OAuth2 Bearer) | `yoursite.wordpress.com/post` | ✅ |

---

## Project Structure

```
automated-posting/
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app, /posting endpoint, /health endpoint
│   ├── schemas.py              ← Pydantic request/response models + validation
│   ├── config.py               ← All settings loaded from .env
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py             ← Abstract BasePlatform (_success, _failure helpers)
│   │   ├── pastebin.py
│   │   ├── telegram.py
│   │   ├── mastodon.py
│   │   ├── reddit.py
│   │   └── wordpress.py
│   └── services/
│       ├── __init__.py
│       └── posting_service.py  ← asyncio.gather orchestration + PostingSummary
├── tests/
│   └── test_posting.py         ← 35+ pytest tests, all HTTP mocked
├── .env.example                ← Credential template with inline comments
├── requirements.txt
├── Makefile
├── pytest.ini
└── README.md
```

---

## Prerequisites

- Python **3.10** or higher
- `pip` (bundled with Python)
- Accounts on the platforms you want to post to (details below)

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/automated-posting.git
cd automated-posting

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Open .env and fill in your API keys — see the guide below
```

---

## Platform Credential Guide

### 1. Pastebin

> Free developer key — no approval required.

1. Register at [pastebin.com](https://pastebin.com) and log in.
2. Visit [pastebin.com/doc_api](https://pastebin.com/doc_api) — your key appears at the top.
3. Add to `.env`:
   ```
   PASTEBIN_API_KEY=your_key_here
   ```

---

### 2. Telegram

> Free Bot API — no approval required for personal bots.

1. Open Telegram → search **@BotFather** → send `/newbot`.
2. Follow the prompts, copy the token BotFather gives you.
3. Create a **public channel** (Telegram app → New Channel → Public).
4. Add your bot as Administrator: Channel → Edit → Administrators → Add Admin.
5. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   TELEGRAM_CHAT_ID=@your_channel_username
   TELEGRAM_CHANNEL_USERNAME=your_channel_username    # without @
   ```

---

### 3. Mastodon

> Free account — no approval required on most instances.

1. Register at [mastodon.social](https://mastodon.social) (or any instance).
2. Go to **Preferences → Development → New Application**.
3. Enable scope: `write:statuses`. Click **Submit**.
4. Copy **Your access token** from the app detail page.
5. Add to `.env`:
   ```
   MASTODON_INSTANCE=mastodon.social
   MASTODON_ACCESS_TOKEN=your_token_here
   ```

---

### 4. Reddit

> Free API access — requires a Reddit account.

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).
2. Click **"create another app"** → type: **script** → redirect URI: `http://localhost`.
3. Note the **Client ID** (the string below the app name) and **Client Secret**.
4. ⚠️ Your Reddit account must have **2FA disabled** for the password flow.
5. For testing, use `r/test` — it accepts posts from anyone.
6. Add to `.env`:
   ```
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USERNAME=your_reddit_username
   REDDIT_PASSWORD=your_reddit_password
   REDDIT_SUBREDDIT=test
   ```

---

### 5. WordPress.com

> Free site — requires a WordPress.com account.

1. Go to [developer.wordpress.com/apps/](https://developer.wordpress.com/apps/) → **Create New Application**.
2. Set Redirect URL to `http://localhost`.
3. Get a bearer token using the Implicit OAuth2 flow. Open this URL in your browser (replace `YOUR_CLIENT_ID`):
   ```
   https://public-api.wordpress.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost&response_type=token
   ```
4. After authorizing, the browser redirects to something like:
   ```
   http://localhost/#access_token=TOKEN_HERE&token_type=bearer&...
   ```
   Copy the value after `access_token=`.
5. Add to `.env`:
   ```
   WORDPRESS_SITE=yoursite.wordpress.com
   WORDPRESS_TOKEN=your_bearer_token_here
   ```

---

## Running the Server

```bash
# Using Makefile (recommended)
make run

# Or directly
uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

| URL | Description |
|---|---|
| `http://localhost:4000/docs` | Interactive Swagger UI |
| `http://localhost:4000/health` | Platform configuration status |
| `http://localhost:4000/posting` | Main endpoint (POST) |

---

## API Reference

### `POST /posting`

Publishes a message to all configured platforms.

#### Request Body

```json
{
  "message": "Your message with exactly one link. https://example.com"
}
```

| Field | Type | Rules |
|---|---|---|
| `message` | string | Not empty · Max 200 characters · Exactly 1 URL · URL must be valid |

#### Response `200 OK`

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "summary": {
    "total": 5,
    "succeeded": 5,
    "failed": 0,
    "duration_ms": 842.5
  },
  "results": [...]
}
```

#### Per-Platform Result Object

| Field | Type | Description |
|---|---|---|
| `platform` | string | Platform name |
| `status` | string | `"success"` or `"failed"` |
| `posted_url` | string \| null | Public URL of the created content |
| `public_access` | boolean | Whether the content is publicly accessible |
| `date` | string \| null | UTC posting date `YYYY-MM-DD` |
| `time` | string \| null | UTC posting time `HH:MM:SS` |
| `error` | string \| null | Error detail when `status == "failed"` |

#### Validation Error `422`

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "message"],
      "msg": "Value error, message must contain exactly one CTA link (starting with http:// or https://).",
      "input": "No link here"
    }
  ]
}
```

### `GET /health`

Returns server status and shows which platforms have credentials configured (never exposes the values themselves).

```json
{
  "status": "ok",
  "version": "1.0.0",
  "platforms_registered": ["Pastebin", "Telegram", "Mastodon", "Reddit", "WordPress.com"],
  "platforms_configured": {
    "Pastebin": true,
    "Telegram": true,
    "Mastodon": false,
    "Reddit": true,
    "WordPress.com": false
  },
  "docs": "/docs"
}
```

---

## Sample Request & Response

### cURL — Success

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Check out our latest business platform and grow your online visibility. https://example.com"
  }'
```

```json
{
  "request_id": "7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "success": true,
  "summary": {
    "total": 5,
    "succeeded": 5,
    "failed": 0,
    "duration_ms": 723.4
  },
  "results": [
    {
      "platform": "Pastebin",
      "status": "success",
      "posted_url": "https://pastebin.com/AbCdEfGh",
      "public_access": true,
      "date": "2026-11-20",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Telegram",
      "status": "success",
      "posted_url": "https://t.me/mychannel/42",
      "public_access": true,
      "date": "2026-11-20",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@myuser/109876543210",
      "public_access": true,
      "date": "2026-11-20",
      "time": "10:30:01",
      "error": null
    },
    {
      "platform": "Reddit",
      "status": "success",
      "posted_url": "https://www.reddit.com/r/test/comments/abc123/dxora_post/",
      "public_access": true,
      "date": "2026-11-20",
      "time": "10:30:01",
      "error": null
    },
    {
      "platform": "WordPress.com",
      "status": "success",
      "posted_url": "https://mysite.wordpress.com/2026/11/20/dxora-update/",
      "public_access": true,
      "date": "2026-11-20",
      "time": "10:30:02",
      "error": null
    }
  ]
}
```

### cURL — Validation Error

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message": "No link in this message at all"}'
```

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "message"],
      "msg": "Value error, message must contain exactly one CTA link (starting with http:// or https://).",
      "input": "No link in this message at all"
    }
  ]
}
```

---

## Running Tests

The test suite uses `pytest-httpx` to mock all external HTTP calls. No real API credentials are required to run tests.

```bash
# Using Makefile
make test

# Or directly
pytest tests/ -v
```

**What the tests cover:**

| Category | Count | Description |
|---|---|---|
| Input validation | 11 | Empty, too long, no URL, multiple URLs, invalid URL, boundary (200 chars), trailing punctuation |
| PostingService | 5 | Concurrency, failure isolation, exception wrapping, timing, empty-platform guard |
| Pastebin | 3 | Success, API error body, missing credential |
| Telegram | 4 | Public channel, private channel URL correctness, `ok:false`, missing token |
| Mastodon | 3 | Success, https:// prefix normalization, 401 error |
| Reddit | 4 | Success, subreddit name bug regression, token failure, errors array |
| WordPress.com | 3 | Success, 401 error, missing credentials |
| Health endpoint | 3 | Status, structure, platform configuration map |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Invalid input | HTTP 422 with field-level error messages |
| Missing credential | That platform returns `failed` immediately — no HTTP call made |
| Platform API error (4xx/5xx) | Specific, human-readable error message per status code |
| Network timeout | Returns `failed` with timeout message |
| Unexpected exception | Caught by `PostingService`; returned as `failed` result |
| All platforms fail | HTTP 200 with `success: false` and all results |

---

## Design Decisions

**Why `asyncio.gather` with `return_exceptions=True`?**
Running platforms concurrently means total time ≈ slowest platform (not the sum). `return_exceptions=True` ensures that an unhandled exception from one coroutine doesn't cancel the others.

**Why `app.state` instead of a module global?**
FastAPI's `lifespan` context initialises shared objects at startup. Storing them in `app.state` makes them accessible via the `request` object in endpoints and avoids mutable module-level globals, which are an anti-pattern in async applications.

**Why `str.removeprefix` instead of `str.lstrip`?**
`lstrip(chars)` strips individual *characters*, not a prefix string. `"r/rareposts".lstrip("r/")` would strip both `r` and `/` as individual characters, corrupting subreddit names that begin with `r`. `removeprefix("r/")` strips the literal string only once from the start.

**Why is `python-dotenv` not a dependency?**
`pydantic-settings` with `env_file` support handles `.env` loading natively — no extra package needed.

---

## License

MIT License — free to use and modify.

---

*Built for Dxora Technologies — Python Practical Test | Submission Deadline: 22nd November 2026*
