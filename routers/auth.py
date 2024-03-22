from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from nng_sdk.postgres.nng_postgres import NngPostgres
from pydantic import BaseModel

from auth.actions import get_bearer_token
from dependencies import get_db
from services.auth_service import (
    AuthService,
    InvalidCredentialError,
    InvalidVkResponseError,
    UnauthorizedUserError,
)

router = APIRouter()


class AuthForm(BaseModel):
    service_name: str
    credential: str


class VkCodeForm(BaseModel):
    code: str
    original_redirect_uri: str


class WhoAmIResponse(BaseModel):
    is_valid: bool
    user_id: Optional[int] = None


@router.post("/auth", tags=["auth"], response_model=dict)
async def auth(credential_form: AuthForm):
    """Authenticate a service and return a token."""
    service = AuthService()
    try:
        result = await service.authenticate_service(
            credential_form.service_name, credential_form.credential
        )
        return {"token": result.token, "token_type": result.token_type}
    except InvalidCredentialError:
        raise HTTPException(status_code=401, detail="Invalid credential")


@router.post("/vk_auth", tags=["auth"])
async def vk_auth(code_form: VkCodeForm, postgres: NngPostgres = Depends(get_db)):
    """Authenticate a user via VK OAuth."""
    service = AuthService(postgres=postgres)
    try:
        result = await service.authenticate_vk_user(
            code_form.code, code_form.original_redirect_uri
        )
        return {
            "token": result.token,
            "token_type": result.token_type,
            "user_id": result.user_id,
            "vk_token": result.vk_token,
        }
    except InvalidVkResponseError:
        raise HTTPException(status_code=401, detail="Invalid response from VK")
    except UnauthorizedUserError:
        raise HTTPException(
            status_code=403, detail="You don't have rights to authorize"
        )


@router.get("/auth/whoami", tags=["auth"], response_model=WhoAmIResponse)
async def is_valid(request: Request):
    """Check if a token is valid and return user info."""
    token: str | None = get_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Could not find token, you need to put it into Authorization header",
        )

    service = AuthService()
    return await service.whoami(token)
