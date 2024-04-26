from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.comment import Comment

from auth.actions import ensure_user_authorization
from dependencies import get_db
from services.comment_service import (
    CommentService,
    CommentNotFoundError,
    UserNotFoundError,
)

router = APIRouter()


@router.get("/comments/comment/{comment_id}", tags=["comments"], response_model=Comment)
async def get_single_comment(
    comment_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get a comment by ID."""
    service = CommentService(postgres)
    try:
        return await service.get_comment(comment_id)
    except CommentNotFoundError:
        raise HTTPException(status_code=404, detail="Comment not found")


@router.get("/comments/user/{user_id}", tags=["comments"], response_model=list[Comment])
async def get_user_comments(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get all comments by a user."""
    service = CommentService(postgres)
    try:
        return await service.get_user_comments(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
