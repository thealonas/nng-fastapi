import datetime
from enum import IntEnum
from typing import Annotated, Optional

from typing import Annotated

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.ticket import (
    TicketType,
    TicketStatus,
    Ticket,
)
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from auth.actions import (
    ensure_authorization,
    ensure_websocket_authorization,
    ensure_user_authorization,
)
from dependencies import get_db
from services.ticket_service import (
    TicketService,
    TicketNotFoundError,
    UserNotFoundError,
    TicketClosedError,
    TicketStatusConflictError,
    AlgoliaOutput,
    TicketShort,
    UploadMessage,
)
from utils.websocket_logger_manager import WebSocketLoggerManager

socket_manager: WebSocketLoggerManager = WebSocketLoggerManager()

router = APIRouter()


class PostAlgoliaQuery(BaseModel):
    query: str


class PutTicket(BaseModel):
    user_id: int
    type: TicketType
    text: str
    attachments: list[str] = []


class UpdateTicketStatus(BaseModel):
    status: TicketStatus


@router.post("/tickets/algolia", response_model=list[AlgoliaOutput], tags=["tickets"])
async def algolia_search(
    query: PostAlgoliaQuery, _: Annotated[bool, Depends(ensure_authorization)]
):
    """Search Algolia for FAQ entries."""
    from nng_sdk.postgres.nng_postgres import NngPostgres

    postgres = NngPostgres()
    service = TicketService(postgres, socket_manager)
    return await service.search_algolia(query.query)


@router.post("/tickets/ticket/{ticket_id}/update/status", tags=["tickets"])
async def update_status(
    ticket_id: int,
    status: UpdateTicketStatus,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    silent: bool = False,
    postgres: NngPostgres = Depends(get_db),
):
    """Update a ticket's status."""
    service = TicketService(postgres, socket_manager)
    try:
        await service.update_ticket_status(ticket_id, status.status, silent)
        return {"detail": "Ticket status successfully updated"}
    except TicketNotFoundError:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except TicketStatusConflictError:
        raise HTTPException(status_code=409, detail="Ticket status does not differ")
    except TicketClosedError:
        raise HTTPException(status_code=409, detail="Ticket is closed")


@router.post("/tickets/ticket/{ticket_id}/update/add_message", tags=["tickets"])
async def add_message(
    ticket_id: int,
    message: UploadMessage,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Add a message to a ticket."""
    service = TicketService(postgres, socket_manager)
    try:
        await service.add_message(ticket_id, message)
        return {"detail": "Message successfully added"}
    except TicketNotFoundError:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except TicketClosedError:
        raise HTTPException(status_code=400, detail="Ticket is closed")


@router.put("/tickets/upload", response_model=Ticket, tags=["tickets"])
async def add_ticket(
    issue: PutTicket,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Create a new ticket."""
    service = TicketService(postgres, socket_manager)
    try:
        return await service.create_ticket(
            issue.user_id, issue.type, issue.text, issue.attachments
        )
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get(
    "/tickets/user/{user_id}", response_model=list[TicketShort], tags=["tickets"]
)
async def get_user_tickets(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get tickets for a user."""
    service = TicketService(postgres, socket_manager)
    return await service.get_user_tickets(user_id)


@router.get("/tickets/get", response_model=list[TicketShort], tags=["tickets"])
async def get_all_opened_tickets(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get all opened tickets."""
    service = TicketService(postgres, socket_manager)
    return await service.get_all_opened_tickets()


@router.get("/tickets/ticket/{ticket_id}", response_model=Ticket, tags=["tickets"])
async def get_ticket(
    ticket_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get a ticket by ID."""
    service = TicketService(postgres, socket_manager)
    try:
        return await service.get_ticket(ticket_id)
    except TicketNotFoundError:
        raise HTTPException(status_code=404, detail="Ticket not found")


async def try_close(socket: WebSocket):
    """Try to close a websocket connection."""
    try:
        socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/tickets/logs")
async def websocket_ticket_logs(
    websocket: WebSocket, _: Annotated[bool, Depends(ensure_websocket_authorization)]
):
    """Websocket endpoint for ticket logs."""
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
