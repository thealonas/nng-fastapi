"""
Audit logging service module - provides audit trail functionality.
"""

import datetime
import json
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_CHANGE = "permission_change"
    BAN = "ban"
    UNBAN = "unban"
    VIOLATION_ADD = "violation_add"
    TICKET_CREATE = "ticket_create"
    TICKET_CLOSE = "ticket_close"
    REQUEST_SUBMIT = "request_submit"
    REQUEST_PROCESS = "request_process"
    SYSTEM_CONFIG = "system_config"


class AuditSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditEntry(BaseModel):
    audit_id: Optional[int] = None
    timestamp: datetime.datetime
    actor_id: Optional[int] = None
    actor_type: str = "user"
    action: AuditAction
    resource_type: str
    resource_id: Optional[str] = None
    severity: AuditSeverity = AuditSeverity.LOW
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    success: bool = True
    error_message: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            self.timestamp = datetime.datetime.now()


class AuditFilter(BaseModel):
    actor_id: Optional[int] = None
    action: Optional[AuditAction] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    severity: Optional[AuditSeverity] = None
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None
    success: Optional[bool] = None


class AuditService:
    def __init__(self, max_entries: int = 10000):
        self._entries: List[AuditEntry] = []
        self._max_entries = max_entries
        self._audit_counter = 0

    def _trim_entries(self) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    async def log(
        self,
        action: AuditAction,
        resource_type: str,
        actor_id: Optional[int] = None,
        actor_type: str = "user",
        resource_id: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.LOW,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AuditEntry:
        self._audit_counter += 1
        
        entry = AuditEntry(
            audit_id=self._audit_counter,
            timestamp=datetime.datetime.now(),
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity,
            ip_address=ip_address,
            user_agent=user_agent,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata or {},
            success=success,
            error_message=error_message
        )
        
        self._entries.append(entry)
        self._trim_entries()
        
        return entry

    async def log_user_action(
        self,
        user_id: int,
        action: AuditAction,
        resource_type: str,
        resource_id: str = None,
        details: Dict[str, Any] = None
    ) -> AuditEntry:
        return await self.log(
            action=action,
            resource_type=resource_type,
            actor_id=user_id,
            actor_type="user",
            resource_id=resource_id,
            metadata=details or {}
        )

    async def log_system_action(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: str = None,
        details: Dict[str, Any] = None
    ) -> AuditEntry:
        return await self.log(
            action=action,
            resource_type=resource_type,
            actor_type="system",
            resource_id=resource_id,
            metadata=details or {}
        )

    async def get_entries(
        self,
        filter_params: Optional[AuditFilter] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditEntry]:
        entries = self._entries.copy()
        
        if filter_params:
            if filter_params.actor_id is not None:
                entries = [e for e in entries if e.actor_id == filter_params.actor_id]
            
            if filter_params.action is not None:
                entries = [e for e in entries if e.action == filter_params.action]
            
            if filter_params.resource_type is not None:
                entries = [e for e in entries if e.resource_type == filter_params.resource_type]
            
            if filter_params.resource_id is not None:
                entries = [e for e in entries if e.resource_id == filter_params.resource_id]
            
            if filter_params.severity is not None:
                entries = [e for e in entries if e.severity == filter_params.severity]
            
            if filter_params.start_date is not None:
                entries = [e for e in entries if e.timestamp >= filter_params.start_date]
            
            if filter_params.end_date is not None:
                entries = [e for e in entries if e.timestamp <= filter_params.end_date]
            
            if filter_params.success is not None:
                entries = [e for e in entries if e.success == filter_params.success]
        
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        
        return entries[offset:offset + limit]

    async def get_entry(self, audit_id: int) -> Optional[AuditEntry]:
        return next(
            (e for e in self._entries if e.audit_id == audit_id),
            None
        )

    async def get_user_activity(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[AuditEntry]:
        return await self.get_entries(
            filter_params=AuditFilter(actor_id=user_id),
            limit=limit
        )

    async def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50
    ) -> List[AuditEntry]:
        return await self.get_entries(
            filter_params=AuditFilter(
                resource_type=resource_type,
                resource_id=resource_id
            ),
            limit=limit
        )

    def get_stats(self) -> Dict[str, Any]:
        now = datetime.datetime.now()
        last_hour = now - datetime.timedelta(hours=1)
        last_day = now - datetime.timedelta(days=1)
        
        return {
            "total_entries": len(self._entries),
            "entries_last_hour": len([e for e in self._entries if e.timestamp > last_hour]),
            "entries_last_day": len([e for e in self._entries if e.timestamp > last_day]),
            "failed_actions": len([e for e in self._entries if not e.success]),
            "actions_by_type": self._count_by_action(),
            "severity_distribution": self._count_by_severity()
        }

    def _count_by_action(self) -> Dict[str, int]:
        counts = {}
        for entry in self._entries:
            action = entry.action.value
            counts[action] = counts.get(action, 0) + 1
        return counts

    def _count_by_severity(self) -> Dict[str, int]:
        counts = {}
        for entry in self._entries:
            severity = entry.severity.value
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count

    def export_json(self) -> str:
        return json.dumps(
            [e.model_dump() for e in self._entries],
            default=str,
            indent=2
        )


audit_service = AuditService()
