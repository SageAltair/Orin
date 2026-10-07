from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orin_api.config import get_settings
from orin_api.health.router import router as health_router

settings = get_settings()
app = FastAPI(title="Orin API", version="0.1.0", description="Orin platform API foundation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(health_router)
