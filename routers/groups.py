from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.group import Group
from pydantic import BaseModel

from auth.actions import ensure_authorization
from dependencies import get_db, get_response_formatter
from services.group_service import GroupService, GroupNotFoundError
from utils.response import ResponseFormatter

router = APIRouter()


class PhotoData(BaseModel):
    server: int
    photo: str
    hash: str


class UploadGroup(BaseModel):
    group: Group
    photo: PhotoData


@router.get("/groups", response_model=list[Group], tags=["groups", "public"])
async def get_groups(
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get all groups."""
    service = GroupService(postgres)
    return await service.get_all_groups()


@router.get("/groups/{group_id}", response_model=Group, tags=["groups"])
async def get_group_by_id(
    group_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get a group by ID."""
    service = GroupService(postgres)
    try:
        return await service.get_group(group_id)
    except GroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")
