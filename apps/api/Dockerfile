FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install db-models (shared package) first
COPY packages/db-models /packages/db-models
RUN pip install --no-cache-dir -e /packages/db-models

# Install API dependencies directly (avoids broken file: reference in pyproject.toml)
RUN pip install --no-cache-dir \
    "fastapi>=0.104.0" \
    "uvicorn[standard]>=0.24.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "python-jose[cryptography]>=3.3.0" \
    "passlib>=1.7.4" \
    "python-multipart>=0.0.6" \
    "httpx>=0.25.0" \
    "structlog>=23.2.0" \
    "python-dotenv>=1.0.0" \
    "openpyxl>=3.1" \
    "celery[redis]>=5.3" \
    "redis>=5.0" \
    "stripe>=7.0" \
    "alembic>=1.13" \
    "psycopg2-binary>=2.9" \
    "boto3>=1.34"

# Copy source last (code changes won't bust the pip cache layer)
COPY apps/api/src /app/src
COPY apps/api/alembic /app/alembic
COPY apps/api/alembic.ini /app/alembic.ini

EXPOSE 8000

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--app-dir", "/app/src"]
