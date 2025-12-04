import datetime
from enum import IntEnum
from typing import List, Optional

import sentry_sdk
from algoliasearch.search_client import SearchClient
from algoliasearch.search_index import SearchIndex
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

from utils.websocket_logger_manager import WebSocketLoggerManager


class TicketServiceError(Exception):
    """Base exception for ticket service errors."""

    pass


class TicketNotFoundError(TicketServiceError):
    """Raised when a ticket is not found."""

    pass


class UserNotFoundError(TicketServiceError):
    """Raised when a user is not found."""

    pass


class TicketClosedError(TicketServiceError):
    """Raised when trying to modify a closed ticket."""

    pass


class TicketStatusConflictError(TicketServiceError):
    """Raised when there's a status conflict."""

    pass


class AlgoliaOutput(BaseModel):
    """Model for Algolia search output."""

    question: str
    answer: str
    attachment: Optional[str] = None
    action: Optional[list] = None


class TicketLogType(IntEnum):
    """Type of ticket log."""

    updated_status = 0
    admin_added_message = 1
    user_added_message = 2


class TicketWebsocketLog(BaseModel):
    """Model for ticket websocket log."""

    log_type: TicketLogType
    ticket_id: int


class TicketShort(BaseModel):
    """Short model for ticket list."""

    ticket_id: int
    type: TicketType
    status: TicketStatus
    topic: str
    issuer: int
    needs_attention: bool
    opened: datetime.datetime

    @staticmethod
    def _get_topic(ticket: Ticket) -> str:
        topic: str = ticket.dialog[0].message_text
        if len(topic) > 30:
            topic = topic[:30] + "..."
        return topic

    @staticmethod
    def _needs_attention(ticket: Ticket) -> bool:
        ticket.sort_dialogs()
        return not ticket.dialog[-1].author_admin

    @staticmethod
    def from_ticket(ticket: Ticket) -> "TicketShort":
        return TicketShort(
            ticket_id=ticket.ticket_id,
            issuer=ticket.issuer,
            type=ticket.type,
            status=ticket.status,
            topic=TicketShort._get_topic(ticket),
            needs_attention=TicketShort._needs_attention(ticket),
            opened=ticket.opened,
        )


class UploadMessage(BaseModel):
    """Model for uploading a message."""

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


class TicketService:
    """Service class for handling ticket-related business logic."""

    def __init__(
        self,
        postgres: NngPostgres,
        ws_manager: Optional[WebSocketLoggerManager] = None,
        algolia_index: Optional[SearchIndex] = None,
    ):
        self.postgres = postgres
        self.ws_manager = ws_manager or WebSocketLoggerManager()
        self._algolia_index = algolia_index

    @property
    def algolia_index(self) -> SearchIndex:
        """Get or create Algolia index."""
        if self._algolia_index is None:
            algolia_credentials: AlgoliaCredentials = (
                OpConnect().get_algolia_credentials()
            )
            algolia: SearchClient = SearchClient.create(
                algolia_credentials.app_id, algolia_credentials.api_key
            )
            self._algolia_index = algolia.init_index(algolia_credentials.index_name)
        return self._algolia_index

    async def search_algolia(self, query: str) -> List[AlgoliaOutput]:
        """Search Algolia for FAQ entries."""
        try:
            result = self.algolia_index.search(query)
        except Exception as e:
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

    async def update_ticket_status(
        self, ticket_id: int, status: TicketStatus, silent: bool = False
    ) -> None:
        """Update a ticket's status."""
        try:
            ticket = self.postgres.tickets.get_ticket(ticket_id)
        except ItemNotFoundException:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        if ticket.status == status:
            raise TicketStatusConflictError("Ticket status does not differ")

        if ticket.status == TicketStatus.closed:
            raise TicketClosedError("Ticket is closed")

        ticket.status = status

        if status == TicketStatus.closed:
            ticket.closed = datetime.datetime.now()

        self.postgres.tickets.upload_or_update_ticket(ticket)

        if not silent:
            await self.ws_manager.broadcast(
                TicketWebsocketLog(
                    log_type=TicketLogType.updated_status,
                    ticket_id=ticket_id,
                )
            )

    async def add_message(self, ticket_id: int, message: UploadMessage) -> None:
        """Add a message to a ticket."""
        try:
            ticket: Ticket = self.postgres.tickets.get_ticket(ticket_id)
        except ItemNotFoundException:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")

        if ticket.is_closed:
            raise TicketClosedError("Ticket is closed")

        self.postgres.tickets.add_message(
            ticket_id, message.to_ticket_message(added=datetime.datetime.now())
        )

        if message.author_admin and ticket.status != TicketStatus.in_review:
            ticket.status = TicketStatus.in_review
            self.postgres.tickets.upload_or_update_ticket(ticket)

        await self.ws_manager.broadcast(
            TicketWebsocketLog(
                log_type=(
                    TicketLogType.admin_added_message
                    if message.author_admin
                    else TicketLogType.user_added_message
                ),
                ticket_id=ticket_id,
            )
        )

    async def create_ticket(
        self,
        user_id: int,
        ticket_type: TicketType,
        text: str,
        attachments: List[str],
    ) -> Ticket:
        """Create a new ticket."""
        try:
            self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

        return self.postgres.tickets.upload_or_update_ticket(
            Ticket(
                ticket_id=-1,
                issuer=user_id,
                status=TicketStatus.unreviewed,
                type=ticket_type,
                dialog=[
                    TicketMessage(
                        author_admin=False,
                        message_text=text,
                        attachments=attachments,
                        added=datetime.datetime.now(),
                    )
                ],
                opened=datetime.datetime.now(),
                closed=None,
            )
        )

    async def get_user_tickets(self, user_id: int) -> List[TicketShort]:
        """Get tickets for a user."""
        return [
            TicketShort.from_ticket(i)
            for i in self.postgres.tickets.get_user_tickets(user_id)
            if i.status != TicketStatus.closed
        ]

    async def get_all_opened_tickets(self) -> List[TicketShort]:
        """Get all opened tickets."""
        try:
            return [
                TicketShort.from_ticket(i)
                for i in self.postgres.tickets.get_opened_tickets()
            ]
        except ItemNotFoundException:
            return []

    async def get_ticket(self, ticket_id: int) -> Ticket:
        """Get a ticket by ID."""
        try:
            return self.postgres.tickets.get_ticket(ticket_id)
        except ItemNotFoundException:
            raise TicketNotFoundError(f"Ticket {ticket_id} not found")
