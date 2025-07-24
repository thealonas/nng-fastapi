"""
Dependency injection container module - provides DI functionality.
"""

from typing import Type, TypeVar, Dict, Any, Optional, Callable, List, Set
from enum import Enum
from dataclasses import dataclass
import threading
import inspect


T = TypeVar('T')


class Scope(str, Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


@dataclass
class ServiceDescriptor:
    service_type: Type
    implementation_type: Optional[Type] = None
    factory: Optional[Callable] = None
    instance: Optional[Any] = None
    scope: Scope = Scope.TRANSIENT
    dependencies: List[Type] = None
    tags: Set[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.tags is None:
            self.tags = set()


class ServiceCollection:
    def __init__(self):
        self._descriptors: Dict[Type, ServiceDescriptor] = {}

    def add_singleton(
        self,
        service_type: Type[T],
        implementation_type: Type[T] = None,
        factory: Callable[..., T] = None,
        instance: T = None
    ) -> "ServiceCollection":
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation_type=implementation_type,
            factory=factory,
            instance=instance,
            scope=Scope.SINGLETON
        )
        return self

    def add_transient(
        self,
        service_type: Type[T],
        implementation_type: Type[T] = None,
        factory: Callable[..., T] = None
    ) -> "ServiceCollection":
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation_type=implementation_type,
            factory=factory,
            scope=Scope.TRANSIENT
        )
        return self

    def add_scoped(
        self,
        service_type: Type[T],
        implementation_type: Type[T] = None,
        factory: Callable[..., T] = None
    ) -> "ServiceCollection":
        self._descriptors[service_type] = ServiceDescriptor(
            service_type=service_type,
            implementation_type=implementation_type,
            factory=factory,
            scope=Scope.SCOPED
        )
        return self

    def add_instance(
        self,
        service_type: Type[T],
        instance: T
    ) -> "ServiceCollection":
        return self.add_singleton(service_type, instance=instance)

    def build_provider(self) -> "ServiceProvider":
        return ServiceProvider(self._descriptors.copy())


class ServiceProvider:
    def __init__(self, descriptors: Dict[Type, ServiceDescriptor]):
        self._descriptors = descriptors
        self._singletons: Dict[Type, Any] = {}
        self._scoped: Dict[Type, Any] = {}
        self._lock = threading.RLock()

    def get_service(self, service_type: Type[T]) -> Optional[T]:
        descriptor = self._descriptors.get(service_type)
        if not descriptor:
            return None
        
        return self._resolve(descriptor)

    def get_required_service(self, service_type: Type[T]) -> T:
        service = self.get_service(service_type)
        if service is None:
            raise ServiceNotFoundError(f"Service {service_type.__name__} not registered")
        return service

    def _resolve(self, descriptor: ServiceDescriptor) -> Any:
        if descriptor.scope == Scope.SINGLETON:
            return self._resolve_singleton(descriptor)
        elif descriptor.scope == Scope.SCOPED:
            return self._resolve_scoped(descriptor)
        else:
            return self._create_instance(descriptor)

    def _resolve_singleton(self, descriptor: ServiceDescriptor) -> Any:
        with self._lock:
            if descriptor.service_type in self._singletons:
                return self._singletons[descriptor.service_type]
            
            instance = self._create_instance(descriptor)
            self._singletons[descriptor.service_type] = instance
            return instance

    def _resolve_scoped(self, descriptor: ServiceDescriptor) -> Any:
        with self._lock:
            if descriptor.service_type in self._scoped:
                return self._scoped[descriptor.service_type]
            
            instance = self._create_instance(descriptor)
            self._scoped[descriptor.service_type] = instance
            return instance

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        if descriptor.instance is not None:
            return descriptor.instance
        
        if descriptor.factory is not None:
            return self._invoke_factory(descriptor.factory)
        
        impl_type = descriptor.implementation_type or descriptor.service_type
        return self._construct(impl_type)

    def _invoke_factory(self, factory: Callable) -> Any:
        sig = inspect.signature(factory)
        params = {}
        
        for name, param in sig.parameters.items():
            if param.annotation != inspect.Parameter.empty:
                service = self.get_service(param.annotation)
                if service is not None:
                    params[name] = service
        
        return factory(**params)

    def _construct(self, cls: Type) -> Any:
        try:
            sig = inspect.signature(cls.__init__)
        except (ValueError, TypeError):
            return cls()
        
        params = {}
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            
            if param.annotation != inspect.Parameter.empty:
                service = self.get_service(param.annotation)
                if service is not None:
                    params[name] = service
                elif param.default == inspect.Parameter.empty:
                    raise DependencyResolutionError(
                        f"Cannot resolve dependency {param.annotation} for {cls.__name__}"
                    )
        
        return cls(**params)

    def create_scope(self) -> "ServiceScope":
        return ServiceScope(self)

    def clear_scoped(self) -> None:
        with self._lock:
            self._scoped.clear()


class ServiceScope:
    def __init__(self, provider: ServiceProvider):
        self._provider = provider
        self._scoped: Dict[Type, Any] = {}

    def get_service(self, service_type: Type[T]) -> Optional[T]:
        if service_type in self._scoped:
            return self._scoped[service_type]
        
        service = self._provider.get_service(service_type)
        
        descriptor = self._provider._descriptors.get(service_type)
        if descriptor and descriptor.scope == Scope.SCOPED:
            self._scoped[service_type] = service
        
        return service

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._scoped.clear()


class ServiceNotFoundError(Exception):
    pass


class DependencyResolutionError(Exception):
    pass


class Container:
    _instance: Optional["Container"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._collection = ServiceCollection()
        self._provider: Optional[ServiceProvider] = None

    @classmethod
    def instance(cls) -> "Container":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register_singleton(
        self,
        service_type: Type[T],
        implementation: Type[T] = None,
        factory: Callable = None
    ) -> "Container":
        self._collection.add_singleton(service_type, implementation, factory)
        return self

    def register_transient(
        self,
        service_type: Type[T],
        implementation: Type[T] = None,
        factory: Callable = None
    ) -> "Container":
        self._collection.add_transient(service_type, implementation, factory)
        return self

    def register_scoped(
        self,
        service_type: Type[T],
        implementation: Type[T] = None,
        factory: Callable = None
    ) -> "Container":
        self._collection.add_scoped(service_type, implementation, factory)
        return self

    def register_instance(
        self,
        service_type: Type[T],
        instance: T
    ) -> "Container":
        self._collection.add_instance(service_type, instance)
        return self

    def build(self) -> ServiceProvider:
        self._provider = self._collection.build_provider()
        return self._provider

    def resolve(self, service_type: Type[T]) -> T:
        if self._provider is None:
            self.build()
        return self._provider.get_required_service(service_type)

    def get_service(self, service_type: Type[T]) -> Optional[T]:
        if self._provider is None:
            self.build()
        return self._provider.get_service(service_type)


container = Container.instance()


def inject(service_type: Type[T]) -> T:
    return container.resolve(service_type)
