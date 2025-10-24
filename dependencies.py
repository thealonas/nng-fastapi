from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.vk_manager import VkManager

from services.trust_service import TrustService
from utils.di_container import Container, container
from utils.response import ResponseFormatter


def setup_container() -> Container:
    """Configure and setup the DI container with all services."""
    container.register_singleton(NngPostgres, factory=lambda: NngPostgres())
    container.register_singleton(VkManager, factory=lambda: VkManager())
    container.register_singleton(OpConnect, factory=lambda: OpConnect())
    container.register_singleton(ResponseFormatter, factory=lambda: ResponseFormatter())
    
    def trust_service_factory(
        postgres: NngPostgres, vk: VkManager, op: OpConnect
    ) -> TrustService:
        return TrustService(postgres, vk, op)
    
    container.register_scoped(TrustService, factory=trust_service_factory)
    
    container.build()
    return container


_container_initialized = False


def get_container() -> Container:
    """Get the initialized DI container."""
    global _container_initialized
    if not _container_initialized:
        setup_container()
        _container_initialized = True
    return container


async def get_trust_service():
    """Get trust service dependency via DI container."""
    c = get_container()
    postgres = c.resolve(NngPostgres)
    vk = c.resolve(VkManager)
    op = c.resolve(OpConnect)
    
    trust_service = TrustService(postgres, vk, op)
    yield trust_service


async def get_db():
    """Get database connection dependency via DI container."""
    c = get_container()
    yield c.resolve(NngPostgres)


async def get_response_formatter():
    """Get response formatter dependency via DI container."""
    c = get_container()
    yield c.resolve(ResponseFormatter)
