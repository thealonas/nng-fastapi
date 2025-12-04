"""
Error handling utilities module - provides enhanced error handling.
"""

import traceback
import datetime
from typing import Optional, Dict, Any, Type, Callable
from enum import Enum

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMIT = "rate_limit"
    EXTERNAL_SERVICE = "external_service"
    DATABASE = "database"
    INTERNAL = "internal"
    BUSINESS_LOGIC = "business_logic"


class ErrorResponse(BaseModel):
    error_id: Optional[str] = None
    category: ErrorCategory
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime.datetime = None
    path: Optional[str] = None
    trace_id: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            self.timestamp = datetime.datetime.now()


class AppException(Exception):
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Dict[str, Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ValidationException(AppException):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class NotFoundException(AppException):
    def __init__(self, resource: str, resource_id: Any = None):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"

        super().__init__(
            message=message,
            category=ErrorCategory.NOT_FOUND,
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id},
        )


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHENTICATION,
            code="UNAUTHORIZED",
            status_code=401,
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Access forbidden"):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHORIZATION,
            code="FORBIDDEN",
            status_code=403,
        )


class ConflictException(AppException):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFLICT,
            code="CONFLICT",
            status_code=409,
            details=details,
        )


class RateLimitException(AppException):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            category=ErrorCategory.RATE_LIMIT,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )


class ExternalServiceException(AppException):
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"External service error: {message}",
            category=ErrorCategory.EXTERNAL_SERVICE,
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details={"service": service},
        )


class DatabaseException(AppException):
    def __init__(self, message: str = "Database error"):
        super().__init__(
            message=message,
            category=ErrorCategory.DATABASE,
            code="DATABASE_ERROR",
            status_code=500,
        )


class BusinessLogicException(AppException):
    def __init__(
        self, message: str, code: str = "BUSINESS_ERROR", details: Dict[str, Any] = None
    ):
        super().__init__(
            message=message,
            category=ErrorCategory.BUSINESS_LOGIC,
            code=code,
            status_code=422,
            details=details,
        )


class ErrorHandler:
    def __init__(self):
        self._handlers: Dict[Type[Exception], Callable] = {}
        self._error_counter = 0

    def register_handler(
        self,
        exception_type: Type[Exception],
        handler: Callable[[Exception, Request], JSONResponse],
    ) -> None:
        self._handlers[exception_type] = handler

    def generate_error_id(self) -> str:
        self._error_counter += 1
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        return f"ERR-{timestamp}-{self._error_counter:06d}"

    async def handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        handler = self._handlers.get(type(exc))
        if handler:
            return handler(exc, request)

        if isinstance(exc, AppException):
            return self._handle_app_exception(exc, request)

        if isinstance(exc, HTTPException):
            return self._handle_http_exception(exc, request)

        return self._handle_unknown_exception(exc, request)

    def _handle_app_exception(
        self, exc: AppException, request: Request
    ) -> JSONResponse:
        error_response = ErrorResponse(
            error_id=self.generate_error_id(),
            category=exc.category,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=exc.status_code, content=error_response.model_dump(mode="json")
        )

    def _handle_http_exception(
        self, exc: HTTPException, request: Request
    ) -> JSONResponse:
        category = self._get_category_from_status(exc.status_code)

        error_response = ErrorResponse(
            error_id=self.generate_error_id(),
            category=category,
            code=f"HTTP_{exc.status_code}",
            message=exc.detail,
            path=str(request.url.path),
        )

        return JSONResponse(
            status_code=exc.status_code, content=error_response.model_dump(mode="json")
        )

    def _handle_unknown_exception(
        self, exc: Exception, request: Request
    ) -> JSONResponse:
        error_response = ErrorResponse(
            error_id=self.generate_error_id(),
            category=ErrorCategory.INTERNAL,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            path=str(request.url.path),
            details={"exception_type": type(exc).__name__},
        )

        return JSONResponse(
            status_code=500, content=error_response.model_dump(mode="json")
        )

    def _get_category_from_status(self, status_code: int) -> ErrorCategory:
        if status_code == 400:
            return ErrorCategory.VALIDATION
        elif status_code == 401:
            return ErrorCategory.AUTHENTICATION
        elif status_code == 403:
            return ErrorCategory.AUTHORIZATION
        elif status_code == 404:
            return ErrorCategory.NOT_FOUND
        elif status_code == 409:
            return ErrorCategory.CONFLICT
        elif status_code == 429:
            return ErrorCategory.RATE_LIMIT
        else:
            return ErrorCategory.INTERNAL


error_handler = ErrorHandler()
