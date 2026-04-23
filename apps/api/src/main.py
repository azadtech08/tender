"""Main FastAPI application."""

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import create_tables
from middleware.tenant import TenantMiddleware
from routers import auth, billing, exports, health, jobs, tenders, webhooks
from routers import admin_licenses, alerts, api_keys, license as license_router, outbound_webhooks

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Create FastAPI app
app = FastAPI(
    title="GeM Tender SaaS API",
    description="API for GeM Tender scraping and intelligence",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Middleware is processed LIFO — last added runs first (outermost).
# TenantMiddleware must be added FIRST (innermost) so that CORSMiddleware,
# added last, is outermost and handles OPTIONS pre-flights before any
# token parsing is attempted.
app.add_middleware(TenantMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(tenders.router, prefix="/api/tenders", tags=["Tenders"])
app.include_router(exports.router, prefix="/api/exports", tags=["Exports"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API Keys"])
app.include_router(outbound_webhooks.router, prefix="/api/webhooks", tags=["Outbound Webhooks"])
app.include_router(admin_licenses.router, prefix="/api/admin/licenses", tags=["Admin · Licenses"])
app.include_router(license_router.router, prefix="/api/license", tags=["License · Client"])


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    # Create database tables if they don't exist
    await create_tables()


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    pass


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "GeM Tender SaaS API", "version": "0.1.0"}


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    structlog.get_logger().error(
        "Unhandled exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )