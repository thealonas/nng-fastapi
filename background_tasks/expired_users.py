import datetime
from datetime import timedelta
from typing import List

import sentry_sdk
from fastapi import HTTPException
from nng_sdk.logger import get_logger
from nng_sdk.postgres.db_models.users import DbUser
from nng_sdk.postgres.exceptions import NngPostgresException, ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from sqlalchemy.exc import IntegrityError

from utils.users_utils import create_default_user

logger = get_logger()


def try_create_default_user(user_id: int, postgres: NngPostgres):
    try:
        create_default_user(user_id, postgres)
    except HTTPException as e:
        logger.warning(f"ошибка создания пользователя {user_id}: {e}")
        return
    else:
        logger.info(f"создал пользователя {user_id}")


def expired_users_task(postgres: NngPostgres):
    month_ago = datetime.date.today() - timedelta(days=30)

    logger.info("получаю всех пользователей")

    active_users_ids = list(
        set([i.author_id for i in postgres.comments.get_all_comments()])
    )

    logger.info(f"всего активных пользователей: {len(active_users_ids)}")

    for index, user_id in enumerate(active_users_ids):
        logger.info(f"проверяю {user_id} ({index + 1}/{len(active_users_ids)})")
        try:
            postgres.users.get_user(user_id)
        except ItemNotFoundException:
            try_create_default_user(user_id, postgres)

    with postgres.begin_session() as session:
        expired_db_users: List[DbUser] = (
            session.query(DbUser).filter(DbUser.join_date <= month_ago).all()
        )

        potential_expired_users = [
            user
            for user in expired_db_users
            if not user.groups
            and not user.violations
            and not user.admin
            and not user.trust_info.activism
        ]

    expired_users = []

    for user in potential_expired_users:
        if not postgres.comments.get_user_comments(user.user_id):
            expired_users.append(user)

    logger.info(f"на удаление: {len(expired_users)}")

    for user in expired_users:
        try:
            user_id: int = user.user_id
            postgres.users.delete_user(user_id)
        except (NngPostgresException, IntegrityError) as e:
            sentry_sdk.capture_exception(e)
            session.rollback()
            logger.error(f"ошибка удаления пользователя: {e}")
        else:
            logger.info(f"удалил пользователя {user_id}")
