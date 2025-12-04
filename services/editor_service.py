"""
Editor service module - handles all editor-related business logic.

This service extracts editor logic from routes to maintain clean separation of concerns.
"""

import asyncio
import datetime
from enum import IntEnum
from typing import Optional

import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from nng_sdk.vk.actions import edit_manager, is_in_group, GroupDataResponse
from pydantic import BaseModel

from storage.group_data_storage import GroupDataStorage
from utils.trust_restrictions import get_groups_restriction, allowed_to_receive_editor
from utils.websocket_logger_manager import WebSocketLoggerManager

logger = get_logger()


class EditorServiceError(Exception):
    """Base exception for editor service errors."""

    pass


class CannotChooseGroupError(EditorServiceError):
    """Raised when a group cannot be chosen."""

    pass


class UserNotFoundError(EditorServiceError):
    """Raised when a user is not found."""

    pass


class OperationStatus(IntEnum):
    """Status of editor operation."""

    join_group = 0
    success = 1
    fail = 2
    cooldown = 3


class EditorLogType(IntEnum):
    """Type of editor log."""

    editor_success = 0
    editor_fail_left_group = 1
    editor_fail = 2
    new_ban = 3


class EditorLog(BaseModel):
    """Model for editor log."""

    user_id: int
    log_type: EditorLogType
    group_id: Optional[int] = None


class GiveEditorResponse(BaseModel):
    """Model for give editor response."""

    status: OperationStatus
    argument: Optional[str] = None


class EditorService:
    """Service class for handling editor-related business logic."""

    def __init__(
        self,
        postgres: NngPostgres,
        ws_manager: Optional[WebSocketLoggerManager] = None,
    ):
        self.postgres = postgres
        self.ws_manager = ws_manager or WebSocketLoggerManager()

    def choose_group(self, user: User) -> int:
        """Choose a group for the user to be editor in."""
        groups_data: dict[int, GroupDataResponse] = GroupDataStorage().groups
        group_list: list[int] = list(groups_data.keys())

        user_groups = user.groups or []

        potential_groups = [group for group in group_list if group not in user_groups]

        if not potential_groups:
            raise CannotChooseGroupError()

        potential_groups = sorted(
            potential_groups,
            key=lambda group: groups_data[group].managers_count,
        )

        return potential_groups[0]

    def user_on_cooldown(self, user_id: int) -> bool:
        """Check if user is on editor cooldown."""
        history = self.postgres.editor_history.get_user_history(user_id)
        if not history:
            return False

        now = datetime.datetime.now()
        for index, item in enumerate(history.history):
            logger.info(f"итем #{index + 1}/{len(history.history)} юзер {user_id}")
            if not item.granted:
                logger.info(f"не выдано в группе {item.group_id}, пропуск")
                continue

            delta = (now - item.date).total_seconds()

            if delta < 60 * 60 * 4:
                logger.info(f"{user_id} на кулдауне")
                return True
            else:
                logger.info(f"мимо: delta ({delta}) < {60 * 60 * 4}")

        return False

    def is_limited(self, user: User) -> bool:
        """Check if user has reached group limit."""
        total_groups = user.groups or []
        return len(total_groups) >= get_groups_restriction(user.trust_info.trust)

    async def safe_give_editor(self, user_id: int, group_id: int) -> None:
        """Safely try to give editor to user."""
        try:
            await self.try_give_editor_and_update_history(user_id, group_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            return

    async def try_give_editor_and_update_history(
        self, user_id: int, group_id: int
    ) -> None:
        """Try to give editor and update history."""
        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            return

        if user.has_active_violation() or not allowed_to_receive_editor(
            user.trust_info.trust
        ):
            self.postgres.editor_history.clear_non_granted_items(user.user_id)
            return

        history = self.postgres.editor_history.get_user_history(user_id)
        if not history or not [
            i for i in history.get_items_from_last_day() if not i.granted
        ]:
            return

        if [i for i in history.history if i.wip]:
            return

        self.postgres.editor_history.set_wip(user_id, group_id)
        await asyncio.sleep(2)

        if not is_in_group(user_id, group_id):
            self.postgres.editor_history.clear_wip(user_id)
            await self.ws_manager.broadcast(
                EditorLog(
                    user_id=user_id,
                    log_type=EditorLogType.editor_fail_left_group,
                    group_id=group_id,
                )
            )
            return

        try:
            edit_manager(group_id, user_id, "editor")
            self.postgres.editor_history.add_granted_item(user_id, group_id)
            await self.ws_manager.broadcast(
                EditorLog(
                    user_id=user_id,
                    log_type=EditorLogType.editor_success,
                    group_id=group_id,
                )
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await self.ws_manager.broadcast(
                EditorLog(user_id=user_id, log_type=EditorLogType.editor_fail)
            )
            self.postgres.editor_history.add_non_granted_item(user_id, group_id)

    async def give_editor(self, user_id: int) -> GiveEditorResponse:
        """Give editor to a user."""
        fail = GiveEditorResponse(status=OperationStatus.fail)
        group_cache = GroupDataStorage()

        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            fail.argument = "Не удалось подобрать группу 😢"
            return fail

        if user.has_active_violation():
            fail.argument = "Ты заблокирован 🐀"
            return fail

        if user.trust_info.trust <= 10:
            fail.argument = "У тебя слишком низкий траст фактор 😖"
            return fail

        if self.is_limited(user):
            fail.argument = "Ты достиг лимита групп 🤷‍♂️"
            return fail

        if self.user_on_cooldown(user.user_id):
            return GiveEditorResponse(status=OperationStatus.cooldown)

        if self.postgres.editor_history.is_wip(user.user_id):
            fail.argument = "Выдача уже производится, подожди, пожалуйста ⏳"
            return fail

        history = self.postgres.editor_history.get_user_history(user_id)

        target_group: int = 0

        non_granted_last_day = [
            i for i in history.get_items_from_last_day() if not i.granted
        ]

        if non_granted_last_day:
            target_group = non_granted_last_day[0].group_id

        if target_group == 0:
            try:
                target_group = self.choose_group(user)
            except CannotChooseGroupError:
                fail.argument = "Не удалось подобрать группу 🙁"
                return fail

        self.postgres.editor_history.set_wip(user.user_id, group_id=target_group)

        group_cache.update_group(target_group)
        group = group_cache.groups[target_group]

        if is_in_group(user_id=user.user_id, group_id=group.group_id):
            edit_manager(target_group, user_id, "editor")
            self.postgres.editor_history.add_granted_item(user.user_id, target_group)
            user.groups.append(target_group)
            self.postgres.users.update_user(user)
            return GiveEditorResponse(
                status=OperationStatus.success, argument=str(target_group)
            )

        self.postgres.editor_history.add_non_granted_item(user.user_id, target_group)
        return GiveEditorResponse(
            status=OperationStatus.join_group, argument=str(target_group)
        )
