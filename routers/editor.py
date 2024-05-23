from typing import Annotated

import sentry_sdk
from fastapi import APIRouter, Depends
from nng_sdk.postgres.nng_postgres import NngPostgres
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import ensure_authorization, ensure_websocket_authorization
from dependencies import get_db
from services.editor_service import (
    EditorService,
    GiveEditorResponse,
    EditorLog,
    EditorLogType,
)
from utils.websocket_logger_manager import WebSocketLoggerManager

router = APIRouter()

ws_manager = WebSocketLoggerManager()


class GiveEditorRequest(BaseModel):
    user_id: int


async def safe_give_editor_async(user_id: int, group_id: int):
    """Async background task for giving editor to a user."""
    from nng_sdk.postgres.nng_postgres import NngPostgres

    postgres = NngPostgres()
    service = EditorService(postgres, ws_manager)
    await service.safe_give_editor(user_id, group_id)


def safe_give_editor(user_id: int, group_id: int):
    """Sync wrapper for background task compatibility with non-async contexts."""
    import asyncio
    from nng_sdk.postgres.nng_postgres import NngPostgres

    postgres = NngPostgres()
    service = EditorService(postgres, ws_manager)
    asyncio.run(service.safe_give_editor(user_id, group_id))


async def try_close(socket: WebSocket):
    """Try to close a websocket connection."""
    try:
        ws_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/editor/logs")
async def websocket_callback_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    """Websocket endpoint for editor logs."""
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


@router.post("/editor/give", response_model=GiveEditorResponse, tags=["editor"])
async def give_editor(
    request: GiveEditorRequest,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Give editor to a user."""
    service = EditorService(postgres, ws_manager)
    return await service.give_editor(request.user_id)
