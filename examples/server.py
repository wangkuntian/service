import asyncio
import json
import time

import websockets
from loguru import logger

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


async def main():
    """
    main function, start WebSocket server
    """
    LOG.info('WebSocket server started: ws://192.168.33.138:8765')
    LOG.info('Press Ctrl+C to stop server')

    # start server
    async with websockets.serve(
        handle_client,
        '192.168.33.138',
        8765,
        ping_interval=30,
        ping_timeout=10,
    ):
        # keep server running
        await asyncio.Future()  # run forever, until interrupted


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOG.info('\nserver stopped')
