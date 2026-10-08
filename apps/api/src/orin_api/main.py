from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from orin_api.config import get_settings
from orin_api.auth_router import router as auth_router
from orin_api.domain_router import router as domain_router
from orin_api.health.router import router as health_router
from orin_api.worker_router import router as worker_router

settings = get_settings()
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


@app.middleware("http")
async def disable_api_caching(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
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
