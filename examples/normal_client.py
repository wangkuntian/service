import asyncio
import json
import time

import websockets
from loguru import logger

LOG = logger.bind(name='client')


async def create_vm(ws):
    LOG.info('creating vm')
    LOG.info('.' * 20)
    time.sleep(45)
    LOG.info('vm created')
    LOG.info('.' * 20)
    data = {
        'type': 'create_vm_done',
        'time': time.time(),
        'status': 'ok',
        'message': 'create_vm_done',
    }
    try:
        await ws.send(json.dumps(data))
    except Exception as e:
        LOG.error(f'error sending message: {e}')


async def handle_message(ws, message: str):
    LOG.info('*' * 20)
    LOG.info(f'Received: {message}')
    try:
        data = json.loads(message)
        LOG.info(f'Received: {data}')
    except json.JSONDecodeError:
        LOG.info(f'Received: {message}', message)

    if data['type'] == 'create_vm':
        await create_vm(ws)


async def main():
    url = 'ws://192.168.33.138:8765'
    while True:
        async with websockets.connect(
            url, ping_interval=10, ping_timeout=10
        ) as websocket:
            LOG.info(f'Connected to server {url}')
            try:
                async for message in websocket:
                    asyncio.create_task(handle_message(websocket, message))
            except websockets.exceptions.ConnectionClosed as e:
                LOG.info(f'Connection closed: {e}, reconnecting...')
                await asyncio.sleep(3)
            except Exception as e:
                LOG.error(f'Error: {e}, reconnecting...')
                await asyncio.sleep(3)


if __name__ == '__main__':
    asyncio.run(main())
