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

    async def get_thx_users(self) -> List[User]:
        """Get all users eligible for thanks."""
        return self.postgres.users.get_thx_users()

    async def get_user(self, user_id: int) -> User:
        """Get a user by ID."""
        try:
            return self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

    async def search_users(self, query: str) -> List[User]:
        """Search users by query."""
        if not query:
            return []
        return self.postgres.users.search_users(query)

    async def create_user(
        self, user_id: int, name: Optional[str] = None
    ) -> User:
        """Create a new user."""
        try:
            self.postgres.users.get_user(user_id)
            raise UserAlreadyExistsError(f"User {user_id} already exists")
        except ItemNotFoundException:
            pass

        if not name:
            try:
                user_vk_data = get_user_data(user_id)
                name = f"{user_vk_data['first_name']} {user_vk_data['last_name']}"
            except Exception as e:
                sentry_sdk.capture_exception(e)
                raise VkOperationError("User doesn't exist in VK")

        trust = 40
        user = User(
            user_id=user_id,
            name=name,
            admin=False,
            trust=trust,
            invited_by=None,
            trust_info=TrustInfo.create_default(),
            join_date=datetime.date.today(),
            groups=[],
            violations=[],
        )
        self.postgres.users.add_user(user)
        return user

    async def fire_user(self, user_id: int, group_id: int) -> str:
        """Fire a user from a group."""
        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

        if not user.groups or group_id not in user.groups:
            raise UserNotInGroupError(f"User {user_id} is not in group {group_id}")

        group_data = get_groups_data([group_id])
        if group_id not in group_data.keys():
            raise GroupNotFoundError(f"Group {group_id} not found")

        group: GroupDataResponse = group_data[group_id]
        if user.user_id not in [i["id"] for i in group.managers]:
            user.groups.remove(group_id)
            self.postgres.users.update_user(user)
            return "User fired only in db"

        try:
            edit_manager(group.group_id, user.user_id, None)
        except VkApiError as e:
            sentry_sdk.capture_exception(e)
            raise VkOperationError("Error while firing user")

        user.groups.remove(group_id)
        self.postgres.users.update_user(user)
        return "User fired successfully"

    async def restore_user(self, user_id: int, group_id: int) -> str:
        """Restore a user to a group."""
        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

        group_data = get_groups_data([group_id])
        if group_id not in group_data.keys():
            raise GroupNotFoundError(f"Group {group_id} not found")

        group: GroupDataResponse = group_data[group_id]
        if user.user_id in [i["id"] for i in group.managers]:
            user.groups.append(group_id)
            self.postgres.users.update_user(user)
            return "User restored only in db"

        try:
            edit_manager(group.group_id, user.user_id, "editor")
        except VkApiError as e:
            sentry_sdk.capture_exception(e)
            raise VkOperationError("Error while restoring user")

        user.groups.append(group_id)
        self.postgres.users.update_user(user)
        return "User restored successfully"

    async def update_user(
        self,
        user_id: int,
        name: Optional[str] = None,
        admin: Optional[bool] = None,
        groups: Optional[List[int]] = None,
        activism: Optional[bool] = None,
        donate: Optional[bool] = None,
    ) -> User:
        """Update a user's information."""
        try:
            db_user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

        if name:
            db_user.name = name

        if admin is not None:
            db_user.admin = admin

        if activism is not None:
            db_user.trust_info.activism = activism

        if donate is not None:
            db_user.trust_info.donate = donate

        if groups is not None:
            db_user.groups = groups

        self.postgres.users.update_user(db_user)
        return db_user
