import asyncio

from service import Service
from service.config.common import ConfigOpts
from service.daemon import DaemonService
from service.launchers.launch import launch
from service.utils.log import LOG


class MyService(Service):
    async def start(self):
        LOG.debug('start')
        await super().start()
        # 添加一个定时任务来保持服务活跃
        self.tg.add_timer(5.0, self._heartbeat)

    async def stop(self):
        LOG.debug('stop')
        await super().stop()

    async def wait(self):
        LOG.debug('wait')
        await super().wait()

    async def _heartbeat(self):
        LOG.debug(f'heartbeat at: {asyncio.get_event_loop().time():.2f}s')


async def main():
    # service = MyService()
    # launcher = await launch(conf=ConfigOpts(), service=service, workers=2)
    # await launcher.wait()
    service = DaemonService()
    launcher = await launch(conf=ConfigOpts(), service=service, workers=2)
    await launcher.wait()


if __name__ == '__main__':
    asyncio.run(main())
