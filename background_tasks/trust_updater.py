import asyncio
import datetime

import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.db_models.users import DbUser, DbTrustInfo
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import TrustInfo
from nng_sdk.vk.vk_manager import VkManager
from sqlalchemy import select

from services.trust_service import TrustService

logger = get_logger()


def get_users_with_outdated_trust(postgres: NngPostgres) -> list[int]:
    try:
        with postgres.begin_session() as session:
            month_ago = datetime.date.today() - datetime.timedelta(days=30)
            # noinspection PyTypeChecker
            all_users: list[int] = (
                session.execute(
                    select(DbUser.user_id)
                    .join(DbTrustInfo)
                    .where(DbTrustInfo.last_updated <= month_ago)
                )
                .scalars()
                .all()
            )

            return all_users
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error("не удалось получить пользователей с устаревшим трастом")
        return []


async def wait_for_next_update():
    now = datetime.datetime.now()
    next_startup = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if next_startup < now:
        next_startup += datetime.timedelta(days=1)

    wait_time = next_startup - now

    await asyncio.sleep(wait_time.total_seconds())


def update_all_trust_factors(vk: VkManager, postgres: NngPostgres, op: OpConnect):
    trust_service = TrustService(postgres, vk, op)

    def iterate():
        users: list[int] = get_users_with_outdated_trust(postgres)
        logger.info(f"всего пользователей с устаревшим траст фактором: {len(users)}")
        for user in users:
            logger.info(
                f"обновляю траст у {user} ({users.index(user) + 1}/{len(users)})"
            )

            new_trust: TrustInfo = trust_service.calculate_trust(user)
            new_trust.last_updated = datetime.date.today()
            postgres.users.update_user_trust_info(user, new_trust)

    while True:
        iterate()
        asyncio.run(wait_for_next_update())
