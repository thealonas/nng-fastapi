import datetime
import requests
import sentry_sdk
from fastapi import HTTPException
from nng_sdk.logger import get_logger
from nng_sdk.one_password.models.vk_client import VkClient
from nng_sdk.postgres.exceptions import NngPostgresException, ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import (
    User,
    TrustInfo,
    Violation,
    ViolationType,
    BanPriority,
)
from nng_sdk.vk.actions import get_user_data
from nng_sdk.vk.vk_manager import VkManager

import routers.utils
from services.trust_service import TrustService

logger = get_logger()


def update_trust(user_id: int, postgres: NngPostgres, trust_service: TrustService):
    try:
        new_trust = trust_service.calculate_trust(user_id)
    except RuntimeError:
        raise HTTPException(status_code=400, detail="User not found")

    new_trust.last_updated = datetime.date.today()
    postgres.users.update_user_trust_info(user_id, new_trust)


def create_default_user(
    user_id: int, postgres: NngPostgres, username: str | None = None
):
    if not username:
        try:
            user_vk_data = get_user_data(user_id)
            username = f"{user_vk_data['first_name']} {user_vk_data['last_name']}"
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise HTTPException(status_code=406, detail="User doesn't exist in VK")

    trust = 40  # потом пересчитается само
    postgres.users.add_user(
        User(
            user_id=user_id,
            name=username,
            admin=False,
            trust=trust,
            invited_by=None,
            trust_info=TrustInfo.create_default(),
            join_date=datetime.date.today(),
            groups=[],
            violations=[],
        )
    )


def try_ban_user_as_teal(
    intruder: int,
    comment_link: str,
    request_id: int,
    complaint: int,
    postgres: NngPostgres,
) -> bool:
    comment_info: routers.utils.GetCommentInfoResponse = (
        routers.utils.get_comment_info_utility(comment_link, postgres)
    )

    violation = Violation(
        type=ViolationType.banned,
        group_id=comment_info.group_id or None,
        priority=BanPriority.teal,
        complaint=complaint,
        request_ref=request_id,
        active=True,
        date=datetime.date.today(),
    )

    try:
        postgres.users.add_violation(intruder, violation)
    except NngPostgresException as e:
        sentry_sdk.capture_exception(e)
        return False
    else:
        return True


def authorize_user_by_code(
    client: VkClient,
    code: str,
    redirect_uri: str,
    postgres: NngPostgres,
):
    response = requests.post(
        "https://oauth.vk.com/access_token",
        data={
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )

    vk_response: dict = response.json()

    invalid_response = HTTPException(status_code=401, detail="Invalid response from VK")

    if "access_token" not in vk_response.keys():
        raise invalid_response

    token: str = vk_response["access_token"]

    user_id: int | None = VkManager.get_token_user_id(token)

    if not user_id:
        raise invalid_response

    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(
            status_code=403, detail="You don't have rights to authorize"
        )

    return token, user
