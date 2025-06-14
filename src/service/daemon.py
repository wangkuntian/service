from service import Service
from service.config.common import ConfigOpts
from service.periodic_task import PeriodicTasks


class Manager(PeriodicTasks):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def start(self):
        pass

    async def stop(self):
        pass


class DaemonService(Service):
    def __init__(self, conf: ConfigOpts, manager: Manager, *args, **kwargs):
        if not isinstance(manager, Manager):
            raise ValueError('manager must be an instance of Manager')
        super().__init__(*args, **kwargs)
        self.conf = conf
        self.manager = manager

    async def start(self):
        self.tg.add_dynamic_timer(
            self.manager.run_periodic_tasks,
            initial_delay=self.conf.initial_delay,
            periodic_interval_max=self.conf.periodic_interval_max,
        )
        await self.manager.start()

    async def stop(self):
        await self.manager.stop()
        await super().stop()
