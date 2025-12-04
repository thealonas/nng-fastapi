"""
Rate limit middleware module - provides API rate limiting.
"""

import time
from typing import Callable, Optional, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from services.rate_limit_service import RateLimitService, rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        service: RateLimitService = None,
        default_rule: str = "default",
        identifier_header: str = "X-API-Key",
        skip_paths: list = None,
    ):
        super().__init__(app)
        self.service = service or rate_limiter
        self.default_rule = default_rule
        self.identifier_header = identifier_header
        self.skip_paths = skip_paths or ["/health", "/health/live", "/health/ready"]
        self._path_rules: Dict[str, str] = {}

    def add_path_rule(self, path_prefix: str, rule_name: str) -> None:
        self._path_rules[path_prefix] = rule_name

    def _get_identifier(self, request: Request) -> str:
        api_key = request.headers.get(self.identifier_header)
        if api_key:
            return f"api:{api_key}"

        if request.client:
            return f"ip:{request.client.host}"

        return "anonymous"

    def _get_rule_for_path(self, path: str) -> str:
        for prefix, rule in self._path_rules.items():
            if path.startswith(prefix):
                return rule
        return self.default_rule

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.skip_paths:
            return await call_next(request)

        identifier = self._get_identifier(request)
        rule_name = self._get_rule_for_path(request.url.path)

        result = self.service.check_rate_limit(identifier, rule_name)

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": result.retry_after,
                    "reset_at": result.reset_at.isoformat(),
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": result.reset_at.isoformat(),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = result.reset_at.isoformat()

        return response


class PerRouteRateLimiter:
    def __init__(self, service: RateLimitService = None):
        self.service = service or rate_limiter

    def __call__(self, rule_name: str = "default"):
        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request, *args, **kwargs):
                identifier = self._get_identifier(request)
                result = self.service.check_rate_limit(identifier, rule_name)

                if not result.allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "Rate limit exceeded",
                            "retry_after": result.retry_after,
                        },
                    )

                return await func(request, *args, **kwargs)

            return wrapper

        return decorator

    def _get_identifier(self, request: Request) -> str:
        if request.client:
            return f"ip:{request.client.host}"
        return "anonymous"


per_route_limiter = PerRouteRateLimiter()
