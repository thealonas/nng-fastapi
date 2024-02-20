from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from nng_sdk.one_password.models.vk_client import VkClient
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from pydantic import BaseModel

from auth.actions import (
    verify_credential,
    create_service_access_token,
    create_user_access_token,
    get_bearer_token,
    check_user_auth,
    get_jwt_token_user_id,
    allowed_services,
)
from dependencies import get_db
from utils.users_utils import authorize_user_by_code

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
def auth(credential_form: AuthForm):
    if (
        not verify_credential(credential_form.credential)
        or credential_form.service_name not in allowed_services
    ):
        raise HTTPException(status_code=401, detail="Invalid credential")

    return {
        "token": create_service_access_token(credential_form.service_name),
        "token_type": "bearer",
    }


@router.post("/vk_auth", tags=["auth"])
def vk_auth(code_form: VkCodeForm, postgres: NngPostgres = Depends(get_db)):
    vk_client: VkClient = OpConnect().get_vk_client()

    token, user = authorize_user_by_code(
        vk_client, code_form.code, code_form.original_redirect_uri, postgres
    )

    if not user.admin:
        raise HTTPException(
            status_code=403, detail="You don't have rights to authorize"
        )

    return {
        "token": create_user_access_token(user.user_id),
        "token_type": "bearer",
        "user_id": user.user_id,
        "vk_token": token,
    }


@router.get("/auth/whoami", tags=["auth"], response_model=WhoAmIResponse)
def is_valid(request: Request):
    token: str | None = get_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Could not find token, you need to put it into Authorization header",
        )

    if check_user_auth(token):
        user_id: int = get_jwt_token_user_id(token)
        return WhoAmIResponse(is_valid=True, user_id=user_id)

    return WhoAmIResponse(is_valid=False)
