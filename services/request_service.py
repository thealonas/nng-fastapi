import datetime
from typing import List, Optional

import sentry_sdk
from nng_sdk.postgres.exceptions import ItemNotFoundException, NngPostgresException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.request import Request, RequestType
from nng_sdk.pydantic_models.user import (
    User,
    Violation,
    ViolationType,
    BanPriority,
)
from pydantic import BaseModel

from services.utils_service import get_comment_info_utility
from utils.websocket_logger_manager import WebSocketLoggerManager

TEAL_OR_ORANGE = "С твоим приоритетом подавать запрос на разблокировку нельзя"
NOT_FIRST_VIOLATION = "Нельзя подавать еще один запрос после первого нарушения"
UNEXPIRED_VIOLATION = "С момента твоего нарушения прошло меньше года"
TOO_LOW_TRUST = "Твой траст фактор недостаточен для подачи запроса"
TOO_TOXIC = "Большинство оставленных тобой комментариев были отмечены как токсичные"
ANOTHER_REQUEST_WAS_OPENED = "Ты уже подавал запрос на разблокировку"
USER_NOT_FOUND = "Внутренняя ошибка"


class RequestServiceError(Exception):
    """Base exception for request service errors."""

    pass


class RequestNotFoundError(RequestServiceError):
    """Raised when a request is not found."""

    pass


class UserNotFoundError(RequestServiceError):
    """Raised when a user is not found."""

    pass


class DuplicateRequestError(RequestServiceError):
    """Raised when a duplicate request is detected."""

    pass


class RequestAlreadyAnsweredError(RequestServiceError):
    """Raised when trying to modify an answered request."""

    pass


class RequestWebsocketLog(BaseModel):
    """Model for request websocket log."""

    request_id: int
    send_to_user: int


class PutRequestResponse(BaseModel):
    """Model for put request response."""

    response: str
    success: bool
    request_id: Optional[int] = None


class RequestService:
    """Service class for handling request-related business logic."""

    def __init__(
        self,
        postgres: NngPostgres,
        ws_manager: Optional[WebSocketLoggerManager] = None,
    ):
        self.postgres = postgres
        self.ws_manager = ws_manager or WebSocketLoggerManager()

    async def get_all_unanswered_requests(self) -> List[Request]:
        """Get all unanswered requests."""
        return self.postgres.requests.get_all_unanswered_requests()

    async def get_user_requests(self, user_id: int) -> List[Request]:
        """Get all requests for a user."""
        return self.postgres.requests.get_user_requests(user_id)

    async def get_request(self, request_id: int) -> Request:
        """Get a request by ID."""
        try:
            return self.postgres.requests.get_request(request_id)
        except ItemNotFoundException:
            raise RequestNotFoundError(f"Request {request_id} not found")