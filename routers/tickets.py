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
from dependencies import get_db, get_response_formatter
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
from services.audit_service import audit_service, AuditAction, AuditSeverity
from services.metrics_service import metrics_service
from services.cache_service import cache_instance
from services.logging_service import logging_service
from utils.websocket_logger_manager import WebSocketLoggerManager
from utils.response import ResponseFormatter

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
    query: PostAlgoliaQuery,
    _: Annotated[bool, Depends(ensure_authorization)],
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Search Algolia for FAQ entries."""
    from nng_sdk.postgres.nng_postgres import NngPostgres

    start_time = datetime.datetime.now()
    postgres = NngPostgres()
    service = TicketService(postgres, socket_manager)

    cache_key = f"algolia_search_{query.query}"
    cached = cache_instance.get(cache_key, namespace="tickets")
    if cached:
        await metrics_service.increment(
            "cache_hits", labels={"endpoint": "algolia_search"}
        )
        return cached

    results = await service.search_algolia(query.query)
    cache_instance.set(cache_key, results, ttl=300, namespace="tickets")

    duration = (datetime.datetime.now() - start_time).total_seconds() * 1000
    await metrics_service.timer("algolia_search_duration", duration)
    await logging_service.info(
        f"Algolia search: '{query.query}' returned {len(results)} results"
    )

    return results


@router.post("/tickets/ticket/{ticket_id}/update/status", tags=["tickets"])
async def update_status(
    ticket_id: int,
    status: UpdateTicketStatus,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    silent: bool = False,
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Update a ticket's status."""
    service = TicketService(postgres, socket_manager)
    try:
        await service.update_ticket_status(ticket_id, status.status, silent)

        await audit_service.log(
            action=AuditAction.UPDATE,
            resource_type="ticket",
            resource_id=str(ticket_id),
            severity=AuditSeverity.MEDIUM,
            new_value={"status": str(status.status)},
        )
        await metrics_service.increment(
            "ticket_status_updates", labels={"status": str(status.status)}
        )
        cache_instance.delete(f"ticket_{ticket_id}", namespace="tickets")
        cache_instance.delete("opened_tickets", namespace="tickets")

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
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Add a message to a ticket."""
    service = TicketService(postgres, socket_manager)
    try:
        await service.add_message(ticket_id, message)

        await audit_service.log(
            action=AuditAction.UPDATE,
            resource_type="ticket",
            resource_id=str(ticket_id),
            metadata={"action": "add_message"},
        )
        await metrics_service.increment("ticket_messages_added")
        cache_instance.delete(f"ticket_{ticket_id}", namespace="tickets")

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
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Create a new ticket."""
    service = TicketService(postgres, socket_manager)
    try:
        ticket = await service.create_ticket(
            issue.user_id, issue.type, issue.text, issue.attachments
        )

        await audit_service.log(
            action=AuditAction.TICKET_CREATE,
            resource_type="ticket",
            resource_id=str(ticket.ticket_id),
            severity=AuditSeverity.LOW,
            new_value={"user_id": issue.user_id, "type": str(issue.type)},
        )
        await metrics_service.increment(
            "tickets_created", labels={"type": str(issue.type)}
        )
        await logging_service.info(
            f"Ticket created: {ticket.ticket_id} by user {issue.user_id}"
        )
        cache_instance.delete("opened_tickets", namespace="tickets")
        cache_instance.delete(f"user_tickets_{issue.user_id}", namespace="tickets")

        return ticket
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get(
    "/tickets/user/{user_id}", response_model=list[TicketShort], tags=["tickets"]
)
async def get_user_tickets(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get tickets for a user."""
    service = TicketService(postgres, socket_manager)

    cache_key = f"user_tickets_{user_id}"
    cached = cache_instance.get(cache_key, namespace="tickets")
    if cached:
        return cached

    tickets = await service.get_user_tickets(user_id)
    cache_instance.set(cache_key, tickets, ttl=30, namespace="tickets")
    return tickets


@router.get("/tickets/get", response_model=list[TicketShort], tags=["tickets"])
async def get_all_opened_tickets(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get all opened tickets."""
    service = TicketService(postgres, socket_manager)

    cache_key = "opened_tickets"
    cached = cache_instance.get(cache_key, namespace="tickets")
    if cached:
        return cached

    tickets = await service.get_all_opened_tickets()
    cache_instance.set(cache_key, tickets, ttl=15, namespace="tickets")
    return tickets


@router.get("/tickets/ticket/{ticket_id}", response_model=Ticket, tags=["tickets"])
async def get_ticket(
    ticket_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Get a ticket by ID."""
    service = TicketService(postgres, socket_manager)

    cache_key = f"ticket_{ticket_id}"
    cached = cache_instance.get(cache_key, namespace="tickets")
    if cached:
        return cached

    try:
        ticket = await service.get_ticket(ticket_id)
        cache_instance.set(cache_key, ticket, ttl=30, namespace="tickets")
        return ticket
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
