"""
Utils service module - handles utility business logic.

This service extracts utility logic to avoid circular imports and maintain
clean separation of concerns.
"""

import re
from typing import Optional

import sentry_sdk
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.actions import get_comment
from pydantic import BaseModel
from vk_api import VkApiError


class CommentInfo(BaseModel):
    """Model for comment info."""

    id: int
    from_id: int
    date: int
    text: Optional[str] = None


class GetCommentInfoResponse(BaseModel):
    """Model for get comment info response."""

    valid: bool
    is_nng: bool
    group_id: int
    normalized_link: Optional[str] = None
    object: Optional[CommentInfo] = None


def normalized_link(link: str) -> str:
    """Normalize a VK link."""
    return (
        link.replace("http://", "https://").replace("vk.com", "vk.ru").strip().lower()
    )


def get_comment_info_utility(
    link: str, postgres: NngPostgres
) -> GetCommentInfoResponse:
    """Get comment info from a VK link."""
    vk_com_link_regex = r"^https?://vk\.(com|ru)/wall(-?\d+)_\d+\?reply=(\d+)(?:&.+)?$"

    link = link.replace("http://", "https://")
    if not link.startswith("https://"):
        link = "https://" + link

    match = re.match(vk_com_link_regex, link)

    if not match:
        return GetCommentInfoResponse(valid=False, is_nng=False, group_id=0)

    posted_on: int = int(match.group(2))
    comment_id: int = int(match.group(3))

    try:
        obj: dict = get_comment(posted_on, comment_id)
    except VkApiError as e:
        sentry_sdk.capture_exception(e)
        return GetCommentInfoResponse(
            valid=False,
            is_nng=False,
            object=None,
            group_id=0,
            normalized_link=normalized_link(link),
        )

    if not obj or "from_id" not in obj:
        return GetCommentInfoResponse(
            valid=False, is_nng=False, group_id=0, normalized_link=normalized_link(link)
        )

    from_id: int = int(abs(obj["from_id"]))

    try:
        postgres.groups.get_group(from_id)
    except ItemNotFoundException:
        return GetCommentInfoResponse(valid=True, is_nng=False, group_id=from_id)

    return GetCommentInfoResponse(
        valid=True,
        is_nng=True,
        group_id=from_id,
        object=CommentInfo.model_validate(obj),
        normalized_link=normalized_link(link),
    )
