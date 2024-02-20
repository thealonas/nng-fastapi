from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Response
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from pydantic import BaseModel

from auth.actions import ensure_authorization
from dependencies import get_db
from utils.invite_crypt import check_invite, generate_invite_for_user
from utils.trust_restrictions import allowed_to_invite


class InviteForm(BaseModel):
    invite_string: str
    user: int


class UseInviteResponseType(Enum):
    invalid_or_banned_referral = 0
    invalid_user = 1
    banned_user = 2
    user_already_invited = 3
    cannot_invite_yourself = 4
    user_is_invited_by_you = 5
    success = 6
    too_low_trust = 7
    too_low_trust_referral = 8


class UseInviteResponse(BaseModel):
    response_type: UseInviteResponseType
    referral_id: Optional[int] = None


class MyCodeResponse(BaseModel):
    code: str


router = APIRouter()


def check_user(user: int, postgres: NngPostgres, check_bnnd: bool = True) -> bool:
    try:
        user: User = postgres.users.get_user(user)
    except ItemNotFoundException:
        return False
    if check_bnnd:
        return not user.has_active_violation()
    return True


@router.get(
    "/invites/get_my_code/{user_id}", tags=["invites"], response_model=MyCodeResponse
)
def get_my_code(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    if not check_user(user_id, postgres):
        raise HTTPException(status_code=400, detail="Invalid or banned user")

    return MyCodeResponse(code=generate_invite_for_user(user_id))


@router.post("/invites/use", tags=["invites"], response_model=UseInviteResponse)
def use_invite(
    form: InviteForm,
    response: Response,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    response.status_code = 400

    referral_id = check_invite(form.invite_string)
    if not referral_id:
        return UseInviteResponse(
            response_type=UseInviteResponseType.invalid_or_banned_referral
        )

    if not check_user(referral_id, postgres):
        return UseInviteResponse(
            response_type=UseInviteResponseType.invalid_or_banned_referral
        )

    try:
        user: User = postgres.users.get_user(form.user)
        referral: User = postgres.users.get_user(referral_id)
    except ItemNotFoundException:
        return UseInviteResponse(response_type=UseInviteResponseType.invalid_user)

    if user.user_id == referral.user_id:
        return UseInviteResponse(
            response_type=UseInviteResponseType.cannot_invite_yourself,
            referral_id=referral_id,
        )

    if user.has_active_violation():
        return UseInviteResponse(
            response_type=UseInviteResponseType.banned_user, referral_id=referral_id
        )

    if user.invited_by:
        return UseInviteResponse(
            response_type=UseInviteResponseType.user_already_invited,
            referral_id=referral_id,
        )

    if referral.invited_by == user.user_id:
        return UseInviteResponse(
            response_type=UseInviteResponseType.user_is_invited_by_you,
            referral_id=referral_id,
        )

    if not allowed_to_invite(user.trust_info.trust):
        return UseInviteResponse(
            response_type=UseInviteResponseType.too_low_trust,
            referral_id=referral.user_id,
        )

    if not allowed_to_invite(referral.trust_info.trust):
        return UseInviteResponse(
            response_type=UseInviteResponseType.too_low_trust_referral,
            referral_id=referral.user_id,
        )

    response.status_code = 200

    user.invited_by = referral.user_id
    postgres.users.update_user(user)

    return UseInviteResponse(
        response_type=UseInviteResponseType.success,
        referral_id=referral.user_id,
    )


@router.get("/invites/referral/{user_id}", tags=["invites"], response_model=list[User])
def get_users_invited_by_user(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    if not check_user(user_id, postgres):
        raise HTTPException(status_code=400, detail="Invalid or banned user")

    return postgres.users.get_invited_users(user_id)
