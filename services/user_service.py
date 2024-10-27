import datetime
from typing import List, Optional

import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import (
    User,
    Violation,
    ViolationType,
    TrustInfo,
)
from nng_sdk.vk.actions import (
    get_groups_data,
    GroupDataResponse,
    edit_manager,
    get_user_data,
)
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel
from vk_api import VkApiError

from services.trust_service import TrustService
from utils.trust_restrictions import get_groups_restriction

logger = get_logger()


class UserServiceError(Exception):
    """Base exception for user service errors."""

    pass


class UserNotFoundError(UserServiceError):
    """Raised when a user is not found."""

    pass


class UserAlreadyExistsError(UserServiceError):
    """Raised when trying to create a user that already exists."""

    pass


class UserNotInGroupError(UserServiceError):
    """Raised when a user is not in the specified group."""

    pass


class GroupNotFoundError(UserServiceError):
    """Raised when a group is not found."""

    pass


class VkOperationError(UserServiceError):
    """Raised when a VK API operation fails."""

    pass


class ViolationAddError(UserServiceError):
    """Raised when adding a violation fails."""

    pass


class UserNotBannedError(UserServiceError):
    """Raised when trying to unban a user that is not banned."""

    pass


class BannedUserOutput(BaseModel):
    """Model for banned user output."""

    user_id: int
    name: str
    violations: List[Violation]


class ThxUserOutput(BaseModel):
    """Model for thanks user output."""

    user_id: int
    name: str


class GroupLimitOutput(BaseModel):
    """Model for group limit output."""

    max_groups: int
    user_id: int


class UserService:
    """Service class for handling user-related business logic."""

    def __init__(
        self,
        postgres: NngPostgres,
        vk_manager: Optional[VkManager] = None,
        op_connect: Optional[OpConnect] = None,
    ):
        self.postgres = postgres
        self.vk_manager = vk_manager
        self.op_connect = op_connect

    async def get_banned_users(self) -> List[User]:
        """Get all banned users with active violations."""
        users: List[User] = self.postgres.users.get_banned_users()
        for user in users:
            new_user_violations = [
                i for i in user.violations if i.type == ViolationType.banned
            ]
            user.violations = new_user_violations

        return [i for i in users if i.has_active_violation()]
