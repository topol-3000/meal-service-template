from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


@router.get("/live")
async def live(request: Request) -> HealthResponse:
    return _ok(request)


@router.get("/ready")
async def ready(request: Request) -> HealthResponse:
    # Add dependency checks (database, Redis) here when the service gets them.
    return _ok(request)


def _ok(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok", service=settings.service_name, version=settings.service_version
    )
