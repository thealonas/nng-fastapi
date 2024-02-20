import datetime
from typing import Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, HTTPException, Depends, Response, BackgroundTasks
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.request import Request, RequestType
from nng_sdk.pydantic_models.user import User, Violation, ViolationType
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
    ensure_websocket_authorization,
)
from dependencies import get_db
from services.ban_service import BanService
from utils.users_utils import try_ban_user_as_teal
from utils.websocket_logger_manager import (
    WebSocketLoggerManager,
)

TEAL_OR_ORANGE = "С твоим приоритетом подавать запрос на разблокировку нельзя"
NOT_FIRST_VIOLATION = "Нельзя подавать еще один запрос после первого нарушения"
UNEXPIRED_VIOLATION = "С момента твоего нарушения прошло меньше года"
TOO_LOW_TRUST = "Твой траст фактор недостаточен для подачи запроса"
TOO_TOXIC = "Большинство оставленных тобой комментариев были отмечены как токсичные"
ANOTHER_REQUEST_WAS_OPENED = "Ты уже подавал запрос на разблокировку"
USER_NOT_FOUND = "Внутренняя ошибка"


class RequestWebsocketLog(BaseModel):
    request_id: int
    send_to_user: int


class PutRequest(BaseModel):
    request_type: RequestType
    user_id: int
    user_message: str
    vk_comment: Optional[str] = None


class PostChangeRequestIntruder(BaseModel):
    new_intruder: int


class PutRequestResponse(BaseModel):
    response: str
    success: bool
    request_id: Optional[int] = None


class PostRequest(BaseModel):
    answer: Optional[str] = None
    decision: bool
    answered: bool


logger = get_logger()

router = APIRouter()

socket_manager: WebSocketLoggerManager = WebSocketLoggerManager()


@router.get("/requests/list", response_model=list[Request], tags=["requests"])
def get_requests(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    return postgres.requests.get_all_unanswered_requests()


@router.get("/requests/user/{user_id}", response_model=list[Request], tags=["requests"])
def get_user_requests(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    return postgres.requests.get_user_requests(user_id)


def throw_for_request_duplicates(req: PutRequest, user: User, postgres: NngPostgres):
    if req.request_type is not RequestType.unblock:
        return

    user_requests: list[Request] = postgres.requests.get_user_requests(user.user_id)

    if user_requests:
        for request in user_requests:
            if (
                request.answered
                and request.request_type is RequestType.unblock
                and not request.decision
                and (datetime.date.today() - request.created_on)
                < datetime.timedelta(days=365)
            ):
                raise HTTPException(
                    status_code=400, detail="Another request has already been received"
                )
    return


def auto_deny_request(request: Request, user: User) -> Request:
    if request.request_type is not RequestType.unblock:
        return request

    violation: Violation

    try:
        violation = user.get_active_violation()
    except RuntimeError:
        return request

    is_first_violation = (
        len([i for i in user.violations if i.type == ViolationType.banned]) <= 1
    )

    more_than_year_ago: bool | None = (
        True
        if violation.date
        and (datetime.date.today() - violation.date) > datetime.timedelta(days=365)
        else False if violation.date else None
    )

    is_toxic = user.trust_info.toxicity > 75

    answer: str = (
        NOT_FIRST_VIOLATION
        if not is_first_violation
        else (
            UNEXPIRED_VIOLATION
            if (more_than_year_ago == False)
            else TOO_TOXIC if is_toxic else ""
        )
    )

    if not is_first_violation or (more_than_year_ago == False) or is_toxic:
        request.answer = answer
        request.answered = True
        request.decision = False

    return request


@router.put("/requests/open", response_model=PutRequestResponse, tags=["requests"])
async def open_request(
    response: Response,
    request_data: PutRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(request_data.user_id)
    except ItemNotFoundException:
        response.status_code = 404
        return PutRequestResponse(response=USER_NOT_FOUND, success=False)

    try:
        throw_for_request_duplicates(request_data, user, postgres)
    except HTTPException:
        return PutRequestResponse(response=ANOTHER_REQUEST_WAS_OPENED, success=False)

    request = Request(
        request_type=request_data.request_type,
        created_on=datetime.date.today(),
        user_id=request_data.user_id,
        user_message=request_data.user_message,
        vk_comment=(
            request_data.vk_comment
            if request_data.request_type is RequestType.complaint
            else None
        ),
        answer="",
        decision=False,
        answered=False,
    )

    request = auto_deny_request(request, user)

    new_request: Request = postgres.requests.upload_or_update_request(request)

    if new_request.answered:
        await socket_manager.broadcast(
            RequestWebsocketLog(
                request_id=new_request.request_id, send_to_user=new_request.user_id
            )
        )

    return PutRequestResponse(
        response="success", success=True, request_id=new_request.request_id
    )


@router.get("/requests/request/{request_id}", response_model=Request, tags=["requests"])
def get_request(
    request_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        request = postgres.requests.get_request(request_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Request not found")
    else:
        return request


@router.post("/requests/update/{request_id}", tags=["requests"])
async def change_request_status(
    request_id: int,
    status: PostRequest,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        request: Request = postgres.requests.get_request(request_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Request not found")

    if status.answer:
        request.answer = status.answer

    original_answered = request.answered

    request.decision = status.decision
    request.answered = status.answered

    postgres.requests.upload_or_update_request(request)

    if (
        request.request_type is RequestType.unblock
        and request.answered
        and request.decision
    ):
        ban_service = BanService(postgres, VkManager(), OpConnect())
        background_tasks.add_task(ban_service.amnesty_user, request.user_id)

    if (
        request.request_type is RequestType.complaint
        and request.answered
        and request.vk_comment
        and request.decision
        and request.intruder
        and not original_answered
    ):
        try_ban_user_as_teal(
            request.intruder,
            request.vk_comment,
            request_id,
            request.user_id,
            postgres,
        )

    await socket_manager.broadcast(
        RequestWebsocketLog(
            request_id=request_id,
            send_to_user=request.user_id,
        )
    )

    return {"detail": "Request status changed"}


@router.post(
    "/requests/change_intruder/{request_id}", response_model=Request, tags=["requests"]
)
def change_intruder(
    data: PostChangeRequestIntruder,
    request_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        request: Request = postgres.requests.get_request(request_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.answered:
        raise HTTPException(status_code=400, detail="Request already answered")

    try:
        postgres.users.get_user(data.new_intruder)
    except ItemNotFoundException:
        raise HTTPException(status_code=400, detail="User is not presented in DB")

    request.intruder = data.new_intruder
    postgres.requests.upload_or_update_request(request)

    return request


async def try_close(socket: WebSocket):
    try:
        await socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/requests/logs")
async def websocket_request_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    await socket_manager.connect(websocket)

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
