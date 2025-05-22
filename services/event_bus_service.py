"""
Event bus service module - provides event-driven architecture.
"""

import asyncio
from typing import Dict, List, Callable, Any, Optional, Set
from enum import Enum
from dataclasses import dataclass, field
import datetime
import threading


class EventPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Event:
    event_type: str
    data: Dict[str, Any]
    source: str = "system"
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)
    event_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if self.event_id is None:
            self.event_id = f"evt_{id(self)}_{self.timestamp.timestamp()}"
