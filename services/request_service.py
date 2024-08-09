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

    def _check_for_duplicates(
        self, request_type: RequestType, user: User
    ) -> None:
        """Check for duplicate unblock requests."""
        if request_type is not RequestType.unblock:
            return

        user_requests: List[Request] = self.postgres.requests.get_user_requests(
            user.user_id
        )

        if user_requests:
            for request in user_requests:
                if (
                    request.answered
                    and request.request_type is RequestType.unblock
                    and not request.decision
                    and (datetime.date.today() - request.created_on)
                    < datetime.timedelta(days=365)
                ):
                    raise DuplicateRequestError(ANOTHER_REQUEST_WAS_OPENED)

    def _auto_deny_request(self, request: Request, user: User) -> Request:
        """Auto deny request based on criteria."""
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
                if (more_than_year_ago is False)
                else TOO_TOXIC if is_toxic else ""
            )
        )

        if not is_first_violation or (more_than_year_ago is False) or is_toxic:
            request.answer = answer
            request.answered = True
            request.decision = False

        return request

    async def open_request(
        self,
        request_type: RequestType,
        user_id: int,
        user_message: str,
        vk_comment: Optional[str] = None,
    ) -> tuple[PutRequestResponse, int]:
        """
        Open a new request.

        Returns tuple of (response, status_code).
        """
        try:
            user: User = self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            return PutRequestResponse(response=USER_NOT_FOUND, success=False), 404

        try:
            self._check_for_duplicates(request_type, user)
        except DuplicateRequestError:
            return (
                PutRequestResponse(response=ANOTHER_REQUEST_WAS_OPENED, success=False),
                200,
            )

        request = Request(
            request_type=request_type,
            created_on=datetime.date.today(),
            user_id=user_id,
            user_message=user_message,
            vk_comment=(
                vk_comment if request_type is RequestType.complaint else None
            ),
            answer="",
            decision=False,
            answered=False,
        )

        request = self._auto_deny_request(request, user)

        new_request: Request = self.postgres.requests.upload_or_update_request(request)

        if new_request.answered:
            await self.ws_manager.broadcast(
                RequestWebsocketLog(
                    request_id=new_request.request_id, send_to_user=new_request.user_id
                )
            )

        return (
            PutRequestResponse(
                response="success", success=True, request_id=new_request.request_id
            ),
            200,
        )

    async def update_request_status(
        self,
        request_id: int,
        answer: Optional[str],
        decision: bool,
        answered: bool,
    ) -> tuple[Request, bool]:
        """
        Update a request's status.

        Returns tuple of (request, was_originally_unanswered).
        """
        try:
            request: Request = self.postgres.requests.get_request(request_id)
        except ItemNotFoundException:
            raise RequestNotFoundError(f"Request {request_id} not found")

        if answer:
            request.answer = answer

        original_answered = request.answered

        request.decision = decision
        request.answered = answered

        self.postgres.requests.upload_or_update_request(request)

        return request, not original_answered

    async def change_intruder(
        self, request_id: int, new_intruder: int
    ) -> Request:
        """Change the intruder of a request."""
        try:
            request: Request = self.postgres.requests.get_request(request_id)
        except ItemNotFoundException:
            raise RequestNotFoundError(f"Request {request_id} not found")

        if request.answered:
            raise RequestAlreadyAnsweredError("Request already answered")

        try:
            self.postgres.users.get_user(new_intruder)
        except ItemNotFoundException:
            raise UserNotFoundError("User is not presented in DB")

        request.intruder = new_intruder
        self.postgres.requests.upload_or_update_request(request)

        return request

    async def try_ban_user_as_teal(
        self,
        intruder: int,
        comment_link: str,
        request_id: int,
        complaint: int,
    ) -> bool:
        """Try to ban a user as teal priority."""
        comment_info = get_comment_info_utility(comment_link, self.postgres)

        violation = Violation(
            type=ViolationType.banned,
            group_id=comment_info.group_id or None,
            priority=BanPriority.teal,
            complaint=complaint,
            request_ref=request_id,
            active=True,
            date=datetime.date.today(),
        )

        try:
            self.postgres.users.add_violation(intruder, violation)
        except NngPostgresException as e:
            sentry_sdk.capture_exception(e)
            return False
        else:
            return True
