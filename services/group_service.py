from typing import List

from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.group import Group


class GroupServiceError(Exception):
    """Base exception for group service errors."""

    pass


class GroupNotFoundError(GroupServiceError):
    """Raised when a group is not found."""

    pass


class GroupService:
    """Service class for handling group-related business logic."""

    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres

    async def get_all_groups(self) -> List[Group]:
        """Get all groups."""
        return self.postgres.groups.get_all_groups()

    async def get_group(self, group_id: int) -> Group:
        """Get a group by ID."""
        try:
            return self.postgres.groups.get_group(group_id)
        except ItemNotFoundException:
            raise GroupNotFoundError(f"Group {group_id} not found")
