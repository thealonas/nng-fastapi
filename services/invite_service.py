from enum import Enum
from typing import List, Optional

from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from pydantic import BaseModel

from utils.invite_crypt import check_invite, generate_invite_for_user
from utils.trust_restrictions import allowed_to_invite


class InviteServiceError(Exception):
    """Base exception for invite service errors."""

    pass


class InvalidUserError(InviteServiceError):
    """Raised when user is invalid or banned."""

    pass


class UseInviteResponseType(Enum):
    """Type of use invite response."""

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
    """Model for use invite response."""

    response_type: UseInviteResponseType
    referral_id: Optional[int] = None


class MyCodeResponse(BaseModel):
    """Model for my code response."""

    code: str


class InviteService:
    """Service class for handling invite-related business logic."""

    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres
