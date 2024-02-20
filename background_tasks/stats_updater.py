import asyncio
import datetime

from nng_sdk.logger import get_logger
from nng_sdk.vk.actions import get_members, GroupDataResponse
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.group_stats import GroupStats, GroupStat

from storage.group_data_storage import GroupDataStorage

logger = get_logger()


def has_stat_for_today(postgres: NngPostgres) -> bool:
    all_stats = postgres.groups_stats.get_stats()
    return any(stat for stat in all_stats if stat.date == datetime.date.today())


def get_all_subscribers_count(postgres: NngPostgres) -> int:
    all_groups = [i.group_id for i in postgres.groups.get_all_groups()]

    group_members: list[int] = []

    for group in all_groups:
        members: list[dict] = get_members(group)
        legitimate_members = [i for i in members if "deactivated" not in i.keys()]
        group_members.extend([i["id"] for i in legitimate_members])

    group_members = list(set(group_members))
    return len(group_members)


async def wait_for_next_day():
    next_day = datetime.datetime.now() + datetime.timedelta(days=1)
    next_day = next_day.replace(hour=3, minute=0, second=0)
    now = datetime.datetime.now()
    delta = next_day - now

    if delta.total_seconds() < 0:
        delta = datetime.timedelta(days=1) + delta

    await asyncio.sleep(delta.total_seconds())


def update_group_stats(postgres: NngPostgres):
    while True:
        if has_stat_for_today(postgres):
            logger.info("статистика на сегодня уже присутсвует, жду день")
            asyncio.run(wait_for_next_day())
            continue

        groups: dict[int, GroupDataResponse] = GroupDataStorage().groups
        stats: list[GroupStat] = []

        logger.info(f"обновляю статистику за сегодня, всего {len(groups.keys())} групп")

        for group_id in groups.keys():
            logger.info(f"обновлена статистика в группе {group_id}")
            group: GroupDataResponse = groups[group_id]
            stats.append(
                GroupStat(
                    group_id=group_id,
                    members_count=group.members_count,
                    managers_count=group.managers_count,
                )
            )

        total_managers = len(postgres.users.get_all_editors())

        postgres.groups_stats.upload_statistics(
            GroupStats(
                date=datetime.date.today(),
                stats=stats,
                total_users=get_all_subscribers_count(postgres),
                total_managers=total_managers,
            )
        )
