"""
Export service module - provides data export functionality.
"""

import csv
import io
import json
import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from pydantic import BaseModel
from nng_sdk.postgres.nng_postgres import NngPostgres


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    XML = "xml"


class ExportConfig(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    include_headers: bool = True
    fields: Optional[List[str]] = None
    pretty_print: bool = False
    date_format: str = "%Y-%m-%d %H:%M:%S"


class ExportResult(BaseModel):
    format: ExportFormat
    content: str
    filename: str
    size_bytes: int
    record_count: int
    created_at: datetime.datetime


class ExportService:
    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres

    def _serialize_value(self, value: Any, date_format: str) -> Any:
        if isinstance(value, datetime.datetime):
            return value.strftime(date_format)
        elif isinstance(value, datetime.date):
            return value.strftime(date_format.split()[0])
        elif isinstance(value, (list, dict)):
            return json.dumps(value, default=str)
        elif hasattr(value, 'model_dump'):
            return json.dumps(value.model_dump(), default=str)
        return value

    def _extract_fields(
        self,
        item: Any,
        fields: Optional[List[str]],
        date_format: str
    ) -> Dict[str, Any]:
        if hasattr(item, 'model_dump'):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            data = vars(item) if hasattr(item, '__dict__') else {"value": str(item)}
        
        if fields:
            data = {k: v for k, v in data.items() if k in fields}
        
        return {k: self._serialize_value(v, date_format) for k, v in data.items()}

    def _to_json(
        self,
        items: List[Any],
        config: ExportConfig
    ) -> str:
        data = [self._extract_fields(item, config.fields, config.date_format) for item in items]
        
        if config.pretty_print:
            return json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return json.dumps(data, ensure_ascii=False, default=str)

    def _to_csv(
        self,
        items: List[Any],
        config: ExportConfig
    ) -> str:
        if not items:
            return ""
        
        data = [self._extract_fields(item, config.fields, config.date_format) for item in items]
        
        output = io.StringIO()
        
        fieldnames = list(data[0].keys()) if data else []
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        if config.include_headers:
            writer.writeheader()
        
        for row in data:
            writer.writerow(row)
        
        return output.getvalue()

    def _to_xml(
        self,
        items: List[Any],
        config: ExportConfig
    ) -> str:
        data = [self._extract_fields(item, config.fields, config.date_format) for item in items]
        
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append('<data>')
        
        for item in data:
            lines.append('  <item>')
            for key, value in item.items():
                escaped_value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                lines.append(f'    <{key}>{escaped_value}</{key}>')
            lines.append('  </item>')
        
        lines.append('</data>')
        
        return '\n'.join(lines)

    def _generate_filename(self, prefix: str, format: ExportFormat) -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = format.value
        return f"{prefix}_{timestamp}.{extension}"

    async def export_data(
        self,
        items: List[Any],
        prefix: str,
        config: Optional[ExportConfig] = None
    ) -> ExportResult:
        if config is None:
            config = ExportConfig()
        
        if config.format == ExportFormat.JSON:
            content = self._to_json(items, config)
        elif config.format == ExportFormat.CSV:
            content = self._to_csv(items, config)
        elif config.format == ExportFormat.XML:
            content = self._to_xml(items, config)
        else:
            content = self._to_json(items, config)
        
        return ExportResult(
            format=config.format,
            content=content,
            filename=self._generate_filename(prefix, config.format),
            size_bytes=len(content.encode('utf-8')),
            record_count=len(items),
            created_at=datetime.datetime.now()
        )

    async def export_users(self, config: Optional[ExportConfig] = None) -> ExportResult:
        users = self.postgres.users.get_all_users()
        return await self.export_data(users, "users_export", config)

    async def export_groups(self, config: Optional[ExportConfig] = None) -> ExportResult:
        groups = self.postgres.groups.get_all_groups()
        return await self.export_data(groups, "groups_export", config)

    async def export_tickets(self, config: Optional[ExportConfig] = None) -> ExportResult:
        tickets = self.postgres.tickets.get_opened_tickets()
        return await self.export_data(tickets, "tickets_export", config)

    async def export_requests(self, config: Optional[ExportConfig] = None) -> ExportResult:
        requests = self.postgres.requests.get_all_unanswered_requests()
        return await self.export_data(requests, "requests_export", config)

    async def export_watchdog_logs(self, config: Optional[ExportConfig] = None) -> ExportResult:
        logs = self.postgres.watchdog.get_all_unreviewed_logs()
        return await self.export_data(logs, "watchdog_export", config)

    async def export_user_data(
        self,
        user_id: int,
        config: Optional[ExportConfig] = None
    ) -> ExportResult:
        user = self.postgres.users.get_user(user_id)
        user_tickets = self.postgres.tickets.get_user_tickets(user_id)
        user_requests = self.postgres.requests.get_user_requests(user_id)
        
        combined_data = {
            "user": user.model_dump() if hasattr(user, 'model_dump') else vars(user),
            "tickets": [t.model_dump() if hasattr(t, 'model_dump') else vars(t) for t in user_tickets],
            "requests": [r.model_dump() if hasattr(r, 'model_dump') else vars(r) for r in user_requests]
        }
        
        return await self.export_data([combined_data], f"user_{user_id}_data", config)
