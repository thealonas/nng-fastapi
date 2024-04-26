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

    async def get_comment(self, comment_id: int) -> Comment:
        """Get a comment by ID."""
        try:
            return self.postgres.comments.get_comment(comment_id)
        except ItemNotFoundException:
            raise CommentNotFoundError(f"Comment {comment_id} not found")

    async def get_user_comments(self, user_id: int) -> List[Comment]:
        """Get all comments by a user."""
        try:
            self.postgres.users.get_user(user_id)
        except ItemNotFoundException:
            raise UserNotFoundError(f"User {user_id} not found")

        all_comments = self.postgres.comments.get_user_comments(user_id)
        return all_comments or []
