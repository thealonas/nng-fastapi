import re
from typing import Optional, Annotated

from typing import Annotated

from fastapi import APIRouter, Depends
from nng_sdk.postgres.nng_postgres import NngPostgres
from pydantic import BaseModel

from auth.actions import ensure_authorization, ensure_user_authorization
from dependencies import get_db
from services.utils_service import (
    get_comment_info_utility,
    GetCommentInfoResponse,
)

router = APIRouter()


class GetCommentInfoPost(BaseModel):
    comment_link: str


class GetUpdatesResponse(BaseModel):
    tickets: int
    watchdog: int
    requests: int


@router.post(
    "/utils/get_comment_info", response_model=GetCommentInfoResponse, tags=["utils"]
)
async def get_comment_info(
    post: GetCommentInfoPost,
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get comment info from a VK link."""
    return get_comment_info_utility(post.comment_link, postgres)


@router.get("/utils/get_updates", response_model=GetUpdatesResponse, tags=["utils"])
async def get_updates(
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get update counts for tickets, watchdog, and requests."""
    tickets = len(postgres.tickets.get_opened_tickets())
    watchdog = len(postgres.watchdog.get_all_unreviewed_logs())
    requests = len(postgres.requests.get_all_unanswered_requests())

    return GetUpdatesResponse(tickets=tickets, watchdog=watchdog, requests=requests)
