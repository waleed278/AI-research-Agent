from fastapi import APIRouter

from app.api.v1.routes import research

# Deliberately excludes health.router: liveness/readiness probes (see
# app/main.py) are mounted unversioned at the root, not under /api/v1 --
# an orchestrator's health check shouldn't need to track API versioning.
api_router = APIRouter()
api_router.include_router(research.router)
