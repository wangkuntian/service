import asyncio
import inspect
import random
import time
from time import monotonic as now
from typing import Any

from service.utils import reflection
from service.utils.log import LOG

DEFAULT_INTERVAL = 60.0


def _nearest_boundary(last_run: float | None, spacing: float) -> float:
    """Find the nearest boundary in the past.

    The boundary is a multiple of the spacing with the last run as an offset.

    Eg if last run was 10 and spacing was 7, the new last run could be: 17, 24,
    31, 38...

    0% to 5% of the spacing value will be added to this value to ensure tasks
    do not synchronize. This jitter is rounded to the nearest second, this
    means that spacings smaller than 20 seconds will not have jitter.
    """
    current_time = now()
    if last_run is None:
        return current_time
    delta = current_time - last_run
    offset = delta % spacing
    # Add up to 5% jitter
    jitter = int(spacing * (random.random() / 20))  # nosec
    return current_time - offset + jitter


class _PeriodicTasksMeta(type):
    def _add_periodic_task(cls, task: Any) -> bool:
        """Add a periodic task to the list of periodic tasks.

        The task should already be decorated by @periodic_task.

        :return: whether task was actually enabled
        """
        name = task._periodic_name

        if task._periodic_spacing < 0:
            LOG.info(
                f'Skipping periodic task {name} because '
                f'its interval {task._periodic_spacing} is negative',
            )
            return False
        if not task._periodic_enabled:
            LOG.info(f'Skipping periodic task {name} because it is disabled')
            return False

        # A periodic spacing of zero indicates that this task should
        # be run on the default interval to avoid running too
        # frequently.
        if task._periodic_spacing == 0:
            task._periodic_spacing = DEFAULT_INTERVAL

        cls._periodic_tasks.append((name, task))
        cls._periodic_spacing[name] = task._periodic_spacing
        return True

    def __init__(cls, names: Any, bases: Any, dict_: Any) -> None:
        """Metaclass that allows us to collect decorated periodic tasks."""
        super().__init__(names, bases, dict_)

        try:
            cls._periodic_tasks = cls._periodic_tasks[:]
        except AttributeError:
            cls._periodic_tasks = []

        try:
            cls._periodic_spacing = cls._periodic_spacing.copy()
        except AttributeError:
            cls._periodic_spacing = {}

        for value in cls.__dict__.values():
            if getattr(value, '_periodic_task', False):
                cls._add_periodic_task(value)


class PeriodicTasks(metaclass=_PeriodicTasksMeta):
    def __init__(self):
        super().__init__()
        self._periodic_last_run = {}
        for name, task in self._periodic_tasks:
            self._periodic_last_run[name] = task._periodic_last_run

    def add_periodic_task(self, task: Any) -> None:
        """Add a periodic task to the list of periodic tasks.

        The task should already be decorated by @periodic_task.
        """
        if self.__class__._add_periodic_task(task):
            self._periodic_last_run[task._periodic_name] = (
                task._periodic_last_run
            )

    def run_periodic_tasks(self, raise_on_error: bool = False) -> float:
        """Tasks to be run at a periodic interval."""
        idle_for = DEFAULT_INTERVAL
        for task_name, task in self._periodic_tasks:
            if (
                task._periodic_external_ok
                and hasattr(self, 'conf')
                and not self.conf.run_external_periodic_tasks
            ):
                continue
            cls_name = reflection.get_class_name(self, fully_qualified=False)
            full_task_name = '.'.join([cls_name, task_name])

            spacing = self._periodic_spacing[task_name]
            last_run = self._periodic_last_run[task_name]

            # Check if due, if not skip
            idle_for = min(idle_for, spacing)
            if last_run is not None:
                delta = last_run + spacing - now()
                if delta > 0:
                    idle_for = min(idle_for, delta)
                    continue

            LOG.debug(f'Running periodic task {full_task_name}')
            self._periodic_last_run[task_name] = _nearest_boundary(
                last_run, spacing
            )

            try:
                task(self)
            except BaseException:
                if raise_on_error:
                    raise
                LOG.exception(f'Error during {full_task_name}')
            time.sleep(0)

        return idle_for

    async def run_periodic_tasks_async(
        self, raise_on_error: bool = False
    ) -> float:
        """异步版本的周期性任务运行器。"""
        idle_for = DEFAULT_INTERVAL
        for task_name, task in self._periodic_tasks:
            if (
                task._periodic_external_ok
                and hasattr(self, 'conf')
                and not self.conf.run_external_periodic_tasks
            ):
                continue
            cls_name = reflection.get_class_name(self, fully_qualified=False)
            full_task_name = '.'.join([cls_name, task_name])

            spacing = self._periodic_spacing[task_name]
            last_run = self._periodic_last_run[task_name]

            # Check if due, if not skip
            idle_for = min(idle_for, spacing)
            if last_run is not None:
                delta = last_run + spacing - now()
                if delta > 0:
                    idle_for = min(idle_for, delta)
                    continue

            LOG.debug(f'Running periodic task {full_task_name}')
            self._periodic_last_run[task_name] = _nearest_boundary(
                last_run, spacing
            )

            try:
                # 检测任务是否为异步函数
                if inspect.iscoroutinefunction(task):
                    await task(self)
                else:
                    # 对于同步任务，在线程池中运行以避免阻塞事件循环
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, task, self)
            except BaseException:
                if raise_on_error:
                    raise
                LOG.exception(f'Error during {full_task_name}')

            # 使用异步sleep让出控制权
            await asyncio.sleep(0)

        return idle_for

    async def start_periodic_tasks_daemon(
        self, stop_event: asyncio.Event = None, raise_on_error: bool = False
    ) -> None:
        """Periodic tasks daemon.

        Args:
            stop_event: optional stop event, when set to stop running
            raise_on_error: whether to raise an exception when a task fails
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        LOG.info('Starting periodic tasks daemon')

        while not stop_event.is_set():
            try:
                idle_for = await self.run_periodic_tasks_async(raise_on_error)
                # Wait for the specified time or until the stop event is set
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=idle_for)
                    break  # Stop event is set
                except TimeoutError:
                    continue  # Timeout, continue to the next round
            except BaseException:
                if raise_on_error:
                    raise
                LOG.exception('Periodic tasks daemon running error')
                await asyncio.sleep(1)  # Wait 1 second after error

        LOG.info('Periodic tasks daemon stopped')


def periodic_task(
    spacing: float = 0, enabled: bool = True, external_ok: bool = True
):
    """Decorator for marking periodic tasks.

    Args:
        spacing: task execution interval (seconds)
        enabled: whether to enable the task
        external_ok: whether to allow running in external processes
    """

    def decorator(func):
        func._periodic_task = True
        func._periodic_name = func.__name__
        func._periodic_spacing = spacing
        func._periodic_enabled = enabled
        func._periodic_external_ok = external_ok
        func._periodic_last_run = None
        return func

    return decorator


def async_periodic_task(
    spacing: float = 0, enabled: bool = True, external_ok: bool = True
):
    """Decorator for marking asynchronous periodic tasks.

    Args:
        spacing: task execution interval (seconds)
        enabled: whether to enable the task
        external_ok: whether to allow running in external processes
    """

    def decorator(func):
        # Ensure the function is asynchronous
        if not inspect.iscoroutinefunction(func):
            raise ValueError(
                f'@async_periodic_task decorated function {func.__name__} '
                'must be an asynchronous function'
            )

        func._periodic_task = True
        func._periodic_name = func.__name__
        func._periodic_spacing = spacing
        func._periodic_enabled = enabled
        func._periodic_external_ok = external_ok
        func._periodic_last_run = None
        return func

    return decorator


if __name__ == '__main__':

    class Test(PeriodicTasks):
        def __init__(self):
            super().__init__()
            self.conf = type(
                'Config', (), {'run_external_periodic_tasks': True}
            )()

        @periodic_task(spacing=2.0)
        def sync_task(self):
            print('同步任务执行')

        @async_periodic_task(spacing=3.0)
        async def async_task(self):
            print('异步任务开始')
            await asyncio.sleep(1)  # 模拟异步操作
            print('异步任务完成')

    async def main():
        test = Test()
        stop_event = asyncio.Event()

        # 创建一个任务来运行周期性任务守护进程
        daemon_task = asyncio.create_task(
            test.start_periodic_tasks_daemon(stop_event)
        )

        try:
            # 运行10秒后停止
            await asyncio.sleep(10)
            stop_event.set()
            await daemon_task
        except KeyboardInterrupt:
            print('收到中断信号，停止任务...')
            stop_event.set()
            await daemon_task

    # 运行示例
    asyncio.run(main())
