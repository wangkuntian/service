"""
动态间隔示例：演示如何使用 periodic_task 的 dynamic 参数
实现各种间隔时间的动态调整策略
"""

import asyncio
import random
import time

from service.config.common import ConfigOpts
from service.daemon import DaemonService, Manager
from service.launchers import launch
from service.periodic_task import periodic_task
from service.utils.log import LOG


class DynamicSpacingManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化各种动态间隔属性
        self._exponential_backoff_spacing = 1  # 指数退避间隔
        self._adaptive_spacing = 10  # 自适应间隔
        self._oscillating_spacing = 5  # 振荡间隔
        self._condition_based_spacing = 3  # 基于条件的间隔

        # 用于演示的状态变量
        self.error_count = 0
        self.system_load = 0.5
        self.oscillation_direction = 1

    @periodic_task(spacing=1, dynamic=True)
    async def exponential_backoff_task(self):
        """
        指数退避策略：当发生错误时，间隔时间指数增长
        适用场景：网络重试、外部服务调用等
        """
        try:
            # 模拟可能失败的操作
            if random.random() < 0.3:  # 30% 的失败率
                raise Exception('模拟的错误')

            LOG.info(
                f'指数退避任务成功执行，当前间隔: {self._exponential_backoff_spacing}s'
            )
            # 成功时重置间隔
            self._exponential_backoff_spacing = 1
            self.error_count = 0

        except Exception as e:
            self.error_count += 1
            LOG.warning(f'指数退避任务失败 (第{self.error_count}次): {e}')

            # 指数增长间隔，但设置上限
            self._exponential_backoff_spacing = min(
                self._exponential_backoff_spacing * 2,
                60,  # 最大60秒
            )
            LOG.info(
                f'下次重试间隔调整为: {self._exponential_backoff_spacing}s'
            )

    @periodic_task(spacing=10, dynamic=True)
    async def adaptive_task(self):
        """
        自适应间隔策略：根据系统负载动态调整间隔
        适用场景：系统监控、资源使用检查等
        """
        # 模拟系统负载变化
        self.system_load += random.uniform(-0.1, 0.1)
        self.system_load = max(0.1, min(1.0, self.system_load))

        LOG.info(f'自适应任务执行，系统负载: {self.system_load:.2f}')

        # 根据系统负载调整间隔：负载高时间隔更长
        if self.system_load > 0.8:
            self._adaptive_spacing = 30  # 高负载时降低检查频率
        elif self.system_load > 0.5:
            self._adaptive_spacing = 15  # 中等负载
        else:
            self._adaptive_spacing = 5  # 低负载时提高检查频率

        LOG.info(f'基于负载调整间隔为: {self._adaptive_spacing}s')

    @periodic_task(spacing=5, dynamic=True)
    async def oscillating_task(self):
        """
        振荡间隔策略：间隔时间在一定范围内振荡
        适用场景：需要避免与其他系统同步的任务
        """
        LOG.info(f'振荡间隔任务执行，当前间隔: {self._oscillating_spacing}s')

        # 在5-15秒之间振荡
        self._oscillating_spacing += 2 * self.oscillation_direction

        if self._oscillating_spacing >= 15:
            self.oscillation_direction = -1
        elif self._oscillating_spacing <= 5:
            self.oscillation_direction = 1

        LOG.info(f'振荡间隔调整为: {self._oscillating_spacing}s')

    @periodic_task(spacing=3, dynamic=True)
    async def condition_based_task(self):
        """
        基于条件的间隔策略：根据业务条件动态调整
        适用场景：业务逻辑相关的定时任务
        """
        current_hour = time.localtime().tm_hour

        LOG.info(f'条件基础任务执行，当前时间: {current_hour}:xx')

        # 根据时间段调整间隔
        if 9 <= current_hour <= 17:  # 工作时间
            self._condition_based_spacing = 2  # 更频繁检查
            LOG.info('工作时间：设置为高频检查 (2s)')
        elif 18 <= current_hour <= 22:  # 晚间
            self._condition_based_spacing = 5  # 中等频率
            LOG.info('晚间时间：设置为中频检查 (5s)')
        else:  # 深夜/凌晨
            self._condition_based_spacing = 10  # 低频率
            LOG.info('深夜时间：设置为低频检查 (10s)')

    @periodic_task(spacing=20, dynamic=False)  # 对比：固定间隔任务
    async def fixed_interval_task(self):
        """
        固定间隔任务：用于对比，展示传统的固定间隔行为
        """
        LOG.info('固定间隔任务执行 (每20秒)')

    def get_dynamic_spacing(self, task_name: str) -> float:
        """
        获取指定任务的动态间隔值
        这是一个辅助方法，用于监控和调试
        """
        spacing_attr = f'_{task_name}_spacing'
        return getattr(self, spacing_attr, None)

    async def print_status(self):
        """打印所有动态任务的当前间隔状态"""
        LOG.info('=== 动态间隔状态 ===')
        tasks = [
            'exponential_backoff_task',
            'adaptive_task',
            'oscillating_task',
            'condition_based_task',
        ]
        for task in tasks:
            spacing = self.get_dynamic_spacing(task)
            if spacing:
                LOG.info(f'{task}: {spacing}s')


async def main():
    """主函数：启动服务并运行一段时间后停止"""
    conf = ConfigOpts()
    manager = DynamicSpacingManager()
    service = DaemonService(conf, manager)

    # 启动服务
    launcher = await launch(conf=conf, service=service, workers=1)

    # 运行一段时间后停止（用于演示）
    try:
        # 每30秒打印一次状态
        for i in range(6):  # 运行3分钟
            await asyncio.sleep(30)
            await manager.print_status()
    except KeyboardInterrupt:
        LOG.info('收到中断信号，正在停止...')
    finally:
        # 这里可以添加清理代码
        pass


if __name__ == '__main__':
    asyncio.run(main())
