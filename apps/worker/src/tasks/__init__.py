# Explicitly import all task modules so Celery registers them
# regardless of autodiscover path resolution.
from tasks import scheduler, scrape_job, digest, webhook_fire  # noqa: F401
