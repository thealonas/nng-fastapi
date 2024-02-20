from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.comment import Comment
from nng_sdk.pydantic_models.user import User

from auth.actions import ensure_user_authorization
from dependencies import get_db

router = APIRouter()


@router.get("/comments/comment/{comment_id}", tags=["comments"], response_model=Comment)
def get_single_comment(
    comment_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        comment = postgres.comments.get_comment(comment_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="Comment not found")
    else:
        return comment


@router.get("/comments/user/{user_id}", tags=["comments"], response_model=list[Comment])
def get_user_comments(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    all_comments = postgres.comments.get_user_comments(user.user_id)
    return all_comments or []
