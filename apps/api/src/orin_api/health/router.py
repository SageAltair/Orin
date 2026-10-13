from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from orin_api.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str


@router.get("/live", response_model=HealthStatus)
def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready", response_model=HealthStatus)
def ready(session: Session = Depends(get_session)) -> HealthStatus:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    return HealthStatus(status="ok")
