"""Creative Studio main router: aggregates all creative studio submodules."""
from __future__ import annotations

from fastapi import APIRouter

from orin_api.creative_router_documents import router as documents_router
from orin_api.creative_router_ideas import router as ideas_router

router = APIRouter()
router.include_router(ideas_router)
router.include_router(documents_router)
