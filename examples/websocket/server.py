import asyncio
import json
import time

import websockets
from loguru import logger

from service import launchers
from service.config.common import ConfigOpts
from service.daemon import DaemonService, Manager
from service.periodic_task import periodic_task

LOG = logger.bind(name='server')


async def send_message(ws, message: dict):
    try:
        await ws.send(json.dumps(message))
    except Exception as e:
        LOG.error(f'error sending message: {e}')


async def handle_client(websocket):
    """
    handle WebSocket client connection
    """
    LOG.info('*' * 20)
    try:
        LOG.info(f'new client: {websocket.remote_address}')

        # send message
        message = {
            'type': 'create_vm',
            'time': time.time(),
            'message': 'create_vm',
        }
        LOG.info(f'send message: {message}')
        await send_message(websocket, message)

        # handle messages
        async for message in websocket:
            LOG.info(f'received message: {message}')

    except websockets.exceptions.ConnectionClosedError as e:
        LOG.error(f'client disconnected: {e}')
    finally:
        LOG.info('connection closed')
    LOG.info('*' * 20)


class ServiceManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host = '192.168.33.42'
        self.port = 8765
        self.url = f'ws://{self.host}:{self.port}'

    async def start(self):
        LOG.info(f'WebSocket server started: {self.url}')
        LOG.info('Press Ctrl+C to stop server')

        # start server
        self.server = await websockets.serve(
            handle_client,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
        )
        await self.server.start_serving()

    @periodic_task(spacing=10)
    async def heartbeat(self):
        LOG.info(f'server heartbeat: {time.time():.2f}')


async def main():
    conf = ConfigOpts()
    manager = ServiceManager()
    service = DaemonService(conf, manager)
    launcher = await launchers.launch(conf, service, workers=1)
    await launcher.wait()


asyncio.run(main())
