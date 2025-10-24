import asyncio
import datetime
from typing import Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from nng_sdk.pydantic_models.user import BanPriority
from nng_sdk.pydantic_models.watchdog import Watchdog
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect, WebSocket

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
    ensure_websocket_authorization,
)
from dependencies import get_db, get_response_formatter
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.watchdog_service import (
    WatchdogService,
    WatchdogNotFoundError,
    UserNotFoundError,
    WatchdogWebsocketLog,
)
from utils.websocket_logger_manager import WebSocketLoggerManager
from utils.response import ResponseFormatter

router = APIRouter()
watchdog_socket_manager = WebSocketLoggerManager()


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
async def get_watchdog_logs(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get all unreviewed watchdog logs."""
    service = WatchdogService(postgres, watchdog_socket_manager)
    return await service.get_all_unreviewed_logs()


@router.get("/watchdog/get/{watchdog_id}", response_model=Watchdog, tags=["watchdog"])
async def get_watchdog_by_id(
    watchdog_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get a watchdog log by ID."""
    service = WatchdogService(postgres, watchdog_socket_manager)
    try:
        return await service.get_log(watchdog_id)
    except WatchdogNotFoundError:
        raise HTTPException(status_code=404, detail="Watchdog log not found")


async def _try_ban_and_notify_user(
    user_id: int,
    watchdog_id: int,
    priority: BanPriority,
    group_id: int,
):
    """Background task to ban user and notify them."""
    from nng_sdk.postgres.nng_postgres import NngPostgres

    postgres = NngPostgres()
    service = WatchdogService(postgres, watchdog_socket_manager)
    await service.try_ban_and_notify_user(user_id, watchdog_id, priority, group_id)


@router.post("/watchdog/update/{watchdog_id}", tags=["watchdog"])
async def post_watchdog_additional_info(
    watchdog_id: int,
    info: WatchdogAdditionalInfo,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Update a watchdog log with additional info."""
    service = WatchdogService(postgres, watchdog_socket_manager)
    try:
        log, needs_ban_task = await service.update_watchdog_log(
            watchdog_id,
            intruder=info.intruder,
            group_id=info.group_id,
            victim=info.victim,
            date=info.date,
            reviewed=info.reviewed,
        )
        if needs_ban_task and log.intruder:
            background_tasks.add_task(
                _try_ban_and_notify_user,
                log.intruder,
                log.watchdog_id,
                log.priority,
                log.group_id,
            )
        return {"detail": "Log was successfully updated"}
    except WatchdogNotFoundError:
        raise HTTPException(status_code=404, detail="Watchdog log not found")
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.put("/watchdog/add", tags=["watchdog"], response_model=Watchdog)
async def add_watchdog_log(
    watchdog: PutWatchdog,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Add a new watchdog log."""
    service = WatchdogService(postgres, watchdog_socket_manager)
    return await service.add_watchdog_log(
        intruder=watchdog.intruder,
        victim=watchdog.victim,
        group_id=watchdog.group_id,
        priority=watchdog.priority,
        date=watchdog.date,
        reviewed=watchdog.reviewed,
    )


@router.post("/watchdog/notify_user", tags=["watchdog"])
async def notify_user(
    log: WatchdogWebsocketLog,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Send notification to user via websocket."""
    service = WatchdogService(postgres, watchdog_socket_manager)
    try:
        await service.notify_user(log)
        return {"detail": "Log was successfully sent"}
    except UserNotFoundError:
        raise HTTPException(status_code=400, detail="User not found")


async def try_close(socket: WebSocket):
    """Try to close a websocket connection."""
    try:
        watchdog_socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/watchdog/logs")
async def websocket_watchdog_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    """Websocket endpoint for watchdog logs."""
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
