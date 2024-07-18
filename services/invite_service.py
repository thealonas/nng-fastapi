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

    def check_user(self, user_id: int, check_banned: bool = True) -> bool:
        """Check if user exists and is not banned."""
        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            return False
        if check_banned:
            return not user.has_active_violation()
        return True

    async def get_my_code(self, user_id: int) -> MyCodeResponse:
        """Get invite code for a user."""
        if not self.check_user(user_id):
            raise InvalidUserError("Invalid or banned user")

        return MyCodeResponse(code=generate_invite_for_user(user_id))

    async def use_invite(
        self, invite_string: str, user_id: int
    ) -> tuple[UseInviteResponse, bool]:
        """
        Use an invite code.

        Returns tuple of (response, success) where success indicates HTTP 200.
        """
        referral_id = check_invite(invite_string)
        if not referral_id:
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.invalid_or_banned_referral
                ),
                False,
            )

        if not self.check_user(referral_id):
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.invalid_or_banned_referral
                ),
                False,
            )

        try:
            user: User = self.postgres.users.get_user(user_id)
            referral: User = self.postgres.users.get_user(referral_id)
        except ItemNotFoundException:
            return (
                UseInviteResponse(response_type=UseInviteResponseType.invalid_user),
                False,
            )

        if user.user_id == referral.user_id:
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.cannot_invite_yourself,
                    referral_id=referral_id,
                ),
                False,
            )

        if user.has_active_violation():
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.banned_user,
                    referral_id=referral_id,
                ),
                False,
            )

        if user.invited_by:
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.user_already_invited,
                    referral_id=referral_id,
                ),
                False,
            )

        if referral.invited_by == user.user_id:
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.user_is_invited_by_you,
                    referral_id=referral_id,
                ),
                False,
            )

        if not allowed_to_invite(user.trust_info.trust):
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.too_low_trust,
                    referral_id=referral.user_id,
                ),
                False,
            )

        if not allowed_to_invite(referral.trust_info.trust):
            return (
                UseInviteResponse(
                    response_type=UseInviteResponseType.too_low_trust_referral,
                    referral_id=referral.user_id,
                ),
                False,
            )

        user.invited_by = referral.user_id
        self.postgres.users.update_user(user)

        return (
            UseInviteResponse(
                response_type=UseInviteResponseType.success,
                referral_id=referral.user_id,
            ),
            True,
        )

    async def get_users_invited_by_user(self, user_id: int) -> List[User]:
        """Get users invited by a specific user."""
        if not self.check_user(user_id):
            raise InvalidUserError("Invalid or banned user")

        return self.postgres.users.get_invited_users(user_id)
