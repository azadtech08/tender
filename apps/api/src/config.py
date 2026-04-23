"""Application configuration settings.

All values are read from environment variables (12-factor).
Provide a .env file in development; inject from AWS Secrets Manager in prod.
"""

from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://gem:devpass@localhost:5432/gem_tender",
        env="DATABASE_URL",
    )
    sync_database_url: Optional[str] = Field(
        default=None,
        env="SYNC_DATABASE_URL",
    )

    # ── JWT (local dev fallback — unused when CLERK_JWKS_URL is set) ─────────
    jwt_secret_key: str = Field(
        default="dev-only-change-in-production",
        env="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, env="JWT_EXPIRATION_HOURS")

    # ── Clerk (Phase 2+) ──────────────────────────────────────────────────────
    # When set, token verification switches from local HS256 to Clerk RS256.
    clerk_jwks_url: Optional[str] = Field(
        default=None,
        env="CLERK_JWKS_URL",
    )
    clerk_issuer: Optional[str] = Field(
        default=None,
        env="CLERK_ISSUER",
    )
    clerk_secret_key: Optional[str] = Field(
        default=None,
        env="CLERK_SECRET_KEY",
    )

    # ── Stripe (Phase 2+) ─────────────────────────────────────────────────────
    stripe_secret_key: Optional[str] = Field(
        default=None,
        env="STRIPE_SECRET_KEY",
    )
    stripe_webhook_secret: Optional[str] = Field(
        default=None,
        env="STRIPE_WEBHOOK_SECRET",
    )
    # Stripe Price IDs for each subscription plan.
    stripe_price_starter: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_STARTER"
    )
    stripe_price_pro: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_PRO"
    )
    stripe_price_business: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_BUSINESS"
    )
    # Metered overage price IDs.
    stripe_price_run_meter: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_RUN_METER"
    )
    stripe_price_tender_meter: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_TENDER_METER"
    )
    stripe_price_ai_meter: Optional[str] = Field(
        default=None, env="STRIPE_PRICE_AI_METER"
    )

    # ── S3 / Cloudflare R2 storage ────────────────────────────────────────────
    s3_endpoint: Optional[str] = Field(default=None, env="S3_ENDPOINT")
    s3_bucket: str = Field(default="gem-tender-dev", env="S3_BUCKET")
    s3_access_key: Optional[str] = Field(default=None, env="S3_ACCESS_KEY")
    s3_secret_key: Optional[str] = Field(default=None, env="S3_SECRET_KEY")

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # ── Email / Resend (Phase 3+) ──────────────────────────────────────────────
    resend_api_key: Optional[str] = Field(default=None, env="RESEND_API_KEY")
    email_from: str = Field(
        default="GeM Tender <noreply@gemtender.com>",
        env="EMAIL_FROM",
    )

    # ── Outbound webhooks (Phase 3+) ──────────────────────────────────────────
    webhook_timeout_seconds: int = Field(default=10, env="WEBHOOK_TIMEOUT_SECONDS")

    # ── Application ───────────────────────────────────────────────────────────
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    app_base_url: str = Field(
        default="http://localhost:3000",
        env="APP_BASE_URL",
    )

    # ── API server ────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_workers: int = Field(default=1, env="API_WORKERS")

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        env="CORS_ORIGINS",
    )

    # ── Licensing (Phase 3+) ──────────────────────────────────────────────────
    # Active key ID used when signing newly minted license tokens.
    license_active_kid: str = Field(default="v1", env="LICENSE_ACTIVE_KID")
    # Path inside the container to the public verifying key (Phase 5 will use this).
    license_public_key_path: str = Field(
        default="/keys/signing_public_v1.pem",
        env="LICENSE_PUBLIC_KEY_PATH",
    )
    # Path to private key on disk (dev). When unset, falls back to Secrets Manager.
    license_private_key_path: Optional[str] = Field(
        default=None,
        env="LICENSE_PRIVATE_KEY_PATH",
    )
    # AWS Secrets Manager secret ID holding the private signing key (prod).
    license_signing_key_secret_id: str = Field(
        default="tenzo/licensing/signing_key_v1",
        env="LICENSE_SIGNING_KEY_SECRET_ID",
    )
    # Token TTL — 30 days max (Phase 0 §3.2 LOCKED).
    license_token_ttl_seconds: int = Field(
        default=30 * 24 * 60 * 60, env="LICENSE_TOKEN_TTL_SECONDS"
    )
    # Heartbeat cadence — 6 hours (Phase 0 §3.1 LOCKED).
    license_heartbeat_interval_seconds: int = Field(
        default=6 * 60 * 60, env="LICENSE_HEARTBEAT_INTERVAL_SECONDS"
    )
    # Activation rate limits.
    license_activate_rate_per_ip_per_min: int = Field(
        default=5, env="LICENSE_ACTIVATE_RATE_PER_IP_PER_MIN"
    )
    license_activate_rate_per_key_per_day: int = Field(
        default=10, env="LICENSE_ACTIVATE_RATE_PER_KEY_PER_DAY"
    )

    # ── Admin access control (Phase 3+) ───────────────────────────────────────
    # Comma-separated CIDR list. Empty => skip IP check (dev convenience).
    admin_ip_allowlist: list[str] = Field(
        default_factory=list,
        env="ADMIN_IP_ALLOWLIST",
    )
    # Comma-separated user IDs that count as admin in local-dev / test mode.
    # In Clerk mode, role is read from public_metadata.role == 'tenzo_admin'.
    local_admin_user_ids: list[str] = Field(
        default_factory=list,
        env="LOCAL_ADMIN_USER_IDS",
    )
    # Whether to require Clerk 2FA for admin endpoints (default off — flip in prod).
    admin_require_2fa: bool = Field(default=False, env="ADMIN_REQUIRE_2FA")

    # ── License enforcement mode (Phase 5+) ────────────────────────────────────
    # 'off'     — no enforcement, every route passes (default; safe ship)
    # 'warn'    — log denials, but still serve the request
    # 'enforce' — 402/429 on license violations
    # Phase 0 §8 rollout: ship 'off' → flip 'warn' for a week → flip 'enforce'.
    licensing_mode: str = Field(default="off", env="LICENSING_MODE")

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @computed_field
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }


settings = Settings()
