import datetime
from typing import List, Optional, Annotated

import sentry_sdk
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import (
    ItemNotFoundException,
)
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import (
    Violation,
    User,
    ViolationType,
    BanPriority,
)
from nng_sdk.vk.actions import (
    get_groups_data,
    GroupDataResponse,
    edit_manager,
)
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel
from vk_api import VkApiError

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
)
from dependencies import get_db, get_trust_service
from services.ban_service import BanService
from services.trust_service import TrustService
from utils.trust_restrictions import get_groups_restriction
from utils.users_utils import update_trust, create_default_user


class PostUserGroup(BaseModel):
    group_id: int


class UserPut(BaseModel):
    user_id: int
    name: Optional[str] = None


class UserPost(BaseModel):
    name: Optional[str] = None
    admin: Optional[bool] = None
    groups: Optional[List[int]] = None
    activism: Optional[bool] = None
    donate: Optional[bool] = None


class PublicViolation(BaseModel):
    group_id: Optional[int] = None
    priority: Optional[BanPriority] = None
    complaint: Optional[int] = None
    date: Optional[datetime.date] = None


class BannedOutput(BaseModel):
    user_id: int
    name: str
    violations: List[PublicViolation]

    def has_active_violation(self):
        return any(violation.active for violation in self.violations)


class ThxOutput(BaseModel):
    user_id: int
    name: str


router = APIRouter()


@router.get("/users/bnnd", response_model=List[BannedOutput], tags=["users", "public"])
def get_banned_users(postgres: NngPostgres = Depends(get_db)):
    users: list[User] = postgres.users.get_banned_users()
    for user in users:
        new_user_violations = [
            i for i in user.violations if i.type == ViolationType.banned
        ]
        user.violations = new_user_violations

    return [i for i in users if i.has_active_violation()]


@router.get("/users/thx", response_model=list[ThxOutput], tags=["users", "public"])
def get_thx(postgres: NngPostgres = Depends(get_db)):
    return postgres.users.get_thx_users()


@router.get("/users/user/{user_id}", response_model=User, tags=["users"])
def get_user(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")
    else:
        return user


@router.get("/users/search", response_model=List[User], tags=["users"])
def search_users(
    query: str,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    if not query:
        return []

    return postgres.users.search_users(query)


@router.put("/users/add", tags=["users"])
def put_user(
    user: UserPut,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_authorization)],
    trust_service: TrustService = Depends(get_trust_service),
    postgres: NngPostgres = Depends(get_db),
):
    try:
        postgres.users.get_user(user.user_id)
    except ItemNotFoundException:
        pass
    else:
        raise HTTPException(status_code=409, detail="User already exists")

    create_default_user(user.user_id, postgres, username=user.name)
    background_tasks.add_task(
        update_trust,
        user.user_id,
        postgres,
        trust_service,
    )

    return {"detail": "User successfully created"}


@router.post("/users/fire/{user_id}", tags=["users"])
def fire_user(
    user_id: int,
    fire_data: PostUserGroup,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.groups or fire_data.group_id not in user.groups:
        raise HTTPException(status_code=400, detail="User is not in this group")

    group_data = get_groups_data([fire_data.group_id])
    if fire_data.group_id not in group_data.keys():
        raise HTTPException(status_code=400, detail="Group not found")

    group: GroupDataResponse = group_data[fire_data.group_id]
    if user.user_id not in [i["id"] for i in group.managers]:
        user.groups.remove(fire_data.group_id)
        postgres.users.update_user(user)
        return {"detail": "User fired only in db"}

    try:
        edit_manager(group.group_id, user.user_id, None)
    except VkApiError as e:
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="Error while firing user")

    user.groups.remove(fire_data.group_id)
    postgres.users.update_user(user)
    return {"detail": "User fired successfully"}


@router.post("/users/restore/{user_id}", tags=["users"])
def restore_user(
    user_id: int,
    restore_data: PostUserGroup,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    group_data = get_groups_data([restore_data.group_id])
    if restore_data.group_id not in group_data.keys():
        raise HTTPException(status_code=400, detail="Group not found")

    group: GroupDataResponse = group_data[restore_data.group_id]
    if user.user_id in [i["id"] for i in group.managers]:
        user.groups.append(restore_data.group_id)
        postgres.users.update_user(user)
        return {"detail": "User restored only in db"}

    try:
        edit_manager(group.group_id, user.user_id, "editor")
    except VkApiError as e:
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="Error while restoring user")

    user.groups.append(restore_data.group_id)
    postgres.users.update_user(user)
    return {"detail": "User restored successfully"}


@router.post("/users/update/{user_id}", tags=["users"])
def post_user(
    user_id: int,
    user: UserPost,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    trust_service: TrustService = Depends(get_trust_service),
    postgres: NngPostgres = Depends(get_db),
):
    try:
        db_user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    if user.name:
        db_user.name = user.name

    if user.admin is not None:
        db_user.admin = user.admin

    if user.activism is not None:
        db_user.trust_info.activism = user.activism

    if user.donate is not None:
        db_user.trust_info.donate = user.donate

    if user.groups or user.groups == []:
        if not user.groups:
            db_user.groups = []
        else:
            db_user.groups = user.groups

    postgres.users.update_user(db_user)

    background_tasks.add_task(
        update_trust,
        db_user.user_id,
        postgres,
        trust_service,
    )

    return {"detail": "User successfully updated"}


@router.get("/users/calculate_trust/{user_id}", tags=["users"])
def calculate_trust(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    trust_service: TrustService = Depends(get_trust_service),
):
    try:
        postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    update_trust(user_id, postgres, trust_service)
    return {"detail": "User's trust has been updated"}


@router.get("/users/group_limit/{user_id}", tags=["users"])
def get_group_limit(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    trust: int = user.trust_info.trust
    return {"max_groups": get_groups_restriction(trust), "user_id": user.user_id}


@router.post("/users/add_violation/{user_id}", tags=["users"])
def add_violation(
    user_id: int,
    violation: Violation,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    immediate: bool = False,
    postgres: NngPostgres = Depends(get_db),
    trust_service: TrustService = Depends(get_trust_service),
):
    try:
        db_user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        postgres.users.add_violation(user_id, violation)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail="Error while adding violation")

    ban_service = BanService(postgres, VkManager(), OpConnect())
    if violation.type == ViolationType.banned and violation.active and immediate:
        background_tasks.add_task(ban_service.ban_user_in_groups, user_id)
    else:
        background_tasks.add_task(update_trust, user_id, postgres, trust_service)

    return {"detail": f"Violation was added to user {db_user.user_id}"}


@router.post("/users/unban/{user_id}", tags=["users"])
def unban_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    try:
        db_user: User = postgres.users.get_user(user_id)
    except ItemNotFoundException:
        raise HTTPException(status_code=404, detail="User not found")

    if not db_user.has_active_violation():
        raise HTTPException(status_code=400, detail="User is not banned")

    ban_service = BanService(postgres, VkManager(), OpConnect())
    background_tasks.add_task(ban_service.amnesty_user, user_id)
    return {"detail": f"User {db_user.user_id} was unbanned"}
