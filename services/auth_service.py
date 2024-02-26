from typing import Optional

import requests
from nng_sdk.one_password.models.vk_client import VkClient
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel

from auth.actions import (
    verify_credential,
    create_service_access_token,
    create_user_access_token,
    allowed_services,
    check_user_auth,
    get_jwt_token_user_id,
)


class AuthServiceError(Exception):
    """Base exception for auth service errors."""

    pass


class InvalidCredentialError(AuthServiceError):
    """Raised when credentials are invalid."""

    pass


class InvalidVkResponseError(AuthServiceError):
    """Raised when VK response is invalid."""

    pass


class UnauthorizedUserError(AuthServiceError):
    """Raised when user is not authorized."""

    pass


class TokenResponse(BaseModel):
    """Model for token response."""

    token: str
    token_type: str = "bearer"


class VkAuthResponse(BaseModel):
    """Model for VK auth response."""

    token: str
    token_type: str = "bearer"
    user_id: int
    vk_token: str


class WhoAmIResponse(BaseModel):
    """Model for whoami response."""

    is_valid: bool
    user_id: Optional[int] = None


class AuthService:
    """Service class for handling authentication-related business logic."""

    def __init__(
        self,
        postgres: Optional[NngPostgres] = None,
        op_connect: Optional[OpConnect] = None,
    ):
        self.postgres = postgres
        self.op_connect = op_connect or OpConnect()

    async def authenticate_service(
        self, service_name: str, credential: str
    ) -> TokenResponse:
        """Authenticate a service and return a token."""
        if not verify_credential(credential) or service_name not in allowed_services:
            raise InvalidCredentialError("Invalid credential")

        return TokenResponse(token=create_service_access_token(service_name))