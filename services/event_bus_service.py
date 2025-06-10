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


@dataclass
class EventHandler:
    handler_id: str
    callback: Callable
    event_types: Set[str]
    priority: int = 0
    async_handler: bool = False


@dataclass
class EventResult:
    event_id: str
    handler_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._event_history: List[Event] = []
        self._result_history: List[EventResult] = []
        self._max_history = max_history
        self._handler_counter = 0
        self._lock = threading.RLock()
        self._middleware: List[Callable] = []

    def _generate_handler_id(self) -> str:
        self._handler_counter += 1
        return f"handler_{self._handler_counter}"

    def subscribe(
        self,
        event_types: List[str],
        callback: Callable,
        priority: int = 0
    ) -> str:
        with self._lock:
            handler_id = self._generate_handler_id()
            is_async = asyncio.iscoroutinefunction(callback)

            handler = EventHandler(
                handler_id=handler_id,
                callback=callback,
                event_types=set(event_types),
                priority=priority,
                async_handler=is_async
            )

            for event_type in event_types:
                if event_type not in self._handlers:
                    self._handlers[event_type] = []
                self._handlers[event_type].append(handler)
                self._handlers[event_type].sort(key=lambda h: -h.priority)

            return handler_id

    def unsubscribe(self, handler_id: str) -> bool:
        with self._lock:
            found = False
            for event_type in list(self._handlers.keys()):
                handlers = self._handlers[event_type]
                original_len = len(handlers)
                self._handlers[event_type] = [
                    h for h in handlers if h.handler_id != handler_id
                ]
                if len(self._handlers[event_type]) < original_len:
                    found = True
                if not self._handlers[event_type]:
                    del self._handlers[event_type]
            return found

    def add_middleware(self, middleware: Callable) -> None:
        self._middleware.append(middleware)

    def _apply_middleware(self, event: Event) -> Event:
        for middleware in self._middleware:
            event = middleware(event)
        return event

    async def publish(self, event: Event) -> List[EventResult]:
        event = self._apply_middleware(event)

        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        results = []
        handlers = self._handlers.get(event.event_type, [])

        wildcard_handlers = self._handlers.get("*", [])
        all_handlers = sorted(
            handlers + wildcard_handlers,
            key=lambda h: -h.priority
        )

        for handler in all_handlers:
            result = await self._invoke_handler(handler, event)
            results.append(result)
            self._result_history.append(result)

        if len(self._result_history) > self._max_history:
            self._result_history = self._result_history[-self._max_history:]

        return results

    async def _invoke_handler(
        self,
        handler: EventHandler,
        event: Event
    ) -> EventResult:
        start_time = datetime.datetime.now()

        try:
            if handler.async_handler:
                result = await handler.callback(event)
            else:
                result = handler.callback(event)

            duration = (datetime.datetime.now() - start_time).total_seconds() * 1000

            return EventResult(
                event_id=event.event_id,
                handler_id=handler.handler_id,
                success=True,
                result=result,
                duration_ms=duration
            )
        except Exception as e:
            duration = (datetime.datetime.now() - start_time).total_seconds() * 1000

            return EventResult(
                event_id=event.event_id,
                handler_id=handler.handler_id,
                success=False,
                error=str(e),
                duration_ms=duration
            )

    def publish_sync(self, event: Event) -> None:
        asyncio.create_task(self.publish(event))

    async def publish_and_wait(
        self,
        event: Event,
        timeout: float = 30.0
    ) -> List[EventResult]:
        try:
            return await asyncio.wait_for(
                self.publish(event),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return [EventResult(
                event_id=event.event_id,
                handler_id="timeout",
                success=False,
                error=f"Event handling timed out after {timeout}s"
            )]

    def emit(
        self,
        event_type: str,
        data: Dict[str, Any] = None,
        source: str = "system",
        priority: EventPriority = EventPriority.NORMAL
    ) -> Event:
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source,
            priority=priority
        )
        asyncio.create_task(self.publish(event))
        return event
