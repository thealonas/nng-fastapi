from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.group import Group
from pydantic import BaseModel

from auth.actions import ensure_authorization
from dependencies import get_db

router = APIRouter()


class PhotoData(BaseModel):
    server: int
    photo: str
    hash: str


class UploadGroup(BaseModel):
    group: Group
    photo: PhotoData


@router.get("/groups", response_model=list[Group], tags=["groups", "public"])
def get_groups(postgres: NngPostgres = Depends(get_db)):
    return postgres.groups.get_all_groups()


@router.get("/groups/{group_id}", response_model=Group, tags=["groups"])
def get_group_by_id(
    group_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        return postgres.groups.get_group(group_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Group not found")
