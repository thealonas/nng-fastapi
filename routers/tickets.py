import datetime
from enum import IntEnum
from typing import Annotated, Optional

import algoliasearch.exceptions
import sentry_sdk
from algoliasearch.search_client import SearchClient
from algoliasearch.search_index import SearchIndex
from fastapi import APIRouter, Depends, HTTPException
from nng_sdk.logger import get_logger
from nng_sdk.one_password.models.algolia_credentials import AlgoliaCredentials
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.ticket import (
    TicketType,
    TicketStatus,
    TicketMessage,
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
from utils.websocket_logger_manager import WebSocketLoggerManager

logging = get_logger()

algolia_credentials: AlgoliaCredentials = OpConnect().get_algolia_credentials()
algolia: SearchClient = SearchClient.create(
    algolia_credentials.app_id, algolia_credentials.api_key
)
index: SearchIndex = algolia.init_index(algolia_credentials.index_name)

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


class AlgoliaOutput(BaseModel):
    question: str
    answer: str
    attachment: Optional[str] = None
    action: Optional[list] = None


class TicketLogType(IntEnum):
    updated_status = 0
    admin_added_message = 1
    user_added_message = 2


class TicketWebsocketLog(BaseModel):
    log_type: TicketLogType
    ticket_id: int


class UploadMessage(BaseModel):
    author_admin: bool
    message_text: str
    attachments: Optional[list[str]] = None

    def to_ticket_message(
        self, added: datetime.datetime = datetime.datetime.now()
    ) -> TicketMessage:
        return TicketMessage(
            author_admin=self.author_admin,
            message_text=self.message_text,
            attachments=self.attachments or [],
            added=added,
        )


class TicketShort(BaseModel):
    ticket_id: int
    type: TicketType
    status: TicketStatus
    topic: str
    issuer: int
    needs_attention: bool
    opened: datetime.datetime

    @staticmethod
    def _get_topic(ticket: Ticket):
        topic: str = ticket.dialog[0].message_text
        if len(topic) > 30:
            topic = topic[:30] + "..."
        return topic

    @staticmethod
    def _needs_attention(ticket: Ticket):
        ticket.sort_dialogs()
        return not ticket.dialog[-1].author_admin

    @staticmethod
    def from_ticket(ticket: Ticket):
        return TicketShort(
            ticket_id=ticket.ticket_id,
            issuer=ticket.issuer,
            type=ticket.type,
            status=ticket.status,
            topic=TicketShort._get_topic(ticket),
            needs_attention=TicketShort._needs_attention(ticket),
            opened=ticket.opened,
        )


@router.post("/tickets/algolia", response_model=list[AlgoliaOutput], tags=["tickets"])
def algolia_search(
    query: PostAlgoliaQuery, _: Annotated[bool, Depends(ensure_authorization)]
):
    try:
        result = index.search(query.query)
    except algoliasearch.exceptions.AlgoliaException as e:
        sentry_sdk.capture_exception(e)
        return []

    return [
        AlgoliaOutput.model_validate(
            {
                "question": i["question"],
                "answer": i["answer"],
                "attachment": i.get("attachment"),
                "action": i.get("action"),
            }
        )
        for i in result["hits"]
    ]


@router.post("/tickets/ticket/{ticket_id}/update/status", tags=["tickets"])
async def update_status(
    ticket_id: int,
    status: UpdateTicketStatus,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    silent: bool = False,
    postgres: NngPostgres = Depends(get_db),
):
    try:
        ticket = postgres.tickets.get_ticket(ticket_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status == status.status:
        raise HTTPException(status_code=409, detail="Ticket status does not differ")

    if ticket.status == TicketStatus.closed:
        raise HTTPException(status_code=409, detail="Ticket is closed")

    ticket.status = status.status

    if status == TicketStatus.closed:
        ticket.closed = datetime.datetime.now()

    postgres.tickets.upload_or_update_ticket(ticket)

    if not silent:
        await socket_manager.broadcast(
            TicketWebsocketLog(
                log_type=TicketLogType.updated_status,
                ticket_id=ticket_id,
            )
        )

    return {"detail": "Ticket status successfully updated"}


@router.post("/tickets/ticket/{ticket_id}/update/add_message", tags=["tickets"])
async def add_message(
    ticket_id: int,
    message: UploadMessage,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        ticket: Ticket = postgres.tickets.get_ticket(ticket_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.is_closed:
        raise HTTPException(status_code=400, detail="Ticket is closed")

    postgres.tickets.add_message(
        ticket_id, message.to_ticket_message(added=datetime.datetime.now())
    )

    if message.author_admin and ticket.status != TicketStatus.in_review:
        ticket.status = TicketStatus.in_review
        postgres.tickets.upload_or_update_ticket(ticket)

    await socket_manager.broadcast(
        TicketWebsocketLog(
            log_type=(
                TicketLogType.admin_added_message
                if message.author_admin
                else TicketLogType.user_added_message
            ),
            ticket_id=ticket_id,
        )
    )

    return {"detail": "Message successfully added"}


@router.put("/tickets/upload", response_model=Ticket, tags=["tickets"])
def add_ticket(
    issue: PutTicket,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        postgres.users.get_user(issue.user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    return postgres.tickets.upload_or_update_ticket(
        Ticket(
            ticket_id=-1,
            issuer=issue.user_id,
            status=TicketStatus.unreviewed,
            type=issue.type,
            dialog=[
                TicketMessage(
                    author_admin=False,
                    message_text=issue.text,
                    attachments=issue.attachments,
                    added=datetime.datetime.now(),
                )
            ],
            opened=datetime.datetime.now(),
            closed=None,
        )
    )


@router.get(
    "/tickets/user/{user_id}", response_model=list[TicketShort], tags=["tickets"]
)
def get_user_tickets(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    return [
        TicketShort.from_ticket(i)
        for i in postgres.tickets.get_user_tickets(user_id)
        if i.status != TicketStatus.closed
    ]


@router.get("/tickets/get", response_model=list[TicketShort], tags=["tickets"])
def get_all_opened_tickets(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        return [
            TicketShort.from_ticket(i) for i in postgres.tickets.get_opened_tickets()
        ]
    except ItemNotFoundException:
        return []


@router.get("/tickets/ticket/{ticket_id}", response_model=Ticket, tags=["tickets"])
def get_ticket(
    ticket_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        ticket = postgres.tickets.get_ticket(ticket_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Ticket not found")
    else:
        return ticket


async def try_close(socket: WebSocket):
    try:
        await socket_manager.disconnect(socket)
        await socket.close()
    except Exception as e:
        sentry_sdk.capture_exception(e)


@router.websocket("/tickets/logs")
async def websocket_ticket_logs(
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
