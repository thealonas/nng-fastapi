import datetime
import re
from typing import Optional

import requests
import sentry_sdk
import vk_api
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.db_models.comments import DbComment
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import User, ViolationType, TrustInfo
from nng_sdk.vk.actions import vk_action
from nng_sdk.vk.vk_manager import VkManager

logger = get_logger()


class TrustService:
    TRUST_START_COUNT = 20

    postgres: NngPostgres
    vk: VkManager
    op: OpConnect

    def __init__(self, postgres: NngPostgres, vk: VkManager, op: OpConnect):
        self.postgres = postgres
        self.vk = vk

        if vk.bot is None or vk.api is None:
            raise RuntimeError("Vk is not initialized")

        self.op = op

    def get_user(self, user: int) -> User:
        try:
            output = self.postgres.users.get_user(user)
            return output
        except ItemNotFoundException:
            raise RuntimeError("User not found")

    @vk_action
    def joined_main_group(self, user_id: int) -> bool:
        main_group = self.op.get_bot_group()
        return bool(
            self.vk.bot.groups.isMember(group_id=main_group.group_id, user_id=user_id)
        )

    @vk_action
    def joined_test_group(self, user_id: int):
        return bool(self.vk.api.groups.isMember(group_id=201104581, user_id=user_id))

    @vk_action
    def get_profile_info(self, user_id: int) -> dict:
        user: dict = self.vk.api.users.get(
            user_ids=user_id, fields="photo_200,counters,verified"
        )[0]

        return user

    def has_month_old_comments(self, user_id: int) -> bool:
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        with self.postgres.begin_session() as session:
            comments = (
                session.query(DbComment)
                .where(DbComment.author_id == user_id)
                .where(DbComment.posted_on > month_ago)
                .all()
            )

        return any(comments)

    @staticmethod
    def calculate_profile_info(user_data: dict) -> (bool, bool, bool, bool):
        closed_profile = True
        has_photo = False
        has_friends = False

        verified_param = user_data.get("verified")
        verified = verified_param == 1

        deactivated = user_data.get("deactivated")

        if deactivated:
            return closed_profile, has_photo, has_friends, verified

        photo_200 = user_data.get("photo_200")
        if photo_200:
            has_photo = photo_200 != "https://vk.com/images/camera_200.png"

        counters = user_data.get("counters")
        friends = counters.get("friends")

        has_friends = False
        if friends:
            has_friends = friends >= 15

        cp = user_data.get("is_closed")
        if cp is not None:
            closed_profile = cp
        else:
            closed_profile = True

        return closed_profile, has_photo, has_friends, verified

    @vk_action
    def has_wall_posts(self, user_id: int):
        return self.vk.api.wall.get(owner_id=user_id).get("count") > 5

    @staticmethod
    def get_reg_date(user_id: int) -> Optional[datetime.date]:
        url = f"https://vk.com/foaf.php?id={user_id}"
        response = requests.get(url)

        if response.status_code != 200:
            raise RuntimeError(f"http error {response.status_code}")

        match = re.search(r'<ya:created dc:date="(.+?)"', response.text)
        if match:
            creation_date = match.group(1)
            return datetime.datetime.fromisoformat(
                creation_date.replace("T", " ").replace("+03:00", "")
            ).date()
        else:
            raise RuntimeError("user hasn't got reg date")

    @staticmethod
    def clamp_trust(trust: int) -> int:
        if trust < 0:
            return 0
        if trust > 100:
            return 100
        return trust

    def get_trust_criteria(self, user: User) -> TrustInfo:
        user_id: int = user.user_id
        user_vk: dict = self.get_profile_info(user_id)

        closed_profile, has_photo, has_friends, verified = self.calculate_profile_info(
            user_vk
        )

        try:
            has_wall_posts = self.has_wall_posts(user_id) or False
        except vk_api.exceptions.ApiError:
            has_wall_posts = False

        joined_main_group = self.joined_main_group(user_id)
        joined_test_group = self.joined_test_group(user_id)

        donate = False

        has_active_violation = user.has_active_violation()
        has_violation = has_active_violation
        had_violation = has_active_violation or (
            not has_active_violation
            and any([i for i in user.violations if i.type == ViolationType.banned])
        )

        has_warning = user.has_warning()
        had_warning = any(
            [i for i in user.violations if i.type == ViolationType.warned]
        )

        used_nng = self.has_month_old_comments(user_id)

        try:
            user_comments = self.postgres.comments.get_user_comments(user_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise

        if not user_comments:
            toxicity = 0
        else:
            toxic_scores = [i.toxicity * 100 for i in user_comments]
            toxicity = (sum(toxic_scores) / len(toxic_scores)) / 100

        try:
            registration_date = self.get_reg_date(user_id)
        except RuntimeError:
            registration_date = None

        try:
            odd_groups = self.postgres.sus.is_sus(user_id)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            logger.warning(e)
            odd_groups = False

        return TrustInfo(
            trust=self.TRUST_START_COUNT,
            toxicity=toxicity,
            registration_date=registration_date,
            nng_join_date=user.trust_info.nng_join_date,
            odd_groups=odd_groups,
            closed_profile=closed_profile,
            has_photo=has_photo,
            has_wall_posts=has_wall_posts,
            has_friends=has_friends,
            verified=verified,
            joined_test_group=joined_test_group,
            activism=user.trust_info.activism,
            has_violation=has_violation,
            had_violation=had_violation,
            had_warning=had_warning,
            has_warning=has_warning,
            used_nng=used_nng,
            joined_main_group=joined_main_group,
            donate=donate,
        )

    @staticmethod
    def get_points_for_joined(reg_date: datetime.date) -> int:
        delta = datetime.date.today() - reg_date
        days = delta.days

        if days < 30 * 6:
            return 0

        if days <= 30 * 12:
            return 5

        if days <= 30 * 24:
            return 15

        if days <= 30 * 48:
            return 20

        return 25

    @staticmethod
    def get_points_for_reg(reg_date: datetime.date) -> int:
        delta = datetime.date.today() - reg_date
        days = delta.days

        if days < 30 * 6:
            return -10

        return 0

    @staticmethod
    def get_points_for_vk_profile(trust_info: TrustInfo) -> int:
        output = 0
        if trust_info.closed_profile:
            output -= 7

        if trust_info.has_photo:
            output += 3

        if trust_info.has_wall_posts:
            output += 3

        if trust_info.has_friends:
            output += 3

        if trust_info.verified:
            output += 25

        return output

    @staticmethod
    def get_points_for_api_profile(trust_info: TrustInfo) -> int:
        output = 0
        if trust_info.odd_groups:
            output -= 15

        if trust_info.joined_test_group:
            output += 10

        if trust_info.joined_main_group:
            output += 3

        if trust_info.activism:
            output += 40

        if trust_info.donate:
            output += 10

        return output

    @staticmethod
    def get_points_for_violation(trust_info: TrustInfo) -> int:
        output = 0

        if trust_info.has_violation:
            output -= 100

        if trust_info.had_violation:
            output -= 5

        if trust_info.has_warning:
            output -= 10

        if trust_info.had_warning:
            output -= 5

        return output

    def get_points_for_invite(self, invited_by: int):
        try:
            referral = self.get_user(invited_by)
        except RuntimeError:
            return 0

        return int(referral.trust_info.trust * 0.05)

    def calculate_trust(self, user_id: int) -> TrustInfo:
        try:
            user: User = self.get_user(user_id)
            criteria = self.get_trust_criteria(user)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise

        if user.trust_info.verified:
            criteria.verified = True

        if user.trust_info.donate:
            criteria.donate = True

        total_trust = self.TRUST_START_COUNT

        if user.invited_by:
            total_trust += self.get_points_for_invite(user.invited_by)

        total_trust += self.get_points_for_reg(
            criteria.registration_date or datetime.date.today()
        )

        total_trust += self.get_points_for_joined(
            criteria.nng_join_date or datetime.date.today()
        )

        total_trust += self.get_points_for_vk_profile(criteria)
        total_trust += self.get_points_for_api_profile(criteria)
        total_trust += self.get_points_for_violation(criteria)

        if user.admin:
            total_trust += 100

        if criteria.used_nng:
            total_trust += 3

        criteria.trust = self.clamp_trust(total_trust)

        return criteria
