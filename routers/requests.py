import datetime
from typing import Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, HTTPException, Depends, Response, BackgroundTasks
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.request import Request, RequestType
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
    ensure_websocket_authorization,
)
from dependencies import get_db, get_response_formatter
from services.ban_service import BanService
from services.request_service import (
    RequestService,
    RequestNotFoundError,
    UserNotFoundError,
    RequestAlreadyAnsweredError,
    RequestWebsocketLog,
    PutRequestResponse,
)
from utils.websocket_logger_manager import WebSocketLoggerManager
from utils.response import ResponseFormatter


class PutRequest(BaseModel):
    request_type: RequestType
    user_id: int
    user_message: str
    vk_comment: Optional[str] = None


class PostChangeRequestIntruder(BaseModel):
    new_intruder: int


class PostRequest(BaseModel):
    answer: Optional[str] = None
    decision: bool
    answered: bool


router = APIRouter()

socket_manager: WebSocketLoggerManager = WebSocketLoggerManager()


@router.get("/requests/list", response_model=list[Request], tags=["requests"])
async def get_requests(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get all unanswered requests."""
    service = RequestService(postgres, socket_manager)
    return await service.get_all_unanswered_requests()


@router.get("/requests/user/{user_id}", response_model=list[Request], tags=["requests"])
async def get_user_requests(
    user_id: int,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get all requests for a user."""
    service = RequestService(postgres, socket_manager)
    return await service.get_user_requests(user_id)


@router.put("/requests/open", response_model=PutRequestResponse, tags=["requests"])
async def open_request(
    response: Response,
    request_data: PutRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Open a new request."""
    service = RequestService(postgres, socket_manager)
    result, status_code = await service.open_request(
        request_data.request_type,
        request_data.user_id,
        request_data.user_message,
        request_data.vk_comment,
    )
    response.status_code = status_code
    return result


@router.get("/requests/request/{request_id}", response_model=Request, tags=["requests"])
async def get_request(
    request_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get a request by ID."""
    service = RequestService(postgres, socket_manager)
    try:
        return await service.get_request(request_id)
    except RequestNotFoundError:
        raise HTTPException(status_code=404, detail="Request not found")


@router.post("/requests/update/{request_id}", tags=["requests"])
async def change_request_status(
    request_id: int,
    status: PostRequest,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Update a request's status."""
    service = RequestService(postgres, socket_manager)
    try:
        request, was_originally_unanswered = await service.update_request_status(
            request_id,
            status.answer,
            status.decision,
            status.answered,
        )
    except RequestNotFoundError:
        raise HTTPException(status_code=404, detail="Request not found")

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
        and was_originally_unanswered
    ):
        await service.try_ban_user_as_teal(
            request.intruder,
            request.vk_comment,
            request_id,
            request.user_id,
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
async def change_intruder(
    data: PostChangeRequestIntruder,
    request_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Change the intruder of a request."""
    service = RequestService(postgres, socket_manager)
    try:
        return await service.change_intruder(request_id, data.new_intruder)
    except RequestNotFoundError:
        raise HTTPException(status_code=404, detail="Request not found")
    except RequestAlreadyAnsweredError:
        raise HTTPException(status_code=400, detail="Request already answered")
    except UserNotFoundError:
        raise HTTPException(status_code=400, detail="User is not presented in DB")


async def try_close(socket: WebSocket):
    """Try to close a websocket connection."""
    try:
        socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/requests/logs")
async def websocket_request_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    """Websocket endpoint for request logs."""
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
