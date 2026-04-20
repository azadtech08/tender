# DB Models Package

Shared SQLAlchemy ORM models for the GeM Tender SaaS platform.

## Models

- **User** — User accounts (email, password_hash, display_name)
- **Job** — Scraping jobs (user_id, keywords, status, progress)
- **JobEvent** — Audit log entries for job execution
- **Tender** — Scraped tender records (23 core fields + metadata)
- **Schedule** — Recurring schedules for jobs

## Installation

Install as editable in development:

```bash
pip install -e packages/db-models
```

## Usage

Import models in your application:

```python
from db_models import User, Job, JobEvent, Tender, Schedule, Base
```

Use with SQLAlchemy:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db_models import User

engine = create_engine("postgresql://...")
with Session(engine) as session:
    user = session.query(User).filter_by(email="user@example.com").first()
```

## Migrations

Alembic migrations are in `apps/api/alembic/` and managed by the API package.

```bash
cd apps/api
alembic upgrade head  # Apply migrations
alembic revision --autogenerate -m "description"  # Create new migration
```
