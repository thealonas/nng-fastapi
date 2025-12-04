"""
Session service module - provides user session management functionality.
"""

import datetime
import secrets
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class Session:
    session_id: str
    user_id: int
    created_at: datetime.datetime
    expires_at: datetime.datetime
    last_activity: datetime.datetime
    status: SessionStatus = SessionStatus.ACTIVE
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    refresh_token: Optional[str] = None

    def is_expired(self) -> bool:
        return datetime.datetime.now() > self.expires_at

    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE and not self.is_expired()

    def touch(self) -> None:
        self.last_activity = datetime.datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "status": self.status.value,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "data": self.data,
        }


class SessionService:
    def __init__(
        self,
        session_ttl: int = 3600,
        max_sessions_per_user: int = 5,
        refresh_token_ttl: int = 86400 * 7,
    ):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[int, List[str]] = {}
        self._session_ttl = session_ttl
        self._max_sessions_per_user = max_sessions_per_user
        self._refresh_token_ttl = refresh_token_ttl

    def _generate_session_id(self) -> str:
        return secrets.token_urlsafe(32)

    def _generate_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    async def create_session(
        self,
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
    ) -> Session:
        await self._enforce_session_limit(user_id)

        session_id = self._generate_session_id()
        refresh_token = self._generate_refresh_token()
        now = datetime.datetime.now()
        session_ttl = ttl or self._session_ttl

        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + datetime.timedelta(seconds=session_ttl),
            last_activity=now,
            ip_address=ip_address,
            user_agent=user_agent,
            data=data or {},
            refresh_token=refresh_token,
        )

        self._sessions[session_id] = session

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session_id)

        return session

    async def _enforce_session_limit(self, user_id: int) -> None:
        if user_id not in self._user_sessions:
            return

        user_session_ids = self._user_sessions[user_id]
        while len(user_session_ids) >= self._max_sessions_per_user:
            oldest_session_id = user_session_ids[0]
            await self.revoke_session(oldest_session_id)

    async def get_session(self, session_id: str) -> Optional[Session]:
        session = self._sessions.get(session_id)
        if not session:
            return None

        if session.is_expired():
            session.status = SessionStatus.EXPIRED
            return None

        if session.status != SessionStatus.ACTIVE:
            return None

        session.touch()
        return session

    async def validate_session(self, session_id: str) -> bool:
        session = await self.get_session(session_id)
        return session is not None and session.is_active()

    async def refresh_session(self, refresh_token: str) -> Optional[Session]:
        for session in self._sessions.values():
            if session.refresh_token == refresh_token:
                if session.status == SessionStatus.REVOKED:
                    return None

                now = datetime.datetime.now()
                session.expires_at = now + datetime.timedelta(seconds=self._session_ttl)
                session.last_activity = now
                session.status = SessionStatus.ACTIVE
                session.refresh_token = self._generate_refresh_token()
                return session

        return None

    async def revoke_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = SessionStatus.REVOKED

        if session.user_id in self._user_sessions:
            if session_id in self._user_sessions[session.user_id]:
                self._user_sessions[session.user_id].remove(session_id)

        return True

    async def revoke_all_user_sessions(self, user_id: int) -> int:
        if user_id not in self._user_sessions:
            return 0

        session_ids = self._user_sessions[user_id].copy()
        count = 0

        for session_id in session_ids:
            if await self.revoke_session(session_id):
                count += 1

        return count

    async def get_user_sessions(self, user_id: int) -> List[Session]:
        if user_id not in self._user_sessions:
            return []

        sessions = []
        for session_id in self._user_sessions[user_id]:
            session = self._sessions.get(session_id)
            if session and session.is_active():
                sessions.append(session)

        return sessions

    async def set_session_data(self, session_id: str, key: str, value: Any) -> bool:
        session = await self.get_session(session_id)
        if not session:
            return False

        session.data[key] = value
        return True

    async def get_session_data(
        self, session_id: str, key: str, default: Any = None
    ) -> Any:
        session = await self.get_session(session_id)
        if not session:
            return default

        return session.data.get(key, default)

    async def delete_session_data(self, session_id: str, key: str) -> bool:
        session = await self.get_session(session_id)
        if not session or key not in session.data:
            return False

        del session.data[key]
        return True

    async def cleanup_expired(self) -> int:
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if session.is_expired() or session.status != SessionStatus.ACTIVE
        ]

        for session_id in expired_ids:
            session = self._sessions.pop(session_id, None)
            if session and session.user_id in self._user_sessions:
                if session_id in self._user_sessions[session.user_id]:
                    self._user_sessions[session.user_id].remove(session_id)

        return len(expired_ids)

    def get_stats(self) -> Dict[str, Any]:
        active_sessions = sum(1 for s in self._sessions.values() if s.is_active())
        expired_sessions = sum(1 for s in self._sessions.values() if s.is_expired())
        revoked_sessions = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.REVOKED
        )

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_sessions,
            "expired_sessions": expired_sessions,
            "revoked_sessions": revoked_sessions,
            "unique_users": len(self._user_sessions),
            "session_ttl": self._session_ttl,
            "max_sessions_per_user": self._max_sessions_per_user,
        }


session_service = SessionService()
