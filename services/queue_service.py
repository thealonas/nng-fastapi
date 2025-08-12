"""
Queue service module - provides task queue functionality.
"""

import asyncio
import datetime
import threading
from typing import Callable, Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
import heapq


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass(order=True)
class QueuedTask:
    priority: int
    task_id: str = field(compare=False)
    func: Callable = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: Dict[str, Any] = field(compare=False, default_factory=dict)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    created_at: datetime.datetime = field(compare=False, default_factory=datetime.datetime.now)
    started_at: Optional[datetime.datetime] = field(compare=False, default=None)
    completed_at: Optional[datetime.datetime] = field(compare=False, default=None)
    result: Any = field(compare=False, default=None)
    error: Optional[str] = field(compare=False, default=None)
    retries: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    retries: int = 0


class TaskQueue:
    def __init__(self, name: str = "default", max_workers: int = 5):
        self.name = name
        self.max_workers = max_workers
        self._queue: List[QueuedTask] = []
        self._tasks: Dict[str, QueuedTask] = {}
        self._results: List[TaskResult] = []
        self._lock = threading.RLock()
        self._task_counter = 0
        self._running = False
        self._active_workers = 0

    def _generate_task_id(self) -> str:
        self._task_counter += 1
        return f"{self.name}_{self._task_counter}"

    def enqueue(
        self,
        func: Callable,
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        **kwargs
    ) -> str:
        with self._lock:
            task_id = self._generate_task_id()
            
            task = QueuedTask(
                priority=-priority.value,
                task_id=task_id,
                func=func,
                args=args,
                kwargs=kwargs,
                max_retries=max_retries
            )
            
            heapq.heappush(self._queue, task)
            self._tasks[task_id] = task
            
            return task_id

    def dequeue(self) -> Optional[QueuedTask]:
        with self._lock:
            while self._queue:
                task = heapq.heappop(self._queue)
                if task.status == TaskStatus.PENDING:
                    return task
            return None

    def get_task(self, task_id: str) -> Optional[QueuedTask]:
        return self._tasks.get(task_id)

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        duration = None
        if task.started_at and task.completed_at:
            duration = (task.completed_at - task.started_at).total_seconds() * 1000
        
        return TaskResult(
            task_id=task_id,
            status=task.status,
            result=task.result,
            error=task.error,
            duration_ms=duration,
            retries=task.retries
        )

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                return True
            return False

    def get_pending_count(self) -> int:
        with self._lock:
            return len([t for t in self._queue if t.status == TaskStatus.PENDING])

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts = {}
            for task in self._tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "name": self.name,
                "total_tasks": len(self._tasks),
                "pending": len([t for t in self._queue if t.status == TaskStatus.PENDING]),
                "active_workers": self._active_workers,
                "max_workers": self.max_workers,
                "status_distribution": status_counts
            }

    def clear(self) -> int:
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count


class QueueService:
    def __init__(self):
        self._queues: Dict[str, TaskQueue] = {}
        self._default_queue = TaskQueue("default")
        self._queues["default"] = self._default_queue

    def get_queue(self, name: str = "default") -> TaskQueue:
        if name not in self._queues:
            self._queues[name] = TaskQueue(name)
        return self._queues[name]

    def create_queue(
        self,
        name: str,
        max_workers: int = 5
    ) -> TaskQueue:
        if name in self._queues:
            return self._queues[name]
        
        queue = TaskQueue(name, max_workers)
        self._queues[name] = queue
        return queue

    def delete_queue(self, name: str) -> bool:
        if name == "default":
            return False
        
        if name in self._queues:
            del self._queues[name]
            return True
        return False

    def enqueue(
        self,
        func: Callable,
        *args,
        queue_name: str = "default",
        priority: TaskPriority = TaskPriority.NORMAL,
        **kwargs
    ) -> str:
        queue = self.get_queue(queue_name)
        return queue.enqueue(func, *args, priority=priority, **kwargs)

    async def process_task(
        self,
        task: QueuedTask,
        queue: TaskQueue
    ) -> TaskResult:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.datetime.now()
        
        try:
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func(*task.args, **task.kwargs)
            else:
                result = task.func(*task.args, **task.kwargs)
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.datetime.now()
            
        except Exception as e:
            task.error = str(e)
            task.retries += 1
            
            if task.retries < task.max_retries:
                task.status = TaskStatus.PENDING
                with queue._lock:
                    heapq.heappush(queue._queue, task)
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.datetime.now()
        
        return queue.get_task_result(task.task_id)

    async def process_queue(
        self,
        queue_name: str = "default",
        max_tasks: int = None
    ) -> List[TaskResult]:
        queue = self.get_queue(queue_name)
        results = []
        processed = 0
        
        while True:
            task = queue.dequeue()
            if not task:
                break
            
            result = await self.process_task(task, queue)
            results.append(result)
            processed += 1
            
            if max_tasks and processed >= max_tasks:
                break
        
        return results

    def get_all_stats(self) -> Dict[str, Any]:
        return {
            "queues": {
                name: queue.get_stats()
                for name, queue in self._queues.items()
            },
            "total_queues": len(self._queues)
        }

    def list_queues(self) -> List[str]:
        return list(self._queues.keys())


queue_service = QueueService()


def enqueue_task(
    func: Callable,
    *args,
    queue: str = "default",
    priority: TaskPriority = TaskPriority.NORMAL,
    **kwargs
) -> str:
    return queue_service.enqueue(
        func,
        *args,
        queue_name=queue,
        priority=priority,
        **kwargs
    )
