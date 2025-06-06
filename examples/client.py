import asyncio
import json
import time

import websockets

from service.config.common import ConfigOpts
from service.daemon import DaemonService, Manager
from service.launchers.launch import launch
from service.periodic_task import periodic_task
from service.utils.log import LOG


class MyService(DaemonService):
    def __init__(self, conf: ConfigOpts, manager: Manager, *args, **kwargs):
        super().__init__(conf, manager, *args, **kwargs)

    async def start(self):
        await self.manager.start()
        await super().start()


class ServiceManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws_client = None
        self.url = 'ws://192.168.1.11:8765'
        self.is_connected = False
        self.reconnect_delay = 5  # reconnect delay in seconds
        # connection lock, prevent simultaneous connection
        self._connecting_lock = asyncio.Lock()
        self._max_retries = 3  # max retries
        self._current_retries = 0  # current retries

    async def start(self):
        """start manager, including WebSocket connection"""
        await self.connect_ws()
        # start message listening task
        asyncio.create_task(self.listen_messages())

    @periodic_task(spacing=10)
    async def heartbeat(self):
        """periodic heartbeat check"""
        LOG.info(f'Manager heartbeat at {time.time():.2f}')
        # check connection status, if disconnected, reconnect
        if not self.is_connected and not self._connecting_lock.locked():
            LOG.warning(
                'WebSocket connection lost, attempting to reconnect...'
            )
            await self.connect_ws()
        await self.send_message(
            {
                'type': 'heartbeat',
                'time': time.time(),
                'status': 'ok',
                'message': 'heartbeat',
            }
        )

    async def create_vm(self):
        """create vm"""
        LOG.info('creating vm')
        await asyncio.sleep(60)
        LOG.info('vm created')
        LOG.info('.' * 20)
        await self.send_message(
            {
                'type': 'create_vm',
                'time': time.time(),
                'message': 'create_vm',
            }
        )
        LOG.info('.' * 20)

    async def connect_ws(self):
        """connect WebSocket"""
        async with self._connecting_lock:
            if self.is_connected:
                return  # already connected, return

            try:
                LOG.info(f'Connecting WebSocket at {time.time():.2f}')
                self.ws_client = await websockets.connect(self.url)
                self.is_connected = True
                self._current_retries = 0  # reset retry count
                LOG.info(
                    f'WebSocket connected successfully at {time.time():.2f}'
                )
            except Exception as e:
                LOG.error(f'Failed to connect WebSocket: {e}')
                self.is_connected = False
                self._current_retries += 1

                # check if max retries reached
                if self._current_retries >= self._max_retries:
                    LOG.error(
                        f'Max retries ({self._max_retries}) reached, '
                        'stopping reconnection attempts'
                    )
                    return

                # retry after delay, but not recursively
                LOG.info(
                    f'Will retry connection in {self.reconnect_delay} seconds '
                    f'(attempt {self._current_retries}/{self._max_retries})'
                )
                await asyncio.sleep(self.reconnect_delay)

    async def disconnect_ws(self):
        """disconnect WebSocket connection"""
        if self.ws_client:
            await self.ws_client.close()
            self.is_connected = False
            LOG.info('WebSocket disconnected')

    async def send_message(self, message: dict | str):
        """send message to WebSocket"""
        if self.is_connected and self.ws_client:
            try:
                if isinstance(message, dict):
                    message = json.dumps(message)
                await self.ws_client.send(message)
                LOG.info(f'Sent message: {message}')
            except Exception as e:
                LOG.error(f'Failed to send message: {e}')
                self.is_connected = False
        else:
            LOG.warning('WebSocket not connected, cannot send message')

    async def listen_messages(self):
        """listen WebSocket messages"""
        while True:
            if self.is_connected and self.ws_client:
                try:
                    message = await self.ws_client.recv()
                    LOG.info(f'Received message: {message}')
                    # handle received message
                    await self.handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    LOG.warning('WebSocket connection closed')
                    self.is_connected = False
                    # reset retry count, because it was connected before
                    self._current_retries = 0
                except Exception as e:
                    LOG.error(f'Error receiving message: {e}')
                    self.is_connected = False
            else:
                # if not connected, try to reconnect (with limit)
                if (
                    not self._connecting_lock.locked()
                    and self._current_retries < self._max_retries
                ):
                    asyncio.create_task(self.connect_ws())
                # wait for a while and then retry
                await asyncio.sleep(self.reconnect_delay)

    async def handle_message(self, message):
        """handle received message"""
        try:
            # try to parse JSON message
            data = json.loads(message)
            LOG.info(f'Parsed message data: {data}')
            # add your message handling logic here
        except json.JSONDecodeError:
            # if not JSON format, handle text message directly
            LOG.info(f'Received text message: {message}')

        if data['type'] == 'create_vm':
            await self.create_vm()


async def main():
    conf = ConfigOpts()
    manager = ServiceManager()
    service = MyService(conf=conf, manager=manager)
    launcher = await launch(conf=conf, service=service, workers=1)
    await launcher.wait()


asyncio.run(main())
