"""Worker configuration settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    sync_database_url: str = Field(
        default="postgresql://gem:devpass@localhost:5432/gem_tender",
        env="SYNC_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    environment: str = Field(default="development", env="ENVIRONMENT")

    # Scraper settings
    headless: bool = Field(default=True, env="HEADLESS")
    download_dir: str = Field(default="/tmp/gem_pdfs", env="DOWNLOAD_DIR")

    # S3 / R2 settings (optional — PDFs stored locally if not configured)
    s3_endpoint: str = Field(default="", env="S3_ENDPOINT")
    s3_bucket: str = Field(default="gem-tender-dev", env="S3_BUCKET")
    s3_access_key: str = Field(default="", env="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", env="S3_SECRET_KEY")

    # Email / Resend
    resend_api_key: str = Field(default="", env="RESEND_API_KEY")
    email_from: str = Field(
        default="GeM Tender <noreply@gemtender.com>",
        env="EMAIL_FROM",
    )

    # App base URL (for digest links)
    app_base_url: str = Field(default="http://localhost:3000", env="APP_BASE_URL")

    # Outbound webhook delivery timeout
    webhook_timeout_seconds: int = Field(default=10, env="WEBHOOK_TIMEOUT_SECONDS")

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
