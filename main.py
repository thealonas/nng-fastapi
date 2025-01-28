import asyncio
import sentry_sdk

from fastapi import FastAPI
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.logging_middleware import LoggingMiddleware
from nng_sdk.vk.vk_manager import VkManager
from sqlalchemy.exc import OperationalError
from starlette.middleware.cors import CORSMiddleware

import routers.auth
import routers.callback
import routers.editor
import routers.groups
import routers.invites
import routers.requests
import routers.tickets
import routers.users
import routers.utils
import routers.vk
import routers.watchdog
import routers.export
import routers.health
import routers.comments

from background_tasks.expired_users import expired_users_task
from background_tasks.groups_updater import update_group_cache
from background_tasks.stats_updater import update_group_stats
from background_tasks.trust_updater import update_all_trust_factors
from dev import DEVELOPMENT

if DEVELOPMENT:
    get_logger().info("работаем в режиме разработки")


class BackgroundRunner:
    back_logger = get_logger()

    async def run(self):
        self.back_logger.info("запускаю бэкграунд таски...")
        postgres = await try_get_database_or_wait()

        asyncio.get_event_loop().run_in_executor(
            None, self.back_tasks_sequence, postgres, VkManager(), OpConnect()
        )

        self.back_logger.info("готово")

    @staticmethod
    def back_tasks_sequence(
        postgres: NngPostgres, vk_manager: VkManager, op: OpConnect
    ):
        update_group_cache(postgres)
        expired_users_task(postgres)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        asyncio.get_event_loop().run_in_executor(None, update_group_stats, postgres)

        asyncio.get_event_loop().run_in_executor(
            None, update_all_trust_factors, vk_manager, postgres, op
        )

        while True:
            asyncio.run(asyncio.sleep(60 * 60 * 24))
            update_group_cache(postgres)
            expired_users_task(postgres)


async def try_get_database_or_wait(max_tries: int = 5) -> NngPostgres:
    try_number = 1

    last_exception: Exception | None = None

    while try_number <= max_tries:
        try:
            db = NngPostgres()
        except OperationalError as e:
            await asyncio.sleep(1)
            last_exception = e
            try_number += 1
        else:
            return db

    if last_exception:
        raise last_exception


sentry_sdk.init(
    dsn="https://64194d3dcc31fa6803f2db863e960ec8@o555933.ingest.sentry.io/4505688891916288",
    environment="development" if DEVELOPMENT else None,
    traces_sample_rate=1.0,
)

logger = get_logger()

VkManager().auth_in_vk()
VkManager().auth_in_bot()

app = FastAPI(
    title="nng api",
    description="nng api",
    version="2.0.0",
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
)

if DEVELOPMENT:
    origins = ["*"]
    methods = ["*"]
    headers = ["*"]
else:
    origins = ["https://nng.alonas.lv", "https://admin.nng.alonas.lv"]
    methods = ["GET", "POST"]
    headers = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=methods,
    allow_headers=headers,
)

app.add_middleware(
    RateLimitMiddleware,
)

app.add_middleware(
    LoggingMiddleware,
)

app.include_router(routers.users.router)
app.include_router(routers.groups.router)
app.include_router(routers.watchdog.router)
app.include_router(routers.invites.router)
app.include_router(routers.requests.router)
app.include_router(routers.editor.router)
app.include_router(routers.tickets.router)
app.include_router(routers.callback.router)
app.include_router(routers.export.router)
app.include_router(routers.health.router)
app.include_router(routers.auth.router)
app.include_router(routers.utils.router)
app.include_router(routers.vk.router)
app.include_router(routers.comments.router)


asyncio.create_task(BackgroundRunner().run())
