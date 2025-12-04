"""
Logging middleware module - provides request/response logging.
"""

import time
import datetime
import uuid
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class RequestLog:
    request_id: str
    method: str
    path: str
    query_params: Dict[str, Any]
    headers: Dict[str, str]
    client_ip: Optional[str]
    user_agent: Optional[str]
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    user_id: Optional[int] = None
    body_size: int = 0


@dataclass
class ResponseLog:
    request_id: str
    status_code: int
    headers: Dict[str, str]
    duration_ms: float
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    body_size: int = 0


@dataclass
class RequestResponseLog:
    request: RequestLog
    response: ResponseLog
    error: Optional[str] = None


class RequestLogger:
    def __init__(self, max_logs: int = 1000):
        self._logs: List[RequestResponseLog] = []
        self._max_logs = max_logs
        self._excluded_paths: List[str] = ["/health", "/health/live", "/health/ready"]
        self._masked_headers: List[str] = ["authorization", "cookie", "x-api-key"]

    def add_excluded_path(self, path: str) -> None:
        self._excluded_paths.append(path)

    def add_masked_header(self, header: str) -> None:
        self._masked_headers.append(header.lower())

    def should_log(self, path: str) -> bool:
        return path not in self._excluded_paths

    def _mask_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        masked = {}
        for key, value in headers.items():
            if key.lower() in self._masked_headers:
                masked[key] = "***MASKED***"
            else:
                masked[key] = value
        return masked

    def log_request(
        self, request_id: str, request: Request, user_id: Optional[int] = None
    ) -> RequestLog:
        headers = dict(request.headers)

        return RequestLog(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            headers=self._mask_headers(headers),
            client_ip=request.client.host if request.client else None,
            user_agent=headers.get("user-agent"),
            user_id=user_id,
        )

    def log_response(
        self, request_id: str, response: Response, duration_ms: float
    ) -> ResponseLog:
        headers = dict(response.headers) if hasattr(response, "headers") else {}

        return ResponseLog(
            request_id=request_id,
            status_code=response.status_code if hasattr(response, "status_code") else 0,
            headers=self._mask_headers(headers),
            duration_ms=duration_ms,
        )

    def add_log(self, log: RequestResponseLog) -> None:
        self._logs.append(log)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs :]

    def get_logs(
        self,
        limit: int = 100,
        status_code: Optional[int] = None,
        method: Optional[str] = None,
        path_prefix: Optional[str] = None,
    ) -> List[RequestResponseLog]:
        filtered = self._logs.copy()

        if status_code is not None:
            filtered = [l for l in filtered if l.response.status_code == status_code]

        if method is not None:
            filtered = [l for l in filtered if l.request.method == method.upper()]

        if path_prefix is not None:
            filtered = [l for l in filtered if l.request.path.startswith(path_prefix)]

        filtered.reverse()
        return filtered[:limit]

    def get_stats(self) -> Dict[str, Any]:
        if not self._logs:
            return {
                "total_requests": 0,
                "avg_duration_ms": 0,
                "status_codes": {},
                "methods": {},
            }

        status_codes: Dict[int, int] = {}
        methods: Dict[str, int] = {}
        total_duration = 0.0

        for log in self._logs:
            status = log.response.status_code
            status_codes[status] = status_codes.get(status, 0) + 1

            method = log.request.method
            methods[method] = methods.get(method, 0) + 1

            total_duration += log.response.duration_ms

        return {
            "total_requests": len(self._logs),
            "avg_duration_ms": total_duration / len(self._logs),
            "status_codes": status_codes,
            "methods": methods,
        }

    def get_slow_requests(
        self, threshold_ms: float = 1000, limit: int = 10
    ) -> List[RequestResponseLog]:
        slow = [l for l in self._logs if l.response.duration_ms > threshold_ms]
        slow.sort(key=lambda x: x.response.duration_ms, reverse=True)
        return slow[:limit]

    def clear(self) -> int:
        count = len(self._logs)
        self._logs.clear()
        return count


request_logger = RequestLogger()


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger: RequestLogger = None):
        super().__init__(app)
        self.logger = logger or request_logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.logger.should_log(request.url.path):
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        request_log = self.logger.log_request(request_id, request)

        error_message = None
        try:
            response = await call_next(request)
        except Exception as e:
            error_message = str(e)
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000

            response_log = self.logger.log_response(
                request_id,
                response if "response" in locals() else Response(status_code=500),
                duration_ms,
            )

            self.logger.add_log(
                RequestResponseLog(
                    request=request_log, response=response_log, error=error_message
                )
            )

        response.headers["X-Request-ID"] = request_id
        return response


def get_request_id(request: Request) -> Optional[str]:
    return getattr(request.state, "request_id", None)
