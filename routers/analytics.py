"""
Analytics router module - provides analytics and metrics endpoints.
"""

import datetime
from typing import List, Dict, Any, Optional, Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from dependencies import get_db
from auth.actions import ensure_authorization
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.stats_service import StatsService, MetricType


class MetricInput(BaseModel):
    name: str
    value: float
    metric_type: str = "counter"
    labels: Dict[str, str] = {}


class DateRange(BaseModel):
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None


router = APIRouter()


@router.get("/analytics/overview", tags=["analytics"])
async def get_analytics_overview(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    snapshot = await service.get_system_snapshot()
    
    return {
        "snapshot": snapshot.model_dump(),
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.get("/analytics/users", tags=["analytics"])
async def get_user_analytics(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    snapshot = await service.get_system_snapshot()
    
    active_rate = (snapshot.active_users / snapshot.total_users * 100) if snapshot.total_users > 0 else 0
    banned_rate = (snapshot.banned_users / snapshot.total_users * 100) if snapshot.total_users > 0 else 0
    
    return {
        "total_users": snapshot.total_users,
        "active_users": snapshot.active_users,
        "banned_users": snapshot.banned_users,
        "active_rate": round(active_rate, 2),
        "banned_rate": round(banned_rate, 2),
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.get("/analytics/groups", tags=["analytics"])
async def get_group_analytics(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    snapshot = await service.get_system_snapshot()
    
    return {
        "total_groups": snapshot.total_groups,
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.get("/analytics/tickets", tags=["analytics"])
async def get_ticket_analytics(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    snapshot = await service.get_system_snapshot()
    
    return {
        "open_tickets": snapshot.open_tickets,
        "pending_requests": snapshot.pending_requests,
        "timestamp": datetime.datetime.now().isoformat()
    }


@router.get("/analytics/user/{user_id}", tags=["analytics"])
async def get_user_activity_analytics(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    
    try:
        user_stats = await service.get_user_activity_stats(user_id)
        return user_stats.model_dump()
    except Exception as e:
        return {"error": str(e)}


@router.post("/analytics/metrics", tags=["analytics"])
async def record_metric(
    metric: MetricInput,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    
    metric_type = MetricType(metric.metric_type) if metric.metric_type in [e.value for e in MetricType] else MetricType.COUNTER
    
    recorded = service.record_metric(
        name=metric.name,
        value=metric.value,
        metric_type=metric_type,
        labels=metric.labels
    )
    
    return {
        "recorded": True,
        "metric": recorded.name,
        "value": recorded.value,
        "timestamp": recorded.timestamp.isoformat()
    }


@router.get("/analytics/metrics", tags=["analytics"])
async def get_metrics(
    name: Optional[str] = None,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    metrics = service.get_metrics(name)
    
    return {
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "type": m.metric_type.value,
                "labels": m.labels,
                "timestamp": m.timestamp.isoformat()
            }
            for m in metrics
        ],
        "count": len(metrics)
    }


@router.get("/analytics/dashboard", tags=["analytics"])
async def get_dashboard_data(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db)
):
    service = StatsService(postgres)
    snapshot = await service.get_system_snapshot()
    
    return {
        "summary": {
            "users": {
                "total": snapshot.total_users,
                "active": snapshot.active_users,
                "banned": snapshot.banned_users
            },
            "groups": {
                "total": snapshot.total_groups
            },
            "support": {
                "open_tickets": snapshot.open_tickets,
                "pending_requests": snapshot.pending_requests
            }
        },
        "generated_at": datetime.datetime.now().isoformat()
    }
