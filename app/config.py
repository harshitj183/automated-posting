"""
Application configuration loaded from environment variables.
Copy .env.example to .env and fill in your credentials before running.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Pastebin ──────────────────────────────────────────────────────────────
    pastebin_api_key: str = ""

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_channel_username: str = ""  # without @, e.g. "mychannel"

    # ── Mastodon ──────────────────────────────────────────────────────────────
    mastodon_instance: str = "mastodon.social"  # e.g. mastodon.social
    mastodon_access_token: str = ""

    # ── Reddit ────────────────────────────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_password: str = ""
    reddit_subreddit: str = ""  # without r/, e.g. "test"

    # ── WordPress.com ─────────────────────────────────────────────────────────
    wordpress_site: str = ""   # e.g. yoursite.wordpress.com
    wordpress_token: str = ""


# Singleton settings instance used throughout the application
settings = Settings()
