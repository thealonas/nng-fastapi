"""
Feature flag service module - provides feature toggle functionality.
"""

import datetime
from typing import Dict, Any, Optional, List, Set
from enum import Enum

from pydantic import BaseModel


class FeatureStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    GROUP_LIST = "group_list"


class FeatureFlag(BaseModel):
    name: str
    description: str = ""
    status: FeatureStatus = FeatureStatus.DISABLED
    percentage: float = 0.0
    enabled_users: List[int] = []
    enabled_groups: List[str] = []
    metadata: Dict[str, Any] = {}
    created_at: datetime.datetime = None
    updated_at: datetime.datetime = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = datetime.datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.datetime.now()


class FeatureFlagEvaluation(BaseModel):
    flag_name: str
    enabled: bool
    reason: str
    user_id: Optional[int] = None
    evaluated_at: datetime.datetime = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.evaluated_at is None:
            self.evaluated_at = datetime.datetime.now()


class FeatureFlagService:
    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._evaluation_log: List[FeatureFlagEvaluation] = []
        self._max_log_size = 1000
        self._setup_default_flags()

    def _setup_default_flags(self) -> None:
        default_flags = [
            FeatureFlag(
                name="new_dashboard",
                description="Enable new dashboard UI",
                status=FeatureStatus.DISABLED,
            ),
            FeatureFlag(
                name="advanced_search",
                description="Enable advanced search features",
                status=FeatureStatus.ENABLED,
            ),
            FeatureFlag(
                name="beta_features",
                description="Enable beta features for testing",
                status=FeatureStatus.USER_LIST,
                enabled_users=[],
            ),
            FeatureFlag(
                name="dark_mode",
                description="Enable dark mode UI",
                status=FeatureStatus.PERCENTAGE,
                percentage=50.0,
            ),
        ]

        for flag in default_flags:
            self._flags[flag.name] = flag

    def create_flag(
        self,
        name: str,
        description: str = "",
        status: FeatureStatus = FeatureStatus.DISABLED,
        **kwargs,
    ) -> FeatureFlag:
        if name in self._flags:
            raise ValueError(f"Flag '{name}' already exists")

        flag = FeatureFlag(name=name, description=description, status=status, **kwargs)

        self._flags[name] = flag
        return flag

    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        return self._flags.get(name)

    def get_all_flags(self) -> List[FeatureFlag]:
        return list(self._flags.values())

    def update_flag(
        self,
        name: str,
        status: FeatureStatus = None,
        percentage: float = None,
        enabled_users: List[int] = None,
        enabled_groups: List[str] = None,
        description: str = None,
    ) -> Optional[FeatureFlag]:
        flag = self._flags.get(name)
        if not flag:
            return None

        if status is not None:
            flag.status = status
        if percentage is not None:
            flag.percentage = percentage
        if enabled_users is not None:
            flag.enabled_users = enabled_users
        if enabled_groups is not None:
            flag.enabled_groups = enabled_groups
        if description is not None:
            flag.description = description

        flag.updated_at = datetime.datetime.now()
        return flag

    def delete_flag(self, name: str) -> bool:
        if name in self._flags:
            del self._flags[name]
            return True
        return False

    def is_enabled(
        self,
        name: str,
        user_id: Optional[int] = None,
        user_group: Optional[str] = None,
        default: bool = False,
    ) -> bool:
        evaluation = self.evaluate(name, user_id, user_group, default)
        return evaluation.enabled

    def evaluate(
        self,
        name: str,
        user_id: Optional[int] = None,
        user_group: Optional[str] = None,
        default: bool = False,
    ) -> FeatureFlagEvaluation:
        flag = self._flags.get(name)

        if not flag:
            evaluation = FeatureFlagEvaluation(
                flag_name=name,
                enabled=default,
                reason="Flag not found, using default",
                user_id=user_id,
            )
            self._log_evaluation(evaluation)
            return evaluation

        enabled = False
        reason = ""

        if flag.status == FeatureStatus.ENABLED:
            enabled = True
            reason = "Flag is globally enabled"

        elif flag.status == FeatureStatus.DISABLED:
            enabled = False
            reason = "Flag is globally disabled"

        elif flag.status == FeatureStatus.PERCENTAGE:
            if user_id is not None:
                hash_value = hash(f"{name}:{user_id}") % 100
                enabled = hash_value < flag.percentage
                reason = f"Percentage rollout ({flag.percentage}%)"
            else:
                enabled = False
                reason = "No user_id for percentage evaluation"

        elif flag.status == FeatureStatus.USER_LIST:
            if user_id is not None and user_id in flag.enabled_users:
                enabled = True
                reason = "User is in enabled list"
            else:
                enabled = False
                reason = "User is not in enabled list"

        elif flag.status == FeatureStatus.GROUP_LIST:
            if user_group is not None and user_group in flag.enabled_groups:
                enabled = True
                reason = "User group is in enabled list"
            else:
                enabled = False
                reason = "User group is not in enabled list"

        evaluation = FeatureFlagEvaluation(
            flag_name=name, enabled=enabled, reason=reason, user_id=user_id
        )

        self._log_evaluation(evaluation)
        return evaluation

    def _log_evaluation(self, evaluation: FeatureFlagEvaluation) -> None:
        self._evaluation_log.append(evaluation)
        if len(self._evaluation_log) > self._max_log_size:
            self._evaluation_log = self._evaluation_log[-self._max_log_size :]

    def enable_flag(self, name: str) -> bool:
        return self.update_flag(name, status=FeatureStatus.ENABLED) is not None

    def disable_flag(self, name: str) -> bool:
        return self.update_flag(name, status=FeatureStatus.DISABLED) is not None

    def add_user_to_flag(self, name: str, user_id: int) -> bool:
        flag = self._flags.get(name)
        if flag:
            if user_id not in flag.enabled_users:
                flag.enabled_users.append(user_id)
                flag.updated_at = datetime.datetime.now()
            return True
        return False

    def remove_user_from_flag(self, name: str, user_id: int) -> bool:
        flag = self._flags.get(name)
        if flag and user_id in flag.enabled_users:
            flag.enabled_users.remove(user_id)
            flag.updated_at = datetime.datetime.now()
            return True
        return False

    def set_percentage(self, name: str, percentage: float) -> bool:
        percentage = max(0.0, min(100.0, percentage))
        return (
            self.update_flag(
                name, status=FeatureStatus.PERCENTAGE, percentage=percentage
            )
            is not None
        )

    def get_evaluation_log(
        self, flag_name: Optional[str] = None, limit: int = 100
    ) -> List[FeatureFlagEvaluation]:
        logs = self._evaluation_log.copy()

        if flag_name:
            logs = [l for l in logs if l.flag_name == flag_name]

        logs.reverse()
        return logs[:limit]

    def get_stats(self) -> Dict[str, Any]:
        status_counts = {}
        for flag in self._flags.values():
            status = flag.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_flags": len(self._flags),
            "status_distribution": status_counts,
            "total_evaluations": len(self._evaluation_log),
        }


feature_flags = FeatureFlagService()


def is_feature_enabled(
    name: str, user_id: Optional[int] = None, default: bool = False
) -> bool:
    return feature_flags.is_enabled(name, user_id, default=default)
