import asyncio
import time

from service.config.common import ConfigOpts
from service.daemon import DaemonService, Manager
from service.launchers import launch
from service.periodic_task import periodic_task
from service.utils.log import LOG

DEFAULT_HEARTBEAT_INTERVAL = 10


class ServiceManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化动态间隔属性
        self._heartbeat_spacing = DEFAULT_HEARTBEAT_INTERVAL

    @periodic_task(spacing=DEFAULT_HEARTBEAT_INTERVAL, dynamic=True)
    async def heartbeat(self):
        """心跳任务，每次执行后间隔时间会翻倍"""
        LOG.info(
            f'Manager heartbeat at {time.time():.2f}, '
            f'current interval: {self._heartbeat_spacing}s'
        )
        # 动态修改下次执行的间隔时间（翻倍）
        self._heartbeat_spacing *= 2

        # 可以设置最大间隔限制，避免间隔过长
        if self._heartbeat_spacing > 180:  # 最大180秒
            self._heartbeat_spacing = 180
            LOG.info(
                f'Heartbeat interval reached maximum: {self._heartbeat_spacing}s'
            )

    @periodic_task(spacing=5, dynamic=True)
    async def status_check(self):
        """状态检查任务，演示另一种动态间隔模式"""
        LOG.info(f'Status check at {time.time():.2f}')

        # 如果没有设置动态间隔属性，则创建它
        if not hasattr(self, '_status_check_spacing'):
            self._status_check_spacing = 5

        # 根据某种条件动态调整间隔
        # 这里简单演示：随时间递增间隔
        self._status_check_spacing += 2

        # 设置间隔范围：5-30秒
        if self._status_check_spacing > 30:
            self._status_check_spacing = 5  # 重置到最小间隔
            LOG.info('Status check interval reset to minimum')


async def main():
    conf = ConfigOpts()
    manager = ServiceManager()
    service = DaemonService(conf, manager)
    launcher = await launch(conf=conf, service=service, workers=1)
    await launcher.wait()


if __name__ == '__main__':
    asyncio.run(main())
