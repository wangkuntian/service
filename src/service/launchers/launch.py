from service import ServiceBase
from service.config.common import ConfigOpts
from service.launchers.process_launcher import ProcessLauncher
from service.launchers.service_launcher import ServiceLauncher
from service.utils.log import LOG


async def launch(conf: ConfigOpts, service: ServiceBase, workers: int = 1):
    """Asynchronously start service (recommended new method)

    :param conf: an instance of ConfigOpts
    :param service: a service to launch, must be an instance of
           :class:`service.service.ServiceBase`
    :param workers: a number of processes in which a service will be running,
        type should be int.
    :returns: instance of a launcher that was used to launch the service
    """
    LOG.info(f'Launching service with {workers} workers')
    if workers is not None and not isinstance(workers, int):
        raise TypeError('Type of workers should be int!')

    if workers is not None and workers <= 0:
        raise ValueError('Number of workers should be positive!')

    if workers == 1:
        launcher = ServiceLauncher(conf)
    else:
        # Multi-process case
        launcher = ProcessLauncher(conf)

    await launcher.launch_service(service, workers=workers)

    return launcher
