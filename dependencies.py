from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.vk_manager import VkManager

from services.trust_service import TrustService


async def get_trust_service():
    """Get trust service dependency."""
    op = OpConnect()
    vk = VkManager()
    postgres = NngPostgres()

    trust_service = TrustService(postgres, vk, op)
    yield trust_service


async def get_db():
    """Get database connection dependency."""
    yield NngPostgres()
