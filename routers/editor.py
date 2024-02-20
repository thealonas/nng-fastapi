import asyncio
import datetime
from enum import IntEnum
from typing import Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, Depends
from nng_sdk.logger import get_logger
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import ensure_authorization, ensure_websocket_authorization
from dependencies import get_db
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from nng_sdk.vk.actions import edit_manager, is_in_group, GroupDataResponse
from storage.group_data_storage import GroupDataStorage
from utils.trust_restrictions import get_groups_restriction, allowed_to_receive_editor
from utils.websocket_logger_manager import WebSocketLoggerManager

router = APIRouter()
logger = get_logger()

ws_manager = WebSocketLoggerManager()


class CannotChooseGroup(Exception):
    pass


class OperationStatus(IntEnum):
    join_group = 0
    success = 1
    fail = 2
    cooldown = 3


class GiveEditorRequest(BaseModel):
    user_id: int


class EditorLogType(IntEnum):
    editor_success = 0
    editor_fail_left_group = 1
    editor_fail = 2
    new_ban = 3


class EditorLog(BaseModel):
    user_id: int
    log_type: EditorLogType
    group_id: Optional[int] = None


class GiveEditorResponse(BaseModel):
    status: OperationStatus
    argument: Optional[str] = None


def choose_group(user: User) -> int:
    groups_data: dict[int, GroupDataResponse] = GroupDataStorage().groups
    group_list: list[int] = list(groups_data.keys())

    user_groups = user.groups or []

    potential_groups = [
        group
        for group in group_list
        if group not in user_groups  # группы где чел не редач
    ]

    if not potential_groups:
        raise CannotChooseGroup()

    potential_groups = sorted(
        potential_groups,
        key=lambda group: groups_data[group].managers_count,  # сортировка по редачам
    )

    return potential_groups[0]


def user_on_cooldown(user_id: int, postgres: NngPostgres) -> bool:
    history = postgres.editor_history.get_user_history(user_id)
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
            return True  # 4 часа между выдачами
        else:
            logger.info(f"мимо: delta ({delta}) < {60 * 60 * 4}")

    return False


def safe_give_editor(user_id: int, group_id: int):
    try:
        try_give_editor_and_update_history(user_id, group_id)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return


def try_give_editor_and_update_history(user_id: int, group_id: int):
    postgres = NngPostgres()
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        return

    if user.has_active_violation() or not allowed_to_receive_editor(
        user.trust_info.trust
    ):
        postgres.editor_history.clear_non_granted_items(user.user_id)
        return

    history = postgres.editor_history.get_user_history(user_id)
    if not history or not [
        i for i in history.get_items_from_last_day() if not i.granted
    ]:
        return

    if [i for i in history.history if i.wip]:
        return

    postgres.editor_history.set_wip(user_id, group_id)
    asyncio.run(asyncio.sleep(2))

    if not is_in_group(user_id, group_id):
        postgres.editor_history.clear_wip(user_id)
        asyncio.run(
            ws_manager.broadcast(
                EditorLog(
                    user_id=user_id,
                    log_type=EditorLogType.editor_fail_left_group,
                    group_id=group_id,
                )
            )
        )
        return

    try:
        edit_manager(group_id, user_id, "editor")
        postgres.editor_history.add_granted_item(user_id, group_id)
        asyncio.run(
            ws_manager.broadcast(
                EditorLog(
                    user_id=user_id,
                    log_type=EditorLogType.editor_success,
                    group_id=group_id,
                )
            )
        )
    except Exception as e:
        sentry_sdk.capture_exception(e)
        asyncio.run(
            ws_manager.broadcast(
                EditorLog(user_id=user_id, log_type=EditorLogType.editor_fail)
            )
        )

        postgres.editor_history.add_non_granted_item(user_id, group_id)


async def try_close(socket: WebSocket):
    try:
        ws_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/editor/logs")
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


def is_limited(user: User):
    total_groups = user.groups or []
    return len(total_groups) >= get_groups_restriction(user.trust_info.trust)


@router.post("/editor/give", response_model=GiveEditorResponse, tags=["editor"])
def give_editor(
    request: GiveEditorRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    fail = GiveEditorResponse(status=OperationStatus.fail)

    group_cache = GroupDataStorage()

    try:
        user: User = postgres.users.get_user(request.user_id)
    except ItemNotFoundException:
        fail.argument = "Не удалось подобрать группу 😢"
        return fail

    if user.has_active_violation():
        fail.argument = "Ты заблокирован 🐀"
        return fail

    if user.trust_info.trust <= 10:
        fail.argument = "У тебя слишком низкий траст фактор 😖"
        return fail

    if is_limited(user):
        fail.argument = "Ты достиг лимита групп 🤷‍♂️"
        return fail

    if user_on_cooldown(user.user_id, postgres):
        return GiveEditorResponse(status=OperationStatus.cooldown)

    if postgres.editor_history.is_wip(user.user_id):
        fail.argument = "Выдача уже производится, подожди, пожалуйста ⏳"
        return fail

    history = postgres.editor_history.get_user_history(request.user_id)

    target_group: int = 0

    non_granted_last_day = [
        i for i in history.get_items_from_last_day() if not i.granted
    ]

    if non_granted_last_day:
        target_group = non_granted_last_day[0].group_id

    if target_group == 0:
        try:
            target_group = choose_group(user)
        except CannotChooseGroup:
            fail.argument = "Не удалось подобрать группу 🙁"
            return fail

    postgres.editor_history.set_wip(user.user_id, group_id=target_group)

    group_cache.update_group(target_group)
    group = group_cache.groups[target_group]

    if is_in_group(user_id=user.user_id, group_id=group.group_id):
        edit_manager(target_group, request.user_id, "editor")
        postgres.editor_history.add_granted_item(user.user_id, target_group)
        user.groups.append(target_group)
        postgres.users.update_user(user)
        return GiveEditorResponse(
            status=OperationStatus.success, argument=str(target_group)
        )

    postgres.editor_history.add_non_granted_item(user.user_id, target_group)
    return GiveEditorResponse(
        status=OperationStatus.join_group, argument=str(target_group)
    )
