import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User
from nng_sdk.vk.actions import get_all_managers, edit_manager
from nng_sdk.vk.vk_manager import VkManager

import utils.custom_vk_actions
from services.trust_service import TrustService


class BanService:
    logger = get_logger()

    trust_service: TrustService
    postgres: NngPostgres
    vk: VkManager

    def __init__(self, postgres: NngPostgres, vk: VkManager, op: OpConnect):
        self.trust_service = TrustService(postgres, vk, op)
        self.postgres = postgres
        self.vk = vk

    def recalculate_trust(self, user: int):
        self.logger.info(f"обновляю траст у {user}")
        new_trust = self.trust_service.calculate_trust(user)
        self.postgres.users.update_user_trust_info(user, new_trust)

    def fuck_manager(self, group_id: int, user: int):
        managers: list[int] = [i["id"] for i in get_all_managers(group_id)]
        if user not in managers:
            self.logger.info(f"баню {user} в {group_id}")
            try:
                utils.custom_vk_actions.ban_in_group(user, group_id)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                self.logger.error(f"не удалось забанить {user} в {group_id}")
            return

        self.logger.info(f"снимаю редактора у {user} в {group_id}")
        try:
            edit_manager(group_id, user)
        except Exception as e:
            self.logger.error(f"не удалось снять редактора у {user} в {group_id}")
            sentry_sdk.capture_exception(e)
        else:
            self.logger.info(f"баню {user} в {group_id}")
            utils.custom_vk_actions.ban_in_group(user, group_id)

    def ban_user_in_groups(self, user_id: int):
        self.recalculate_trust(user_id)

        all_groups = self.postgres.groups.get_all_groups()

        user: User = self.postgres.users.get_user(user_id)
        user.groups = []

        self.postgres.users.update_user(user)

        for group in all_groups:
            self.fuck_manager(group.group_id, user_id)

    def amnesty_user(self, user: int):
        self.postgres.users.unban_user(user)
        self.recalculate_trust(user)
        self.unban_user_in_groups(user)

    def unban_user_in_groups(self, user: int):
        all_groups = self.postgres.groups.get_all_groups()
        for group in all_groups:
            group_id = group.group_id
            self.logger.info(f"разбаниваю {user} в {group_id}")
            try:
                utils.custom_vk_actions.unban_in_group(user, group_id)
            except Exception as e:
                self.logger.error(f"не удалось разбанить {user} в {group_id}")
                sentry_sdk.capture_exception(e)

        self.recalculate_trust(user)
