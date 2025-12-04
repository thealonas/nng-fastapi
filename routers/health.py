"""
Health check router module - provides system health monitoring endpoints.
"""

import datetime
import platform
import sys
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dependencies import get_db
from nng_sdk.postgres.nng_postgres import NngPostgres


class ComponentHealth(BaseModel):
    name: str
    status: str
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = {}
    last_check: datetime.datetime = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.last_check is None:
            self.last_check = datetime.datetime.now()


class SystemInfo(BaseModel):
    python_version: str
    platform: str
    hostname: str
    uptime_seconds: float


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime.datetime
    version: str
    components: List[ComponentHealth]
    system: SystemInfo


class ReadinessResponse(BaseModel):
    ready: bool
    checks: Dict[str, bool]


class LivenessResponse(BaseModel):
    alive: bool
    timestamp: datetime.datetime


router = APIRouter()

_start_time = datetime.datetime.now()


def get_system_info() -> SystemInfo:
    uptime = (datetime.datetime.now() - _start_time).total_seconds()

    return SystemInfo(
        python_version=sys.version,
        platform=platform.platform(),
        hostname=platform.node(),
        uptime_seconds=uptime,
    )


async def check_database_health(postgres: NngPostgres) -> ComponentHealth:
    start = datetime.datetime.now()
    try:
        postgres.groups.get_all_groups()
        latency = (datetime.datetime.now() - start).total_seconds() * 1000
        return ComponentHealth(
            name="database",
            status="healthy",
            latency_ms=latency,
            details={"connected": True},
        )
    except Exception as e:
        latency = (datetime.datetime.now() - start).total_seconds() * 1000
        return ComponentHealth(
            name="database",
            status="unhealthy",
            latency_ms=latency,
            details={"connected": False, "error": str(e)},
        )


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check(postgres: NngPostgres = Depends(get_db)):
    components = []

    db_health = await check_database_health(postgres)
    components.append(db_health)

    components.append(
        ComponentHealth(
            name="api", status="healthy", details={"endpoints_loaded": True}
        )
    )

    overall_status = (
        "healthy" if all(c.status == "healthy" for c in components) else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.datetime.now(),
        version="1.0.0",
        components=components,
        system=get_system_info(),
    )


@router.get("/health/live", response_model=LivenessResponse, tags=["health"])
async def liveness_check():
    return LivenessResponse(alive=True, timestamp=datetime.datetime.now())


@router.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
async def readiness_check(postgres: NngPostgres = Depends(get_db)):
    checks = {}

    try:
        postgres.groups.get_all_groups()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    checks["api"] = True

    ready = all(checks.values())

    return ReadinessResponse(ready=ready, checks=checks)


@router.get("/health/info", tags=["health"])
async def system_info():
    return {
        "system": get_system_info().model_dump(),
        "timestamp": datetime.datetime.now().isoformat(),
    }
