import os

from auth.models import AuthCredentials


class EnvironmentHelper:
    @staticmethod
    def get_auth_keys() -> AuthCredentials:
        return AuthCredentials(
            secret_key=EnvironmentHelper.get_env_variable("NNG_API_SK"),
            auth_key=EnvironmentHelper.get_env_variable("NNG_API_AK"),
        )

    @staticmethod
    def get_env_variable(key: str) -> str:
        return os.environ.get(key)
