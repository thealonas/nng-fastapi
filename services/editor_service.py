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

