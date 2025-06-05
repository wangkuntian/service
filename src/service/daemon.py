import time

from service import Service
from service.periodic_task import PeriodicTasks, periodic_task
from service.utils.log import LOG


class Manager(PeriodicTasks):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # @periodic_task(spacing=30)
    # async def heartbeat(self):
    #     LOG.info(f'Manager heartbeat at {time.time():.2f}')


class DaemonService(Service):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.manager = Manager()

    async def start(self):
        self.tg.add_dynamic_timer(
            self.manager.run_periodic_tasks_async,
            initial_delay=3,
            periodic_interval_max=30,
        )

    async def stop(self):
        await super().stop()
