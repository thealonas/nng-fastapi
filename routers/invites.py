from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Response
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from pydantic import BaseModel

from auth.actions import ensure_authorization
from dependencies import get_db
from services.invite_service import (
    InviteService,
    InvalidUserError,
    UseInviteResponse,
    UseInviteResponseType,
    MyCodeResponse,
)


class InviteForm(BaseModel):
    invite_string: str
    user: int


router = APIRouter()


@router.get(
    "/invites/get_my_code/{user_id}", tags=["invites"], response_model=MyCodeResponse
)
async def get_my_code(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get invite code for a user."""
    service = InviteService(postgres)
    try:
        return await service.get_my_code(user_id)
    except InvalidUserError:
        raise HTTPException(status_code=400, detail="Invalid or banned user")


@router.post("/invites/use", tags=["invites"], response_model=UseInviteResponse)
async def use_invite(
    form: InviteForm,
    response: Response,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Use an invite code."""
    service = InviteService(postgres)
    result, success = await service.use_invite(form.invite_string, form.user)
    response.status_code = 200 if success else 400
    return result


@router.get("/invites/referral/{user_id}", tags=["invites"], response_model=list[User])
async def get_users_invited_by_user(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get users invited by a specific user."""
    service = InviteService(postgres)
    try:
        return await service.get_users_invited_by_user(user_id)
    except InvalidUserError:
        raise HTTPException(status_code=400, detail="Invalid or banned user")
