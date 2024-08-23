from typing import List, Annotated

from fastapi import APIRouter, Depends
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user_stats import UserStats

from auth.actions import ensure_authorization
from dependencies import get_db

router = APIRouter()


@router.get("/stats", response_model=List[UserStats], tags=["stats"])
async def get_stats(
    _: Annotated[bool, Depends(ensure_authorization)],
    postgres: NngPostgres = Depends(get_db),
):
    """Get all user stats."""
    return postgres.user_stats.get_all_stats()
