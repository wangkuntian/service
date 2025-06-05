import abc
import asyncio

from service.periodic_task import PeriodicTasks
from service.taskgroup import TaskGroup
from service.utils.log import LOG


class ServiceBase(metaclass=abc.ABCMeta):
    """Base class for all services."""

    @abc.abstractmethod
    async def start(self):
        """Start service."""

    @abc.abstractmethod
    async def stop(self):
        """Stop service."""

    @abc.abstractmethod
    async def wait(self):
        """Wait for service to complete."""

    @abc.abstractmethod
    async def reset(self):
        """Reset service.

        Called in case service running in daemon mode receives SIGHUP.
        """


class Service(ServiceBase):
    """Service object for binaries running on hosts."""

    def __init__(self, max_concurrent_tasks: int = 10):
        self.tg = TaskGroup(max_concurrent_tasks=max_concurrent_tasks)

    async def reset(self):
        """Reset a service in case it received a SIGHUP."""

    async def start(self):
        """Start a service."""

    async def stop(self, graceful=False):
        """Stop a service.

        :param graceful: indicates whether to wait for all tasks to finish
               or terminate them instantly
        """
        await self.tg.stop(graceful=graceful)

    async def wait(self):
        """Wait for a service to shut down."""
        await self.tg.wait()


class Services:
    def __init__(self, max_concurrent_tasks: int = 1000):
        self.services = []
        self.tg = TaskGroup(max_concurrent_tasks)
        self.done = asyncio.Event()

    async def add(self, service):
        """Add a service to a list and create a task to run it.

        :param service: service to run
        """
        self.services.append(service)
        await self.tg.add_task(self.run_service, service, self.done)

    async def stop(self):
        """Wait for graceful shutdown of services and stop the tasks."""
        for service in self.services:
            await service.stop()

        # Each service has performed cleanup, now signal that the run_service
        # wrapper tasks can now die:
        if not self.done.is_set():
            self.done.set()

        # reap tasks:
        await self.tg.stop()

    async def wait(self):
        """Wait for services to shut down."""
        for service in self.services:
            await service.wait()
        await self.tg.wait()

    async def restart(self):
        """Reset services."""
        await self.stop()
        self.done = asyncio.Event()
        for restart_service in self.services:
            await restart_service.reset()
            await self.tg.add_task(
                self.run_service, restart_service, self.done
            )

    @staticmethod
    async def run_service(service: ServiceBase, done: asyncio.Event):
        """Service start wrapper.

        :param service: service to run
        :param done: event to wait on until a shutdown is triggered
        :returns: None

        """
        try:
            await service.start()
        except Exception:
            LOG.exception('Error starting service.')
            raise SystemExit(1)
        else:
            await done.wait()
