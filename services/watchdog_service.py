import asyncio
import datetime
from enum import StrEnum
from typing import List, Optional

import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import (
    BanPriority,
    Violation,
    User,
    ViolationType,
)
from nng_sdk.pydantic_models.watchdog import Watchdog
from pydantic import BaseModel

from utils.websocket_logger_manager import WebSocketLoggerManager

logger = get_logger()


class WatchdogServiceError(Exception):
    """Base exception for watchdog service errors."""

    pass


class WatchdogNotFoundError(WatchdogServiceError):
    """Raised when a watchdog log is not found."""

    pass


class UserNotFoundError(WatchdogServiceError):
    """Raised when a user is not found."""

    pass


class WatchdogWebsocketLogType(StrEnum):
    """Type of watchdog websocket log."""

    new_warning = "new_warning"
    new_ban = "new_ban"


class WatchdogWebsocketLog(BaseModel):
    """Model for watchdog websocket log."""

    type: WatchdogWebsocketLogType
    priority: BanPriority
    group: int
    send_to_user: int


class WatchdogService:
    """Service class for handling watchdog-related business logic."""

    def __init__(
        self,
        postgres: NngPostgres,
        ws_manager: Optional[WebSocketLoggerManager] = None,
    ):
        self.postgres = postgres
        self.ws_manager = ws_manager or WebSocketLoggerManager()

    async def get_all_unreviewed_logs(self) -> List[Watchdog]:
        """Get all unreviewed watchdog logs."""
        return self.postgres.watchdog.get_all_unreviewed_logs()

    async def get_log(self, watchdog_id: int) -> Watchdog:
        """Get a watchdog log by ID."""
        try:
            return self.postgres.watchdog.get_log(watchdog_id)
        except ItemNotFoundException:
            raise WatchdogNotFoundError(f"Watchdog log {watchdog_id} not found")

    def _is_valid_green(self, violation: Violation) -> bool:
        """Check if a violation is a valid green warning."""
        if (
            violation.type != ViolationType.warned
            or violation.priority != BanPriority.green
        ):
            return False

        return not violation.is_expired()

    async def _ban_and_send_log(
        self,
        user: User,
        new_violation: Violation,
        group_id: int,
    ) -> None:
        """Ban user and send log notification."""
        try:
            self.postgres.users.add_violation(user.user_id, new_violation)
            log_type = (
                WatchdogWebsocketLogType.new_ban
                if new_violation.type == ViolationType.banned
                else WatchdogWebsocketLogType.new_warning
            )

            logger.info(f"broadcasting {log_type}...")
            await self.ws_manager.broadcast(
                WatchdogWebsocketLog(
                    type=log_type,
                    priority=BanPriority.green,
                    group=group_id,
                    send_to_user=user.user_id,
                )
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

    async def try_ban_as_green(
        self, user: User, watchdog_id: int, group_id: int
    ) -> None:
        """Try to ban a user with green priority."""
        violations: list[Violation] = user.violations
        violation = Violation(
            type=ViolationType.warned,
            group_id=group_id,
            priority=BanPriority.green,
            watchdog_ref=watchdog_id,
            date=datetime.date.today(),
        )

        if len([v for v in violations if self._is_valid_green(v)]) < 2:
            await self._ban_and_send_log(user, violation, group_id)
            return

        violation.type = ViolationType.banned
        violation.active = True

        await self._ban_and_send_log(user, violation, group_id)

    def _check_violation_exists(self, user_id: int, group_id: int) -> bool:
        """Check if a violation already exists for user in group today."""
        violations: list[Violation] = self.postgres.users.get_user(user_id).violations
        current_date = datetime.date.today()
        for violation in violations:
            if (
                violation.group_id == group_id
                and violation.active
                and violation.date == current_date
            ):
                return True
        return False

    async def try_ban_and_notify_user(
        self,
        user_id: int,
        watchdog_id: int,
        priority: BanPriority,
        group_id: int,
    ) -> None:
        """Try to ban user and notify them."""
        try:
            user = self.postgres.users.get_user(user_id)
        except ItemNotFoundException as e:
            sentry_sdk.capture_exception(e)
            return

        if priority == BanPriority.green:
            await self.try_ban_as_green(user, watchdog_id, group_id)
            return

        if self._check_violation_exists(user_id, group_id):
            return

        self.postgres.users.add_violation(
            user.user_id,
            Violation(
                type=ViolationType.banned,
                group_id=group_id,
                priority=priority,
                watchdog_ref=watchdog_id,
                active=True,
                date=datetime.date.today(),
            ),
        )

        await self.ws_manager.broadcast(
            WatchdogWebsocketLog(
                type=WatchdogWebsocketLogType.new_ban,
                priority=priority,
                group=group_id,
                send_to_user=user.user_id,
            )
        )

    def check_and_throw_user(self, user_id: int) -> bool:
        """Check if user exists, raise error if not."""
        try:
            self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")
        else:
            return True

    async def update_watchdog_log(
        self,
        watchdog_id: int,
        intruder: Optional[int] = None,
        group_id: Optional[int] = None,
        victim: Optional[int] = None,
        date: Optional[datetime.date] = None,
        reviewed: Optional[bool] = None,
    ) -> tuple[Watchdog, bool]:
        """
        Update a watchdog log.

        Returns tuple of (log, needs_ban_task).
        """
        try:
            log: Watchdog = self.postgres.watchdog.get_log(watchdog_id)
        except ItemNotFoundException:
            raise WatchdogNotFoundError(f"Watchdog log {watchdog_id} not found")

        needs_ban_task = False

        if group_id:
            log.group_id = group_id

        if intruder and log.intruder is None:
            self.check_and_throw_user(intruder)
            log.intruder = intruder
            needs_ban_task = True

        if victim:
            self.check_and_throw_user(victim)
            log.victim = victim

        if date:
            log.date = date

        if reviewed:
            log.reviewed = reviewed

        self.postgres.watchdog.upload_or_update_log(log)
        return log, needs_ban_task

    async def add_watchdog_log(
        self,
        intruder: Optional[int],
        victim: Optional[int],
        group_id: int,
        priority: BanPriority,
        date: datetime.date,
        reviewed: bool = False,
    ) -> Watchdog:
        """Add a new watchdog log."""
        new_watchdog = Watchdog(
            watchdog_id=-1,
            intruder=intruder,
            victim=victim,
            group_id=group_id,
            priority=priority,
            date=date,
            reviewed=reviewed,
        )

        return self.postgres.watchdog.upload_or_update_log(new_watchdog)

    async def notify_user(self, log: WatchdogWebsocketLog) -> None:
        """Send notification to user via websocket."""
        try:
            self.postgres.users.get_user(log.send_to_user)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {log.send_to_user} not found")

        await self.ws_manager.broadcast(log)
