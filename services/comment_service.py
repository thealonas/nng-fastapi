from typing import List

from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.comment import Comment


class CommentServiceError(Exception):
    """Base exception for comment service errors."""

    pass


class CommentNotFoundError(CommentServiceError):
    """Raised when a comment is not found."""

    pass


class UserNotFoundError(CommentServiceError):
    """Raised when a user is not found."""

    pass


class CommentService:
    """Service class for handling comment-related business logic."""

    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres

