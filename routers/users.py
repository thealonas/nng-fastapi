import datetime
from typing import List, Optional, Annotated

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import (
    Violation,
    User,
    ViolationType,
    BanPriority,
)
from nng_sdk.vk.vk_manager import VkManager
from pydantic import BaseModel

from auth.actions import (
    ensure_authorization,
    ensure_user_authorization,
)
from dependencies import get_db, get_trust_service
from services.ban_service import BanService
from services.trust_service import TrustService
from services.user_service import (
    UserService,
    UserNotFoundError,
    UserAlreadyExistsError,
    UserNotInGroupError,
    GroupNotFoundError,
    VkOperationError,
    ViolationAddError,
    UserNotBannedError,
)


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
async def get_banned_users(postgres: NngPostgres = Depends(get_db)):
    """Get all banned users with active violations."""
    service = UserService(postgres)
    return await service.get_banned_users()


@router.get("/users/thx", response_model=list[ThxOutput], tags=["users", "public"])
async def get_thx(postgres: NngPostgres = Depends(get_db)):
    """Get all users eligible for thanks."""
    service = UserService(postgres)
    return await service.get_thx_users()


@router.get("/users/user/{user_id}", response_model=User, tags=["users"])
async def get_user(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get a user by ID."""
    service = UserService(postgres)
    try:
        return await service.get_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/users/search", response_model=List[User], tags=["users"])
async def search_users(
    query: str,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Search users by query."""
    service = UserService(postgres)
    return await service.search_users(query)


async def _update_trust_task(
    user_id: int, postgres: NngPostgres, trust_service: TrustService
):
    """Background task to update user trust."""
    service = UserService(postgres)
    await service.update_trust(user_id, trust_service)


@router.put("/users/add", tags=["users"])
async def put_user(
    user: UserPut,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_authorization)],
    trust_service: TrustService = Depends(get_trust_service),
    postgres: NngPostgres = Depends(get_db),
):
    """Create a new user."""
    service = UserService(postgres)
    try:
        await service.create_user(user.user_id, user.name)
    except UserAlreadyExistsError:
        raise HTTPException(status_code=409, detail="User already exists")
    except VkOperationError:
        raise HTTPException(status_code=406, detail="User doesn't exist in VK")

    background_tasks.add_task(
        _update_trust_task,
        user.user_id,
        postgres,
        trust_service,
    )

    return {"detail": "User successfully created"}


@router.post("/users/fire/{user_id}", tags=["users"])
async def fire_user(
    user_id: int,
    fire_data: PostUserGroup,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Fire a user from a group."""
    service = UserService(postgres)
    try:
        message = await service.fire_user(user_id, fire_data.group_id)
        return {"detail": message}
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except UserNotInGroupError:
        raise HTTPException(status_code=400, detail="User is not in this group")
    except GroupNotFoundError:
        raise HTTPException(status_code=400, detail="Group not found")
    except VkOperationError:
        raise HTTPException(status_code=500, detail="Error while firing user")


@router.post("/users/restore/{user_id}", tags=["users"])
async def restore_user(
    user_id: int,
    restore_data: PostUserGroup,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Restore a user to a group."""
    service = UserService(postgres)
    try:
        message = await service.restore_user(user_id, restore_data.group_id)
        return {"detail": message}
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except GroupNotFoundError:
        raise HTTPException(status_code=400, detail="Group not found")
    except VkOperationError:
        raise HTTPException(status_code=500, detail="Error while restoring user")


@router.post("/users/update/{user_id}", tags=["users"])
async def post_user(
    user_id: int,
    user: UserPost,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    trust_service: TrustService = Depends(get_trust_service),
    postgres: NngPostgres = Depends(get_db),
):
    """Update a user's information."""
    service = UserService(postgres)
    try:
        groups = user.groups if user.groups or user.groups == [] else None
        await service.update_user(
            user_id,
            name=user.name,
            admin=user.admin,
            groups=groups if groups is not None else ([] if user.groups == [] else None),
            activism=user.activism,
            donate=user.donate,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    background_tasks.add_task(
        _update_trust_task,
        user_id,
        postgres,
        trust_service,
    )

    return {"detail": "User successfully updated"}


@router.get("/users/calculate_trust/{user_id}", tags=["users"])
async def calculate_trust(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
    trust_service: TrustService = Depends(get_trust_service),
):
    """Calculate and update a user's trust factor."""
    service = UserService(postgres)
    try:
        await service.update_trust(user_id, trust_service)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

    return {"detail": "User's trust has been updated"}


@router.get("/users/group_limit/{user_id}", tags=["users"])
async def get_group_limit(
    user_id: int,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get the group limit for a user based on trust."""
    service = UserService(postgres)
    try:
        return await service.get_group_limit(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/add_violation/{user_id}", tags=["users"])
async def add_violation(
    user_id: int,
    violation: Violation,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    immediate: bool = False,
    postgres: NngPostgres = Depends(get_db),
    trust_service: TrustService = Depends(get_trust_service),
):
    """Add a violation to a user."""
    service = UserService(postgres)
    try:
        db_user = await service.add_violation(user_id, violation)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except ViolationAddError:
        raise HTTPException(status_code=500, detail="Error while adding violation")

    ban_service = BanService(postgres, VkManager(), OpConnect())
    if violation.type == ViolationType.banned and violation.active and immediate:
        background_tasks.add_task(ban_service.ban_user_in_groups, user_id)
    else:
        background_tasks.add_task(
            _update_trust_task, user_id, postgres, trust_service
        )

    return {"detail": f"Violation was added to user {db_user.user_id}"}


@router.post("/users/unban/{user_id}", tags=["users"])
async def unban_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    _: Annotated[bool, Depends(ensure_user_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Unban a user."""
    service = UserService(postgres)
    try:
        db_user = await service.unban_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except UserNotBannedError:
        raise HTTPException(status_code=400, detail="User is not banned")

    ban_service = BanService(postgres, VkManager(), OpConnect())
    background_tasks.add_task(ban_service.amnesty_user, user_id)
    return {"detail": f"User {db_user.user_id} was unbanned"}
