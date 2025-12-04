"""
Admin router module - provides administrative endpoints.
"""

import datetime
from typing import List, Optional, Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_db
from auth.actions import ensure_authorization
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.admin_service import AdminService


class BulkUpdateRequest(BaseModel):
    user_ids: List[int]
    updates: Dict[str, Any]


class PromoteRequest(BaseModel):
    user_id: int


router = APIRouter()


@router.get("/admin/status", tags=["admin"])
async def get_system_status(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    status = await service.get_system_status()
    return status.model_dump()


@router.get("/admin/stats", tags=["admin"])
async def get_admin_stats(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    stats = await service.get_admin_stats()
    return stats.model_dump()


@router.post("/admin/promote", tags=["admin"])
async def promote_user_to_admin(
    request: PromoteRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    success = await service.promote_to_admin(admin_id=0, user_id=request.user_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to promote user")

    return {"detail": f"User {request.user_id} promoted to admin"}


@router.post("/admin/demote", tags=["admin"])
async def demote_user_from_admin(
    request: PromoteRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    success = await service.demote_from_admin(admin_id=0, user_id=request.user_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to demote user")

    return {"detail": f"User {request.user_id} demoted from admin"}


@router.post("/admin/bulk-update", tags=["admin"])
async def bulk_update_users(
    request: BulkUpdateRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    result = await service.bulk_update_users(
        admin_id=0, user_ids=request.user_ids, updates=request.updates
    )
    return result


@router.get("/admin/actions", tags=["admin"])
async def get_admin_actions(
    admin_id: Optional[int] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    actions = await service.get_admin_actions(
        admin_id=admin_id, action_type=action_type, limit=limit
    )

    return {
        "actions": [
            {
                "action_id": a.action_id,
                "admin_id": a.admin_id,
                "action_type": a.action_type,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "details": a.details,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in actions
        ],
        "count": len(actions),
    }


@router.get("/admin/user/{user_id}/summary", tags=["admin"])
async def get_user_summary(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    summary = await service.get_user_activity_summary(user_id)
    return summary


@router.get("/admin/search-logs", tags=["admin"])
async def search_admin_logs(
    query: str,
    limit: int = 50,
    _: Annotated[bool, Depends(ensure_authorization)] = None,
    postgres: NngPostgres = Depends(get_db),
):
    service = AdminService(postgres)
    results = await service.search_admin_logs(query, limit)

    return {
        "results": [
            {
                "action_id": a.action_id,
                "admin_id": a.admin_id,
                "action_type": a.action_type,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in results
        ],
        "count": len(results),
    }
