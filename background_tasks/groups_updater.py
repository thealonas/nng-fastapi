import logging

from nng_sdk.logger import get_logger
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.actions import GroupDataResponse, get_groups_data

from storage.group_data_storage import GroupDataStorage

logger = get_logger()


def update_group_cache(postgres: NngPostgres):
    storage = GroupDataStorage()
    all_groups = [i.group_id for i in postgres.groups.get_all_groups()]

    logger.info(f"всего групп: {len(all_groups)}")
    groups: dict[int, GroupDataResponse] = get_groups_data(all_groups)

    logging.info(f"{len(groups.keys())} групп в кэше")
    storage.update_groups(groups)
