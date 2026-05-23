"""Tenant middleware — extracts tenant_id from JWT and stores it on request.state.

This runs on every request BEFORE route handlers execute.  Route handlers
that use `get_db_rls` will then issue `SET LOCAL app.tenant_id = '...'`
inside the database session, activating the Postgres RLS policies installed
by migration 003.

Design notes:
- If the token is absent or invalid we do NOT raise 401 here; that is the
  job of `get_current_user` in each route's Depends().  We simply set
  request.state.tenant_id to None so that RLS will see no tenant and return
  zero rows — a safe default.
- This middleware MUST run after the CORS middleware so that OPTIONS
  pre-flight requests pass through without token validation.
"""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from auth import verify_token

_log = structlog.get_logger()


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # OPTIONS pre-flight requests must pass through immediately so that
        # CORSMiddleware (outermost) can respond without any token parsing.
        if request.method == "OPTIONS":
            return await call_next(request)

        tenant_id: str | None = None

        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer "):]
                token_data = verify_token(token)
                if token_data:
                    tenant_id = token_data.tenant_id

            # Also accept ?token= query param (SSE EventSource path).
            if tenant_id is None:
                token_param = request.query_params.get("token")
                if token_param:
                    token_data = verify_token(token_param)
                    if token_data:
                        tenant_id = token_data.tenant_id
        except Exception as exc:
            # Never let token-parsing errors crash the request — auth
            # enforcement is the responsibility of each route's Depends().
            _log.warning("tenant_middleware.verify_token_error", error=str(exc))

        request.state.tenant_id = tenant_id
        return await call_next(request)
