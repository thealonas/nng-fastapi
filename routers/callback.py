from typing import Optional, Annotated

import nng_sdk.postgres.exceptions
import sentry_sdk
from fastapi import APIRouter, Depends
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_callback_group import OpCallbackGroup
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from onepasswordconnectsdk.client import FailedToRetrieveItemException
from pydantic import BaseModel
from starlette.background import BackgroundTasks
from starlette.responses import PlainTextResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import ensure_websocket_authorization
from routers.editor import (
    safe_give_editor,
)
from utils.websocket_logger_manager import WebSocketLoggerManager

router = APIRouter()


class VkEvent(BaseModel):
    group_id: int
    type: str
    secret: Optional[str] = None
    object: Optional[dict] = None


class GroupOfficersEdit(BaseModel):
    admin_id: int
    user_id: int
    level_old: int
    level_new: int


ws_manager = WebSocketLoggerManager()
op = OpConnect()


@router.post("/callback", tags=["callback"], response_class=PlainTextResponse)
async def post(
    event: VkEvent,
    background_tasks: BackgroundTasks,
):
    logger = get_logger()
    op_group: OpCallbackGroup

    try:
        op_group = op.get_callback_group(event.group_id)
        if not op_group:
            raise FailedToRetrieveItemException()
    except FailedToRetrieveItemException:
        logger.error(f"группы {event.group_id} не было найдено в 1пассе")
        return "ok"

    if not event.secret:
        logger.info("сикрет отсутствует")
        return "ok"

    if event.secret != op_group.secret:
        logger.info(f"сикрет {event.secret} неверный")
        return "ok"

    if event.type == "confirmation":
        return op_group.confirm

    if event.type == "group_join":
        user_id: int = int(event.object["user_id"])
        logger.info(f"{user_id} вступил в {event.group_id}, начинаю обработку")
        background_tasks.add_task(safe_give_editor, user_id, event.group_id)
        return "ok"

    if event.type != "group_officers_edit":
        await ws_manager.broadcast(event)
        return "ok"

    if not event.object:
        return "ok"

    try:
        group_officers_edit: GroupOfficersEdit = GroupOfficersEdit.model_validate(
            event.object
        )
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return "ok"

    postgres = NngPostgres()
    try:
        user: User = postgres.users.get_user(group_officers_edit.user_id)
    except nng_sdk.postgres.exceptions.ItemNotFoundException:
        return "ok"

    if group_officers_edit.level_new == 0:
        user.remove_group(event.group_id)
    else:
        user.add_group(event.group_id)

    try:
        postgres.users.update_user(user)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return "ok"

    await ws_manager.broadcast(event)
    return "ok"


async def try_close(socket: WebSocket):
    try:
        ws_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/callback/logs")
async def websocket_callback_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    await ws_manager.connect(websocket)

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
