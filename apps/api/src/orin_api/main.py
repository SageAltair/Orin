from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
import logging
import time
import uuid

from orin_api.config import get_settings
from orin_api.auth_router import router as auth_router
from orin_api.domain_router import router as domain_router
from orin_api.health.router import router as health_router
from orin_api.worker_router import router as worker_router
from orin_api.workspace_router import router as workspace_router
from orin_api.integration_router import router as integration_router

settings = get_settings()
logger = logging.getLogger("orin_api.request")
app = FastAPI(title="Orin API", version="0.1.0", description="Orin platform API foundation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(domain_router)
app.include_router(worker_router)
app.include_router(workspace_router)
app.include_router(integration_router)


@app.middleware("http")
async def disable_api_caching(request: Request, call_next: RequestResponseEndpoint) -> Response:
    started = time.perf_counter()
    try:
        request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
    except ValueError:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.error("api_request_complete request_id=%s route=unhandled status=500 duration_ms=%.2f",
            request_id, (time.perf_counter() - started) * 1000)
        raise
    route = request.scope.get("route")
    route_template = getattr(route, "path", "unmatched")
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info("api_request_complete request_id=%s route=%s status=%d duration_ms=%.2f",
        request_id, route_template, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic errors include the submitted input by default; never echo passwords or tokens.
    errors = [
        {"loc": list(error.get("loc", ())), "msg": "Invalid value", "type": error.get("type", "value_error")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})
