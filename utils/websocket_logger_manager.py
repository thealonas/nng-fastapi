from pydantic import BaseModel
import sentry_sdk
from starlette.websockets import WebSocket


class WebSocketLoggerManager:
    active_connections: list[WebSocket]

    def __init__(self):
        self.active_connections = []

    async def connect(self, socket: WebSocket):
        await socket.accept()
        self.active_connections.append(socket)

    def disconnect(self, socket: WebSocket):
        self.active_connections.remove(socket)

    async def broadcast(self, log: BaseModel):
        for connection in self.active_connections:
            try:
                await connection.send_json(log.dict())
            except Exception as e:
                sentry_sdk.capture_exception(e)
