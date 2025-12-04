from typing import Optional
import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from nng_sdk.postgres.nng_postgres import NngPostgres
from pydantic import BaseModel

from auth.actions import get_bearer_token
from dependencies import get_db, get_response_formatter
from services.auth_service import (
    AuthService,
    InvalidCredentialError,
    InvalidVkResponseError,
    UnauthorizedUserError,
)
from services.audit_service import audit_service, AuditAction, AuditSeverity
from services.metrics_service import metrics_service
from services.session_service import session_service
from services.logging_service import logging_service
from utils.response import ResponseFormatter

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
async def auth(
    credential_form: AuthForm,
    request: Request,
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Authenticate a service and return a token."""
    start_time = datetime.datetime.now()
    service = AuthService()
    try:
        result = await service.authenticate_service(
            credential_form.service_name, credential_form.credential
        )
        
        ip_address = request.client.host if request.client else None
        await audit_service.log(
            action=AuditAction.LOGIN,
            resource_type="service",
            resource_id=credential_form.service_name,
            severity=AuditSeverity.MEDIUM,
            ip_address=ip_address
        )
        await metrics_service.increment("auth_service_success")
        
        duration = (datetime.datetime.now() - start_time).total_seconds() * 1000
        await metrics_service.timer("auth_duration", duration)
        
        return {"token": result.token, "token_type": result.token_type}
    except InvalidCredentialError:
        await metrics_service.increment("auth_service_failed")
        await logging_service.warning(f"Failed auth attempt for service: {credential_form.service_name}")
        raise HTTPException(status_code=401, detail="Invalid credential")


@router.post("/vk_auth", tags=["auth"])
async def vk_auth(
    code_form: VkCodeForm,
    request: Request,
    postgres: NngPostgres = Depends(get_db),
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Authenticate a user via VK OAuth."""
    service = AuthService(postgres=postgres)
    try:
        result = await service.authenticate_vk_user(
            code_form.code, code_form.original_redirect_uri
        )
        
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        await session_service.create_session(
            user_id=result.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            data={"vk_token": result.vk_token}
        )
        
        await audit_service.log(
            action=AuditAction.LOGIN,
            resource_type="user",
            actor_id=result.user_id,
            resource_id=str(result.user_id),
            severity=AuditSeverity.LOW,
            ip_address=ip_address,
            user_agent=user_agent
        )
        await metrics_service.increment("auth_vk_success")
        await logging_service.info(f"User {result.user_id} logged in via VK")
        
        return {
            "token": result.token,
            "token_type": result.token_type,
            "user_id": result.user_id,
            "vk_token": result.vk_token,
        }
    except InvalidVkResponseError:
        await metrics_service.increment("auth_vk_failed")
        raise HTTPException(status_code=401, detail="Invalid response from VK")
    except UnauthorizedUserError:
        await metrics_service.increment("auth_vk_unauthorized")
        raise HTTPException(
            status_code=403, detail="You don't have rights to authorize"
        )


@router.get("/auth/whoami", tags=["auth"], response_model=WhoAmIResponse)
async def is_valid(
    request: Request,
    formatter: ResponseFormatter = Depends(get_response_formatter),
):
    """Check if a token is valid and return user info."""
    token: str | None = get_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Could not find token, you need to put it into Authorization header",
        )

    service = AuthService()
    result = await service.whoami(token)
    
    await metrics_service.increment("auth_whoami_requests")
    
    return result
