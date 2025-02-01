"""
Admin service module - provides administrative operations.
"""

import datetime
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from nng_sdk.postgres.nng_postgres import NngPostgres


class AdminAction(BaseModel):
    action_id: int
    admin_id: int
    action_type: str
    target_type: str
    target_id: Optional[str] = None
    details: Dict[str, Any] = {}
    timestamp: datetime.datetime = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            self.timestamp = datetime.datetime.now()


class SystemStatus(BaseModel):
    status: str
    users_count: int
    groups_count: int
    tickets_open: int
    requests_pending: int
    watchdog_unreviewed: int
    last_updated: datetime.datetime


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    banned_users: int
    total_groups: int
    active_groups: int
    tickets_open: int
    tickets_closed_today: int
    requests_pending: int
    requests_processed_today: int


class AdminService:
    def __init__(self, postgres: NngPostgres):
        self.postgres = postgres
        self._action_counter = 0
        self._actions: List[AdminAction] = []
        self._max_actions = 1000

    def _log_action(
        self,
        admin_id: int,
        action_type: str,
        target_type: str,
        target_id: str = None,
        details: Dict[str, Any] = None
    ) -> AdminAction:
        self._action_counter += 1
        
        action = AdminAction(
            action_id=self._action_counter,
            admin_id=admin_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            details=details or {}
        )
        
        self._actions.append(action)
        if len(self._actions) > self._max_actions:
            self._actions = self._actions[-self._max_actions:]
        
        return action

    async def get_system_status(self) -> SystemStatus:
        users = self.postgres.users.get_all_users()
        groups = self.postgres.groups.get_all_groups()
        tickets = self.postgres.tickets.get_opened_tickets()
        requests = self.postgres.requests.get_all_unanswered_requests()
        watchdog = self.postgres.watchdog.get_all_unreviewed_logs()
        
        return SystemStatus(
            status="healthy",
            users_count=len(users),
            groups_count=len(groups),
            tickets_open=len(tickets),
            requests_pending=len(requests),
            watchdog_unreviewed=len(watchdog),
            last_updated=datetime.datetime.now()
        )

    async def get_admin_stats(self) -> AdminStats:
        all_users = self.postgres.users.get_all_users()
        banned_users = self.postgres.users.get_banned_users()
        active_users = [u for u in all_users if not u.has_active_violation()]
        
        all_groups = self.postgres.groups.get_all_groups()
        
        open_tickets = self.postgres.tickets.get_opened_tickets()
        pending_requests = self.postgres.requests.get_all_unanswered_requests()
        
        return AdminStats(
            total_users=len(all_users),
            active_users=len(active_users),
            banned_users=len(banned_users),
            total_groups=len(all_groups),
            active_groups=len(all_groups),
            tickets_open=len(open_tickets),
            tickets_closed_today=0,
            requests_pending=len(pending_requests),
            requests_processed_today=0
        )

    async def promote_to_admin(
        self,
        admin_id: int,
        user_id: int
    ) -> bool:
        try:
            user = self.postgres.users.get_user(user_id)
            user.admin = True
            self.postgres.users.update_user(user)
            
            self._log_action(
                admin_id=admin_id,
                action_type="promote",
                target_type="user",
                target_id=str(user_id),
                details={"promoted_to": "admin"}
            )
            
            return True
        except Exception:
            return False

    async def demote_from_admin(
        self,
        admin_id: int,
        user_id: int
    ) -> bool:
        try:
            user = self.postgres.users.get_user(user_id)
            user.admin = False
            self.postgres.users.update_user(user)
            
            self._log_action(
                admin_id=admin_id,
                action_type="demote",
                target_type="user",
                target_id=str(user_id),
                details={"demoted_from": "admin"}
            )
            
            return True
        except Exception:
            return False

    async def bulk_update_users(
        self,
        admin_id: int,
        user_ids: List[int],
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        successful = 0
        failed = 0
        
        for user_id in user_ids:
            try:
                user = self.postgres.users.get_user(user_id)
                
                for key, value in updates.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                
                self.postgres.users.update_user(user)
                successful += 1
            except Exception:
                failed += 1
        
        self._log_action(
            admin_id=admin_id,
            action_type="bulk_update",
            target_type="users",
            details={
                "user_count": len(user_ids),
                "successful": successful,
                "failed": failed,
                "updates": updates
            }
        )
        
        return {
            "total": len(user_ids),
            "successful": successful,
            "failed": failed
        }

    async def get_admin_actions(
        self,
        admin_id: Optional[int] = None,
        action_type: Optional[str] = None,
        limit: int = 100
    ) -> List[AdminAction]:
        actions = self._actions.copy()
        
        if admin_id is not None:
            actions = [a for a in actions if a.admin_id == admin_id]
        
        if action_type is not None:
            actions = [a for a in actions if a.action_type == action_type]
        
        actions.reverse()
        return actions[:limit]

    async def get_user_activity_summary(
        self,
        user_id: int
    ) -> Dict[str, Any]:
        try:
            user = self.postgres.users.get_user(user_id)
            tickets = self.postgres.tickets.get_user_tickets(user_id)
            requests = self.postgres.requests.get_user_requests(user_id)
            
            return {
                "user_id": user_id,
                "name": user.name,
                "admin": user.admin,
                "groups_count": len(user.groups) if user.groups else 0,
                "violations_count": len(user.violations) if user.violations else 0,
                "active_violation": user.has_active_violation(),
                "tickets_count": len(tickets),
                "requests_count": len(requests),
                "join_date": user.join_date.isoformat() if user.join_date else None
            }
        except Exception:
            return {"error": "User not found"}

    async def search_admin_logs(
        self,
        query: str,
        limit: int = 50
    ) -> List[AdminAction]:
        query_lower = query.lower()
        
        results = [
            a for a in self._actions
            if (query_lower in a.action_type.lower() or
                query_lower in a.target_type.lower() or
                (a.target_id and query_lower in a.target_id.lower()))
        ]
        
        results.reverse()
        return results[:limit]

    def clear_action_log(self) -> int:
        count = len(self._actions)
        self._actions.clear()
        return count
