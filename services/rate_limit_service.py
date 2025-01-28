"""
Rate limiting service module - provides API rate limiting functionality.
"""

import datetime
import threading
from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from pydantic import BaseModel


class RateLimitStrategy(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


@dataclass
class RateLimitRule:
    requests_per_window: int
    window_seconds: int
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW


class RateLimitResult(BaseModel):
    allowed: bool
    remaining: int
    reset_at: datetime.datetime
    retry_after: Optional[int] = None


class RateLimitBucket:
    def __init__(self, rule: RateLimitRule):
        self.rule = rule
        self.requests: list[datetime.datetime] = []
        self.tokens: float = float(rule.requests_per_window)
        self.last_update: datetime.datetime = datetime.datetime.now()

    def _cleanup_old_requests(self, now: datetime.datetime) -> None:
        cutoff = now - datetime.timedelta(seconds=self.rule.window_seconds)
        self.requests = [r for r in self.requests if r > cutoff]

    def _refill_tokens(self, now: datetime.datetime) -> None:
        elapsed = (now - self.last_update).total_seconds()
        refill_rate = self.rule.requests_per_window / self.rule.window_seconds
        self.tokens = min(
            self.rule.requests_per_window,
            self.tokens + elapsed * refill_rate
        )
        self.last_update = now

    def check_and_consume(self) -> RateLimitResult:
        now = datetime.datetime.now()
        
        if self.rule.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return self._token_bucket_check(now)
        elif self.rule.strategy == RateLimitStrategy.FIXED_WINDOW:
            return self._fixed_window_check(now)
        else:
            return self._sliding_window_check(now)

    def _sliding_window_check(self, now: datetime.datetime) -> RateLimitResult:
        self._cleanup_old_requests(now)
        
        if len(self.requests) >= self.rule.requests_per_window:
            oldest = self.requests[0]
            reset_at = oldest + datetime.timedelta(seconds=self.rule.window_seconds)
            retry_after = int((reset_at - now).total_seconds())
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=max(1, retry_after)
            )
        
        self.requests.append(now)
        remaining = self.rule.requests_per_window - len(self.requests)
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_at=now + datetime.timedelta(seconds=self.rule.window_seconds)
        )

    def _fixed_window_check(self, now: datetime.datetime) -> RateLimitResult:
        window_start = now.replace(
            second=(now.second // self.rule.window_seconds) * self.rule.window_seconds,
            microsecond=0
        )
        
        self.requests = [
            r for r in self.requests
            if r >= window_start
        ]
        
        reset_at = window_start + datetime.timedelta(seconds=self.rule.window_seconds)
        
        if len(self.requests) >= self.rule.requests_per_window:
            retry_after = int((reset_at - now).total_seconds())
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=max(1, retry_after)
            )
        
        self.requests.append(now)
        remaining = self.rule.requests_per_window - len(self.requests)
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_at=reset_at
        )

    def _token_bucket_check(self, now: datetime.datetime) -> RateLimitResult:
        self._refill_tokens(now)
        
        reset_at = now + datetime.timedelta(seconds=self.rule.window_seconds)
        
        if self.tokens < 1:
            time_to_next_token = (1 - self.tokens) / (
                self.rule.requests_per_window / self.rule.window_seconds
            )
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=max(1, int(time_to_next_token))
            )
        
        self.tokens -= 1
        
        return RateLimitResult(
            allowed=True,
            remaining=int(self.tokens),
            reset_at=reset_at
        )


class RateLimitService:
    def __init__(self):
        self._buckets: Dict[str, RateLimitBucket] = {}
        self._rules: Dict[str, RateLimitRule] = {}
        self._lock = threading.RLock()
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        self._rules["default"] = RateLimitRule(
            requests_per_window=100,
            window_seconds=60
        )
        self._rules["auth"] = RateLimitRule(
            requests_per_window=10,
            window_seconds=60
        )
        self._rules["search"] = RateLimitRule(
            requests_per_window=30,
            window_seconds=60
        )
        self._rules["write"] = RateLimitRule(
            requests_per_window=50,
            window_seconds=60
        )

    def register_rule(self, name: str, rule: RateLimitRule) -> None:
        with self._lock:
            self._rules[name] = rule

    def _get_bucket_key(self, identifier: str, rule_name: str) -> str:
        return f"{rule_name}:{identifier}"

    def check_rate_limit(
        self,
        identifier: str,
        rule_name: str = "default"
    ) -> RateLimitResult:
        with self._lock:
            rule = self._rules.get(rule_name, self._rules["default"])
            bucket_key = self._get_bucket_key(identifier, rule_name)
            
            if bucket_key not in self._buckets:
                self._buckets[bucket_key] = RateLimitBucket(rule)
            
            return self._buckets[bucket_key].check_and_consume()

    def is_allowed(self, identifier: str, rule_name: str = "default") -> bool:
        result = self.check_rate_limit(identifier, rule_name)
        return result.allowed

    def get_remaining(self, identifier: str, rule_name: str = "default") -> int:
        with self._lock:
            rule = self._rules.get(rule_name, self._rules["default"])
            bucket_key = self._get_bucket_key(identifier, rule_name)
            
            if bucket_key not in self._buckets:
                return rule.requests_per_window
            
            bucket = self._buckets[bucket_key]
            now = datetime.datetime.now()
            bucket._cleanup_old_requests(now)
            
            return max(0, rule.requests_per_window - len(bucket.requests))

    def reset(self, identifier: str, rule_name: str = "default") -> None:
        with self._lock:
            bucket_key = self._get_bucket_key(identifier, rule_name)
            if bucket_key in self._buckets:
                del self._buckets[bucket_key]

    def reset_all(self) -> None:
        with self._lock:
            self._buckets.clear()

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "total_buckets": len(self._buckets),
                "rules_count": len(self._rules),
                "rules": {
                    name: {
                        "requests_per_window": rule.requests_per_window,
                        "window_seconds": rule.window_seconds,
                        "strategy": rule.strategy.value
                    }
                    for name, rule in self._rules.items()
                }
            }


rate_limiter = RateLimitService()
