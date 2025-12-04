"""
Configuration service module - provides centralized configuration management.
"""

import os
import json
from typing import Dict, Any, Optional, List, TypeVar, Type
from enum import Enum
from dataclasses import dataclass

from pydantic import BaseModel


T = TypeVar("T")


class ConfigSource(str, Enum):
    DEFAULT = "default"
    ENV = "environment"
    FILE = "file"
    RUNTIME = "runtime"


@dataclass
class ConfigValue:
    key: str
    value: Any
    source: ConfigSource
    description: Optional[str] = None


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "nng"
    username: str = "postgres"
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20


class CacheConfig(BaseModel):
    enabled: bool = True
    default_ttl: int = 300
    max_size: int = 1000


class RateLimitConfig(BaseModel):
    enabled: bool = True
    default_requests_per_minute: int = 100
    burst_limit: int = 150


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10485760
    backup_count: int = 5


class SecurityConfig(BaseModel):
    secret_key: str = ""
    token_expiry_seconds: int = 3600
    refresh_token_expiry_seconds: int = 604800
    password_min_length: int = 8


class AppConfig(BaseModel):
    app_name: str = "NNG API"
    version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    allowed_hosts: List[str] = ["*"]
    cors_origins: List[str] = ["*"]

    database: DatabaseConfig = DatabaseConfig()
    cache: CacheConfig = CacheConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    logging: LoggingConfig = LoggingConfig()
    security: SecurityConfig = SecurityConfig()


class ConfigService:
    def __init__(self):
        self._config: Dict[str, ConfigValue] = {}
        self._app_config: AppConfig = AppConfig()
        self._load_defaults()

    def _load_defaults(self) -> None:
        defaults = {
            "app.name": "NNG API",
            "app.version": "1.0.0",
            "app.debug": False,
            "app.environment": "development",
            "database.host": "localhost",
            "database.port": 5432,
            "cache.enabled": True,
            "cache.default_ttl": 300,
            "rate_limit.enabled": True,
            "logging.level": "INFO",
        }

        for key, value in defaults.items():
            self._config[key] = ConfigValue(
                key=key, value=value, source=ConfigSource.DEFAULT
            )

    def load_from_env(self, prefix: str = "NNG_") -> int:
        count = 0
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower().replace("_", ".")
                self._config[config_key] = ConfigValue(
                    key=config_key,
                    value=self._parse_env_value(value),
                    source=ConfigSource.ENV,
                )
                count += 1
        return count

    def _parse_env_value(self, value: str) -> Any:
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def load_from_file(self, file_path: str) -> bool:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            self._flatten_and_load(data, ConfigSource.FILE)
            return True
        except Exception:
            return False

    def _flatten_and_load(
        self, data: Dict[str, Any], source: ConfigSource, prefix: str = ""
    ) -> None:
        for key, value in data.items():
            full_key = f"{prefix}{key}" if prefix else key

            if isinstance(value, dict):
                self._flatten_and_load(value, source, f"{full_key}.")
            else:
                self._config[full_key] = ConfigValue(
                    key=full_key, value=value, source=source
                )

    def get(self, key: str, default: Any = None) -> Any:
        config_value = self._config.get(key)
        if config_value:
            return config_value.value
        return default

    def get_typed(self, key: str, type_class: Type[T], default: T = None) -> T:
        value = self.get(key, default)
        if value is None:
            return default
        try:
            return type_class(value)
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value: Any, description: str = None) -> None:
        self._config[key] = ConfigValue(
            key=key, value=value, source=ConfigSource.RUNTIME, description=description
        )

    def has(self, key: str) -> bool:
        return key in self._config

    def delete(self, key: str) -> bool:
        if key in self._config:
            del self._config[key]
            return True
        return False

    def get_all(self, prefix: str = None) -> Dict[str, Any]:
        if prefix:
            return {k: v.value for k, v in self._config.items() if k.startswith(prefix)}
        return {k: v.value for k, v in self._config.items()}

    def get_app_config(self) -> AppConfig:
        return self._app_config

    def update_app_config(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._app_config, key):
                setattr(self._app_config, key, value)

    def get_database_config(self) -> DatabaseConfig:
        return self._app_config.database

    def get_cache_config(self) -> CacheConfig:
        return self._app_config.cache

    def get_rate_limit_config(self) -> RateLimitConfig:
        return self._app_config.rate_limit

    def get_logging_config(self) -> LoggingConfig:
        return self._app_config.logging

    def get_security_config(self) -> SecurityConfig:
        return self._app_config.security

    def export_config(self) -> Dict[str, Any]:
        return {
            "values": {k: v.value for k, v in self._config.items()},
            "sources": {k: v.source.value for k, v in self._config.items()},
            "app_config": self._app_config.model_dump(),
        }

    def get_stats(self) -> Dict[str, Any]:
        sources = {}
        for config_value in self._config.values():
            source = config_value.source.value
            sources[source] = sources.get(source, 0) + 1

        return {"total_keys": len(self._config), "sources": sources}


config_service = ConfigService()


def get_config(key: str, default: Any = None) -> Any:
    return config_service.get(key, default)
