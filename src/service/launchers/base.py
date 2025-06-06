from service import ServiceBase, Services
from service.config.common import ConfigOpts
from service.utils.log import LOG


def _check_service_base(service: ServiceBase) -> None:
    if not isinstance(service, ServiceBase):
        raise TypeError(
            f'Service {service} must an instance of {ServiceBase}!'
        )


class Launcher:
    """Launch one or more services and wait for them to complete."""

    def __init__(
        self, conf: ConfigOpts, services: Services = Services()
    ):
        """Initialize the service launcher.
        :returns: None

        """
        self.conf = conf
        self.services = services

    async def launch_service(
        self, service: ServiceBase, workers: int = 1
    ) -> None:
        """Load and start the given service.

        :param service: The service you would like to start, must be an
                        instance of :class:`service.ServiceBase`
        :param workers: This param makes this method compatible with
                        ProcessLauncher.launch_service. It must be None, 1 or
                        omitted.
        :returns: None

        """
        if workers is not None and workers != 1:
            raise ValueError('Launcher asked to start multiple workers')
        _check_service_base(service)
        await self.services.add(service)

    async def stop(self):
        """Stop all services which are currently running.

        :returns: None

        """
        await self.services.stop()

    async def wait(self):
        """Wait until all services have been stopped, and then return.

        :returns: None

        """
        await self.services.wait()

    async def restart(self):
        """Reload config files and restart service.

        :returns: None
        """
        await self.services.restart()

    async def run(self):
        """Run the launcher in async mode.

        This method starts all services and waits for them to complete.
        It's the main entry point for async usage.

        :returns: None
        """
        try:
            await self.wait()
        except KeyboardInterrupt:
            LOG.info('Caught KeyboardInterrupt, stopping services...')
            await self.stop()
        except Exception as e:
            LOG.exception(f'Unexpected error in launcher: {e}')
            await self.stop()
            raise
