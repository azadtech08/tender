FROM python:3.12-slim

WORKDIR /app

# System deps: psycopg2 + Playwright/Chromium runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install db-models (shared package) first
COPY packages/db-models /packages/db-models
RUN pip install --no-cache-dir -e /packages/db-models

# Install worker Python dependencies directly (avoids the broken file: reference
# in pyproject.toml which uses a relative path that doesn't exist in Docker)
RUN pip install --no-cache-dir \
    "celery[redis]>=5.3" \
    "sqlalchemy>=2.0" \
    "psycopg2-binary>=2.9" \
    "pydantic-settings>=2.0" \
    "structlog>=23.2.0" \
    "python-dotenv>=1.0.0" \
    "playwright>=1.44" \
    "playwright-stealth>=1.0.6" \
    "pdfplumber>=0.11" \
    "requests>=2.31" \
    "boto3>=1.34" \
    "httpx>=0.25"

# Download Chromium browser binary
RUN playwright install chromium

# Copy worker source last (code changes won't bust the pip cache layer)
COPY apps/worker/src /app/src

ENV PYTHONPATH=/app/src
ENV DOWNLOAD_DIR=/tmp/gem_pdfs

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]
