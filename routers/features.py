"""
Feature flags router module - provides feature flag management endpoints.
"""

import datetime
from typing import Optional, Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.actions import ensure_authorization
from services.feature_flag_service import (
    FeatureFlagService,
    feature_flags,
    FeatureStatus,
)


class FeatureFlagCreate(BaseModel):
    name: str
    description: str = ""
    status: str = "disabled"
    percentage: float = 0.0
    enabled_users: List[int] = []
    enabled_groups: List[str] = []


class FeatureFlagUpdate(BaseModel):
    status: Optional[str] = None
    percentage: Optional[float] = None
    enabled_users: Optional[List[int]] = None
    enabled_groups: Optional[List[str]] = None
    description: Optional[str] = None


class FeatureFlagEvaluate(BaseModel):
    user_id: Optional[int] = None
    user_group: Optional[str] = None


router = APIRouter()


def parse_status(value: str) -> FeatureStatus:
    mapping = {
        "enabled": FeatureStatus.ENABLED,
        "disabled": FeatureStatus.DISABLED,
        "percentage": FeatureStatus.PERCENTAGE,
        "user_list": FeatureStatus.USER_LIST,
        "group_list": FeatureStatus.GROUP_LIST,
    }
    return mapping.get(value, FeatureStatus.DISABLED)


@router.get("/features", tags=["features"])
async def list_feature_flags(_: Annotated[bool, Depends(ensure_authorization)]):
    flags = feature_flags.get_all_flags()

    return {
        "flags": [
            {
                "name": f.name,
                "description": f.description,
                "status": f.status.value,
                "percentage": f.percentage,
                "enabled_users_count": len(f.enabled_users),
                "enabled_groups_count": len(f.enabled_groups),
                "created_at": f.created_at.isoformat(),
                "updated_at": f.updated_at.isoformat(),
            }
            for f in flags
        ],
        "count": len(flags),
    }


@router.get("/features/{flag_name}", tags=["features"])
async def get_feature_flag(
    flag_name: str, _: Annotated[bool, Depends(ensure_authorization)]
):
    flag = feature_flags.get_flag(flag_name)

    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")

    return {
        "name": flag.name,
        "description": flag.description,
        "status": flag.status.value,
        "percentage": flag.percentage,
        "enabled_users": flag.enabled_users,
        "enabled_groups": flag.enabled_groups,
        "metadata": flag.metadata,
        "created_at": flag.created_at.isoformat(),
        "updated_at": flag.updated_at.isoformat(),
    }


@router.post("/features", tags=["features"])
async def create_feature_flag(
    request: FeatureFlagCreate, _: Annotated[bool, Depends(ensure_authorization)]
):
    try:
        flag = feature_flags.create_flag(
            name=request.name,
            description=request.description,
            status=parse_status(request.status),
            percentage=request.percentage,
            enabled_users=request.enabled_users,
            enabled_groups=request.enabled_groups,
        )

        return {"created": True, "name": flag.name, "status": flag.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/features/{flag_name}", tags=["features"])
async def update_feature_flag(
    flag_name: str,
    request: FeatureFlagUpdate,
    _: Annotated[bool, Depends(ensure_authorization)],
):
    status = parse_status(request.status) if request.status else None

    flag = feature_flags.update_flag(
        name=flag_name,
        status=status,
        percentage=request.percentage,
        enabled_users=request.enabled_users,
        enabled_groups=request.enabled_groups,
        description=request.description,
    )

    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")

    return {"updated": True, "name": flag.name, "status": flag.status.value}


@router.delete("/features/{flag_name}", tags=["features"])
async def delete_feature_flag(
    flag_name: str, _: Annotated[bool, Depends(ensure_authorization)]
):
    success = feature_flags.delete_flag(flag_name)

    if not success:
        raise HTTPException(status_code=404, detail="Feature flag not found")

    return {"deleted": True, "name": flag_name}


@router.post("/features/{flag_name}/evaluate", tags=["features"])
async def evaluate_feature_flag(
    flag_name: str,
    request: FeatureFlagEvaluate,
    _: Annotated[bool, Depends(ensure_authorization)],
):
    evaluation = feature_flags.evaluate(
        name=flag_name, user_id=request.user_id, user_group=request.user_group
    )

    return {
        "flag_name": evaluation.flag_name,
        "enabled": evaluation.enabled,
        "reason": evaluation.reason,
        "evaluated_at": evaluation.evaluated_at.isoformat(),
    }


@router.post("/features/{flag_name}/enable", tags=["features"])
async def enable_feature_flag(
    flag_name: str, _: Annotated[bool, Depends(ensure_authorization)]
):
    success = feature_flags.enable_flag(flag_name)

    if not success:
        raise HTTPException(status_code=404, detail="Feature flag not found")

    return {"enabled": True, "name": flag_name}


@router.post("/features/{flag_name}/disable", tags=["features"])
async def disable_feature_flag(
    flag_name: str, _: Annotated[bool, Depends(ensure_authorization)]
):
    success = feature_flags.disable_flag(flag_name)

    if not success:
        raise HTTPException(status_code=404, detail="Feature flag not found")

    return {"disabled": True, "name": flag_name}


@router.get("/features/{flag_name}/check", tags=["features", "public"])
async def check_feature_enabled(
    flag_name: str, user_id: Optional[int] = None, user_group: Optional[str] = None
):
    enabled = feature_flags.is_enabled(
        name=flag_name, user_id=user_id, user_group=user_group
    )

    return {"flag": flag_name, "enabled": enabled}


@router.get("/features/stats/overview", tags=["features"])
async def get_feature_stats(_: Annotated[bool, Depends(ensure_authorization)]):
    return feature_flags.get_stats()
