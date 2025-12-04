import asyncio
import logging

from nng_sdk.logger import get_logger
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.actions import GroupDataResponse, get_groups_data

from storage.group_data_storage import GroupDataStorage

logger = get_logger()


async def update_group_cache(postgres: NngPostgres):
    storage = GroupDataStorage()
    groups_rows = await asyncio.to_thread(postgres.groups.get_all_groups)
    all_groups = [i.group_id for i in groups_rows]

    logger.info(f"всего групп: {len(all_groups)}")
    groups: dict[int, GroupDataResponse] = await asyncio.to_thread(
        get_groups_data, all_groups
    )

    logging.info(f"{len(groups.keys())} групп в кэше")
    await asyncio.to_thread(storage.update_groups, groups)
