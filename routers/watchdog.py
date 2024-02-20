import asyncio
import datetime
from enum import StrEnum
from typing import Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from nng_sdk.logger import get_logger
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect, WebSocket

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
    ensure_websocket_authorization,
)
from dependencies import get_db
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import BanPriority, Violation, User, ViolationType
from nng_sdk.pydantic_models.watchdog import Watchdog
from utils.websocket_logger_manager import WebSocketLoggerManager

router = APIRouter()
watchdog_socket_manager = WebSocketLoggerManager()


class WatchdogWebsocketLogType(StrEnum):
    new_warning = "new_warning"
    new_ban = "new_ban"


class WatchdogWebsocketLog(BaseModel):
    type: WatchdogWebsocketLogType
    priority: BanPriority
    group: int
    send_to_user: int


class WatchdogAdditionalInfo(BaseModel):
    intruder: Optional[int] = None
    group_id: Optional[int] = None
    victim: Optional[int] = None
    date: Optional[datetime.date] = None
    reviewed: Optional[bool] = None


class PutWatchdog(BaseModel):
    intruder: Optional[int] = None
    victim: Optional[int] = None
    group_id: int
    priority: BanPriority
    date: datetime.date
    reviewed: bool = False


@router.get("/watchdog/list", response_model=list[Watchdog], tags=["watchdog"])
def get_watchdog_logs(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    return postgres.watchdog.get_all_unreviewed_logs()


@router.get("/watchdog/get/{watchdog_id}", response_model=Watchdog, tags=["watchdog"])
def get_watchdog_by_id(
    watchdog_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        watchdog: Watchdog = postgres.watchdog.get_log(watchdog_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Watchdog log not found")
    return watchdog


def is_valid_green(violation: Violation):
    if (
        violation.type != ViolationType.warned
        or violation.priority != BanPriority.green
    ):
        return False

    return not violation.is_expired()


def try_ban_as_green(
    user: User, watchdog_id: int, group_id: int, postgres: NngPostgres
):
    logger = get_logger()

    async def ban_and_send_log(new_violation: Violation):
        try:
            postgres.users.add_violation(user.user_id, new_violation)
            log_type = (
                WatchdogWebsocketLogType.new_ban
                if new_violation.type == ViolationType.banned
                else WatchdogWebsocketLogType.new_warning
            )

            logger.info(f"broadcasting {log_type}...")
            await watchdog_socket_manager.broadcast(
                WatchdogWebsocketLog(
                    type=log_type,
                    priority=BanPriority.green,
                    group=group_id,
                    send_to_user=user.user_id,
                )
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

    violations: list[Violation] = user.violations
    violation = Violation(
        type=ViolationType.warned,
        group_id=group_id,
        priority=BanPriority.green,
        watchdog_ref=watchdog_id,
        date=datetime.date.today(),
    )

    if len([v for v in violations if is_valid_green(v)]) < 2:
        asyncio.run(ban_and_send_log(violation))
        return

    violation.type = ViolationType.banned
    violation.active = True

    asyncio.run(ban_and_send_log(violation))


def check_violation_exists(user_id: int, group_id: int, postgres: NngPostgres):
    violations: list[Violation] = postgres.users.get_user(user_id).violations
    current_date = datetime.date.today()
    for violation in violations:
        if (
            violation.group_id == group_id
            and violation.active
            and violation.date == current_date
        ):
            return True
    return False


def try_ban_and_notify_user(
    user_id: int,
    watchdog_id: int,
    priority: BanPriority,
    group_id: int,
):
    postgres = NngPostgres()

    try:
        user = postgres.users.get_user(user_id)
    except ItemNotFoundException as e:
        sentry_sdk.capture_exception(e)
        return

    if priority == BanPriority.green:
        try_ban_as_green(user, watchdog_id, group_id, postgres)
        return

    if check_violation_exists(user_id, group_id, postgres):
        return

    postgres.users.add_violation(
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

    asyncio.run(
        watchdog_socket_manager.broadcast(
            WatchdogWebsocketLog(
                type=WatchdogWebsocketLogType.new_ban,
                priority=priority,
                group=group_id,
                send_to_user=user.user_id,
            )
        )
    )


def check_and_throw_user(user_id: int, postgres: NngPostgres) -> bool:
    try:
        postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")
    else:
        return True


@router.post("/watchdog/update/{watchdog_id}", tags=["watchdog"])
def post_watchdog_additional_info(
    watchdog_id: int,
    info: WatchdogAdditionalInfo,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        log: Watchdog = postgres.watchdog.get_log(watchdog_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Watchdog log not found")

    if info.group_id:
        log.group_id = info.group_id

    if info.intruder and log.intruder is None:
        check_and_throw_user(info.intruder, postgres)
        log.intruder = info.intruder
        background_tasks.add_task(
            try_ban_and_notify_user,
            log.intruder,
            log.watchdog_id,
            log.priority,
            log.group_id,
        )

    if info.victim:
        check_and_throw_user(info.victim, postgres)
        log.victim = info.victim

    if info.date:
        log.date = info.date

    if info.reviewed:
        log.reviewed = info.reviewed

    postgres.watchdog.upload_or_update_log(log)
    return {"detail": "Log was successfully updated"}


@router.put("/watchdog/add", tags=["watchdog"], response_model=Watchdog)
def add_watchdog_log(
    watchdog: PutWatchdog,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    new_watchdog = Watchdog(
        watchdog_id=-1,
        intruder=watchdog.intruder,
        victim=watchdog.victim,
        group_id=watchdog.group_id,
        priority=watchdog.priority,
        date=watchdog.date,
        reviewed=watchdog.reviewed,
    )

    retrieved_watchdog = postgres.watchdog.upload_or_update_log(new_watchdog)
    return retrieved_watchdog


@router.post("/watchdog/notify_user", tags=["watchdog"])
async def notify_user(
    log: WatchdogWebsocketLog,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        postgres.users.get_user(log.send_to_user)
    except ItemNotFoundException:
        raise HTTPException(status_code=400, detail="User not found")

    await watchdog_socket_manager.broadcast(log)
    return {"detail": "Log was successfully sent"}


async def try_close(socket: WebSocket):
    try:
        watchdog_socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/watchdog/logs")
async def websocket_watchdog_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    await watchdog_socket_manager.connect(websocket)

    while True:
        try:
            await websocket.receive()
        except WebSocketDisconnect:
            await try_close(websocket)
            return
        except Exception as e:
            await try_close(websocket)
            sentry_sdk.capture_exception(e)
            return
