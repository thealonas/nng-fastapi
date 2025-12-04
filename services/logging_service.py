"""
Structured logging service module - provides centralized logging functionality.
"""

import datetime
import json
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogEntry:
    level: LogLevel
    message: str
    timestamp: datetime.datetime
    logger_name: str = "app"
    context: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[int] = None
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "logger_name": self.logger_name,
            "context": self.context,
            "exception": self.exception,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class LoggingService:
    def __init__(
        self,
        name: str = "app",
        min_level: LogLevel = LogLevel.INFO,
        max_entries: int = 5000,
    ):
        self._name = name
        self._min_level = min_level
        self._max_entries = max_entries
        self._entries: List[LogEntry] = []
        self._level_priority = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }
        self._context: Dict[str, Any] = {}

    def set_context(self, key: str, value: Any) -> None:
        self._context[key] = value

    def clear_context(self) -> None:
        self._context.clear()

    def _should_log(self, level: LogLevel) -> bool:
        return self._level_priority[level] >= self._level_priority[self._min_level]

    def _create_entry(
        self,
        level: LogLevel,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        user_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> LogEntry:
        merged_context = {**self._context, **(context or {})}
        return LogEntry(
            level=level,
            message=message,
            timestamp=datetime.datetime.now(),
            logger_name=self._name,
            context=merged_context,
            exception=exception,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            request_id=request_id,
        )

    def _store_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

    async def log(
        self,
        level: LogLevel,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        user_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> Optional[LogEntry]:
        if not self._should_log(level):
            return None

        entry = self._create_entry(
            level=level,
            message=message,
            context=context,
            exception=exception,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            request_id=request_id,
        )
        self._store_entry(entry)
        return entry

    async def debug(self, message: str, **kwargs) -> Optional[LogEntry]:
        return await self.log(LogLevel.DEBUG, message, **kwargs)

    async def info(self, message: str, **kwargs) -> Optional[LogEntry]:
        return await self.log(LogLevel.INFO, message, **kwargs)

    async def warning(self, message: str, **kwargs) -> Optional[LogEntry]:
        return await self.log(LogLevel.WARNING, message, **kwargs)

    async def error(self, message: str, **kwargs) -> Optional[LogEntry]:
        return await self.log(LogLevel.ERROR, message, **kwargs)

    async def critical(self, message: str, **kwargs) -> Optional[LogEntry]:
        return await self.log(LogLevel.CRITICAL, message, **kwargs)

    def get_entries(
        self,
        level: Optional[LogLevel] = None,
        logger_name: Optional[str] = None,
        user_id: Optional[int] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LogEntry]:
        entries = self._entries.copy()

        if level:
            entries = [e for e in entries if e.level == level]

        if logger_name:
            entries = [e for e in entries if e.logger_name == logger_name]

        if user_id:
            entries = [e for e in entries if e.user_id == user_id]

        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]

        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]

        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries[offset : offset + limit]

    def get_stats(self) -> Dict[str, Any]:
        now = datetime.datetime.now()
        last_hour = now - datetime.timedelta(hours=1)

        level_counts = {level.value: 0 for level in LogLevel}
        for entry in self._entries:
            level_counts[entry.level.value] += 1

        return {
            "total_entries": len(self._entries),
            "entries_by_level": level_counts,
            "entries_last_hour": len(
                [e for e in self._entries if e.timestamp > last_hour]
            ),
            "error_rate": level_counts.get("error", 0)
            / max(len(self._entries), 1)
            * 100,
            "oldest_entry": (
                self._entries[0].timestamp.isoformat() if self._entries else None
            ),
            "newest_entry": (
                self._entries[-1].timestamp.isoformat() if self._entries else None
            ),
        }

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count

    def export_json(self) -> str:
        return json.dumps([e.to_dict() for e in self._entries], default=str, indent=2)


logging_service = LoggingService()
