"""
Response utilities module - provides standardized API response formatting.
"""

import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic
from enum import Enum

from pydantic import BaseModel, Field


T = TypeVar("T")


class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    PARTIAL = "partial"


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ResponseMeta(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    request_id: Optional[str] = None
    version: str = "1.0.0"
    duration_ms: Optional[float] = None


class ApiResponse(BaseModel, Generic[T]):
    status: ResponseStatus
    data: Optional[Any] = None
    message: Optional[str] = None
    errors: Optional[List[ErrorDetail]] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @classmethod
    def success(
        cls, data: Any = None, message: str = None, request_id: str = None
    ) -> "ApiResponse":
        return cls(
            status=ResponseStatus.SUCCESS,
            data=data,
            message=message,
            meta=ResponseMeta(request_id=request_id),
        )

    @classmethod
    def error(
        cls,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
        errors: List[ErrorDetail] = None,
        request_id: str = None,
    ) -> "ApiResponse":
        if errors is None:
            errors = [ErrorDetail(code=code, message=message)]

        return cls(
            status=ResponseStatus.ERROR,
            message=message,
            errors=errors,
            meta=ResponseMeta(request_id=request_id),
        )

    @classmethod
    def validation_error(
        cls, errors: List[Dict[str, Any]], request_id: str = None
    ) -> "ApiResponse":
        error_details = [
            ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message=e.get("message", "Validation error"),
                field=e.get("field"),
                details=e.get("details"),
            )
            for e in errors
        ]

        return cls(
            status=ResponseStatus.ERROR,
            message="Validation failed",
            errors=error_details,
            meta=ResponseMeta(request_id=request_id),
        )

    @classmethod
    def not_found(
        cls, resource: str, resource_id: Any = None, request_id: str = None
    ) -> "ApiResponse":
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"

        return cls.error(
            message=message, code=ErrorCode.NOT_FOUND, request_id=request_id
        )

    @classmethod
    def unauthorized(
        cls, message: str = "Unauthorized access", request_id: str = None
    ) -> "ApiResponse":
        return cls.error(
            message=message, code=ErrorCode.UNAUTHORIZED, request_id=request_id
        )

    @classmethod
    def forbidden(
        cls, message: str = "Access forbidden", request_id: str = None
    ) -> "ApiResponse":
        return cls.error(
            message=message, code=ErrorCode.FORBIDDEN, request_id=request_id
        )


class ListResponse(ApiResponse):
    total: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None

    @classmethod
    def create(
        cls,
        items: List[Any],
        total: int = None,
        page: int = None,
        page_size: int = None,
        request_id: str = None,
    ) -> "ListResponse":
        return cls(
            status=ResponseStatus.SUCCESS,
            data=items,
            total=total or len(items),
            page=page,
            page_size=page_size,
            meta=ResponseMeta(request_id=request_id),
        )


class ResponseFormatter:
    def __init__(self, version: str = "1.0.0"):
        self.version = version

    def format_success(self, data: Any = None, message: str = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "data": data,
            "message": message,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def format_error(
        self, message: str, code: str = "ERROR", details: Any = None
    ) -> Dict[str, Any]:
        return {
            "status": "error",
            "error": {"code": code, "message": message, "details": details},
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def format_list(
        self,
        items: List[Any],
        total: int = None,
        page: int = None,
        page_size: int = None,
    ) -> Dict[str, Any]:
        response = {
            "status": "success",
            "data": items,
            "meta": {
                "total": total or len(items),
                "timestamp": datetime.datetime.now().isoformat(),
            },
        }

        if page is not None:
            response["meta"]["page"] = page
        if page_size is not None:
            response["meta"]["page_size"] = page_size

        return response

    def wrap_response(self, data: Any, include_meta: bool = True) -> Dict[str, Any]:
        response = {"data": data}

        if include_meta:
            response["meta"] = {
                "version": self.version,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        return response


default_formatter = ResponseFormatter()


def success_response(data: Any = None, message: str = None) -> ApiResponse:
    return ApiResponse.success(data, message)


def error_response(message: str, code: str = ErrorCode.INTERNAL_ERROR) -> ApiResponse:
    return ApiResponse.error(message, code)


def list_response(items: List[Any], total: int = None) -> ListResponse:
    return ListResponse.create(items, total)
