from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.vk_manager import VkManager

from services.trust_service import TrustService


def get_trust_service():
    op = OpConnect()
    vk = VkManager()
    postgres = NngPostgres()

    trust_service = TrustService(postgres, vk, op)
    yield trust_service


def get_db():
    yield NngPostgres()
