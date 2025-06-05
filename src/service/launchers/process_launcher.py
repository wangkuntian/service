import asyncio
import errno
import gc
import os
import random
import signal
import sys
import threading
import time

import setproctitle

from service import ServiceBase, systemd
from service.config.common import ConfigOpts
from service.launchers.base import Launcher
from service.utils.log import LOG


def _is_sighup_and_daemon(signo: int) -> bool:
    """Check if it's SIGHUP signal and in daemon mode"""
    return signo == signal.SIGHUP


def _check_service_base(service: ServiceBase) -> None:
    if not isinstance(service, ServiceBase):
        raise TypeError(
            f'Service {service} must an instance of {ServiceBase}!'
        )


class SignalExit(SystemExit):
    def __init__(self, signo: int, exccode: int = 1):
        super().__init__(exccode)
        self.signo = signo


class ServiceWrapper:
    def __init__(self, service: ServiceBase, workers: int):
        self.service = service
        self.workers = workers
        self.children: set[int] = set()
        self.forktimes: list[float] = []


class ProcessLauncher(Launcher):
    """Async version of ProcessLauncher, using asyncio features to
    optimize performance and resource usage."""

    def __init__(
        self,
        conf: ConfigOpts = ConfigOpts(),
        wait_interval: float = 0.01,
    ):
        """Constructor.

        :param conf: an instance of ConfigOpts
        :param wait_interval: The interval to sleep for between checks
                              of child process exit.
        """
        self.conf = conf
        self.children = {}
        self.sigcaught = None
        self.running = True

        # get configurable parameters from config
        self.wait_interval = getattr(
            conf, 'child_monitor_interval', wait_interval
        )

        self.launcher = None

        # optimize file descriptor management
        try:
            rfd, self.writepipe = os.pipe()
            # set non-blocking mode and non-inheritable
            os.set_inheritable(rfd, False)
            os.set_inheritable(self.writepipe, False)
            self.readpipe = os.fdopen(rfd, 'r')
        except OSError as e:
            LOG.error(f'Failed to create pipe: {e}')
            raise

        # asyncio enhanced features
        self._shutdown_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._child_monitor_task = None
        self._signal_handlers_setup = False

    async def _setup_signal_handlers(self):
        """Setup async signal handlers."""
        if self._signal_handlers_setup:
            return

        try:
            loop = asyncio.get_running_loop()

            # Use asyncio signal handling
            loop.add_signal_handler(signal.SIGTERM, self._handle_term)
            loop.add_signal_handler(signal.SIGHUP, self._handle_hup)
            loop.add_signal_handler(signal.SIGINT, self._handle_int)

            # Add SIGALRM handler only if supported
            try:
                loop.add_signal_handler(signal.SIGALRM, self._handle_alarm)
            except (OSError, NotImplementedError):
                LOG.warning(
                    'SIGALRM signal handler not supported on this platform'
                )

            self._signal_handlers_setup = True
            LOG.debug('Async signal handlers setup completed')

        except Exception as e:
            LOG.error(f'Failed to setup async signal handlers: {e}')
            raise

    def _handle_term(self):
        """Async handle TERM signal."""
        LOG.info('Received SIGTERM, initiating graceful shutdown')
        self.sigcaught = signal.SIGTERM
        self.running = False
        self._shutdown_event.set()

    def _handle_hup(self):
        """Async handle HUP signal."""
        LOG.info('Received SIGHUP, initiating restart')
        self.sigcaught = signal.SIGHUP
        self.running = False
        self._restart_event.set()

    def _handle_int(self):
        """Async handle INT signal."""
        LOG.info('Received SIGINT, immediate exit')
        os._exit(1)

    def _handle_alarm(self):
        """Async handle ALARM signal."""
        LOG.info('Graceful shutdown timeout exceeded, immediate exit')
        os._exit(1)

    async def _child_process_launcher(self, service: ServiceBase) -> Launcher:
        """Async child process creation logic."""
        # Setup async signal handling for child process
        await self._child_setup_async_signals()

        # Close write end, ensure only parent process holds
        os.close(self.writepipe)
        # Start parent process monitor thread
        threading.Thread(target=self._pipe_watcher, daemon=True).start()

        # Reinitialize random seed
        random.seed()

        launcher = Launcher(self.conf)
        await launcher.launch_service(service)
        return launcher

    # Run async child process logic
    async def child_main_process(self, wrap: ServiceWrapper):
        LOG.debug('Starting child main process')
        self.launcher = await self._child_process_launcher(wrap.service)
        while True:
            (
                status,
                signo,
            ) = await self._child_wait_for_exit_or_signal(self.launcher)
            if not _is_sighup_and_daemon(signo):
                await self.launcher.wait()
                break
            # Restart launcher
            await self.launcher.restart()
        return status

    async def _start_child(self, wrap: ServiceWrapper) -> int:
        """Async start child process,
        using asyncio.sleep instead of blocking sleep."""
        LOG.debug('Starting child process')
        try:
            wrap.forktimes.append(time.time())
            pid = os.fork()
            if pid == 0:
                # Child process logic - now fully async
                try:
                    setproctitle.setproctitle(f'service-worker-{os.getpid()}')
                    # Run the async child main function
                    status = asyncio.run(self.child_main_process(wrap))
                    os._exit(status)
                except Exception as e:
                    LOG.error(f'Child process error: {e}')
                    os._exit(1)
            LOG.debug(f'Started child process {pid}')
            wrap.children.add(pid)
            self.children[pid] = wrap
            return pid
        except Exception as e:
            LOG.error(f'Unexpected error starting child process: {e}')
            raise

    async def _monitor_children(self):
        """Async monitor children, using event-driven instead of polling."""
        LOG.debug('Starting async child monitor')

        while self.running:
            try:
                # Use async sleep instead of blocking sleep,
                # allow other coroutines to execute
                await asyncio.sleep(self.wait_interval)

                wrap = self._wait_child()
                if wrap:
                    LOG.info(
                        f'Child died, respawning. '
                        f'Current children: {len(wrap.children)}, '
                        f'target: {wrap.workers}'
                    )
                    # Found dead child,
                    # async restart required number of children
                    tasks = []
                    workers_to_start = wrap.workers - len(wrap.children)
                    for i in range(workers_to_start):
                        if not self.running:
                            break
                        task = asyncio.create_task(self._start_child(wrap))
                        tasks.append(task)

                    # Concurrent start all required children
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                LOG.debug('Child monitor cancelled')
                break
            except Exception as e:
                LOG.error(f'Error in async child monitor: {e}')
                # Also use async sleep when error occurs
                await asyncio.sleep(self.wait_interval)

    async def _child_setup_async_signals(self):
        """Setup async signal handlers for child process."""
        try:
            loop = asyncio.get_running_loop()

            # Use asyncio signal handling for child process
            loop.add_signal_handler(signal.SIGTERM, self._child_handle_term)
            loop.add_signal_handler(signal.SIGHUP, self._child_handle_hup)
            loop.add_signal_handler(signal.SIGINT, self._child_handle_int)

            LOG.debug('Child async signal handlers setup completed')

        except Exception as e:
            LOG.error(f'Failed to setup child async signal handlers: {e}')
            raise

    def _child_handle_term(self):
        """Async handle TERM signal in child process."""
        LOG.info('Child received SIGTERM, stopping launcher')
        if self.launcher:
            # Create task to stop launcher asynchronously
            asyncio.create_task(self.launcher.stop())

    def _child_handle_hup(self):
        """Async handle HUP signal in child process."""
        LOG.info('Child received SIGHUP, raising SignalExit')
        raise SignalExit(signal.SIGHUP)

    def _child_handle_int(self):
        """Async handle INT signal in child process."""
        LOG.info('Child received SIGINT, immediate exit')
        os._exit(1)

    async def _child_wait_for_exit_or_signal(
        self, launcher: Launcher
    ) -> tuple[int, int]:
        """Child process async wait logic."""
        status = 0
        signo = 0

        try:
            await launcher.wait()
        except SignalExit as exc:
            LOG.info(f'Child caught signal {exc.signo}')
            status = exc.code
            signo = exc.signo
        except SystemExit as exc:
            await launcher.stop()
            status = exc.code
        except BaseException as e:
            LOG.exception(f'Unhandled exception in child: {e}')
            await launcher.stop()
            status = 2
        finally:
            await LOG.complete()

        return status, signo

    def _pipe_watcher(self):
        """Monitor parent process pipe."""
        try:
            self.readpipe.read(1)
        except Exception:
            pass

        LOG.info('Parent process died unexpectedly, exiting child')
        if self.launcher:
            try:
                asyncio.run(self.launcher.stop())
            except Exception as e:
                LOG.error(f'Error stopping launcher: {e}')
        sys.exit(1)

    def _wait_child(self) -> ServiceWrapper | None:
        """Non-blocking wait for child process exit."""
        try:
            pid, status = os.waitpid(0, os.WNOHANG)
            if not pid:
                return None
        except OSError as exc:
            if exc.errno not in (errno.EINTR, errno.ECHILD):
                raise
            return None

        # Record child process exit information
        if os.WIFSIGNALED(status):
            sig = os.WTERMSIG(status)
            LOG.info(f'Child {pid} killed by signal {sig}')
        else:
            code = os.WEXITSTATUS(status)
            LOG.info(f'Child {pid} exited with status {code}')

        if pid not in self.children:
            LOG.warning(f'Unknown child pid {pid}')
            return None

        wrap = self.children.pop(pid)
        wrap.children.remove(pid)
        return wrap

    async def launch_service(
        self, service: ServiceBase, workers: int = 1
    ) -> None:
        """Async start service."""
        _check_service_base(service)
        wrap = ServiceWrapper(service, workers)

        gc.freeze()

        LOG.info(f'Starting {wrap.workers} workers asynchronously')

        # Setup async signal handling
        await self._setup_signal_handlers()

        # Concurrent start all worker processes
        tasks = []
        for i in range(wrap.workers):
            if not self.running:
                break
            LOG.debug('Starting child process ....')
            task = asyncio.create_task(self._start_child(wrap))
            tasks.append(task)

        # Wait for all worker processes to start
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Check startup results
            failed_count = sum(1 for r in results if isinstance(r, Exception))
            if failed_count > 0:
                LOG.warning(f'{failed_count} worker processes failed to start')

        # Start async child process monitor task
        if self.running:
            self._child_monitor_task = asyncio.create_task(
                self._monitor_children()
            )
            LOG.debug('Child monitor task started')

    async def wait(self) -> int:
        """Async wait for service completion,
        using event-driven instead of polling."""
        systemd.notify_once()

        if self.conf.log_options:
            LOG.debug('Full set of CONF:')
            LOG.debug(self.conf)

        try:
            while self.running:
                # Use asyncio event waiting instead of busy polling
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._shutdown_event.wait()),
                        asyncio.create_task(self._restart_event.wait()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=None,  # Wait until event occurs
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check signal handling result
                if not self.sigcaught:
                    LOG.info('No signal caught, normal shutdown')
                    break

                signame = getattr(
                    signal, f'SIG{self.sigcaught}', str(self.sigcaught)
                )
                LOG.info(f'Caught signal {signame}, processing')

                if not _is_sighup_and_daemon(self.sigcaught):
                    LOG.info('Terminating due to signal')
                    break

                # SIGHUP - restart services
                LOG.info('Restarting services due to SIGHUP')
                await self._restart_services()

        except KeyboardInterrupt:
            LOG.info('Received KeyboardInterrupt, cleaning up')
        except Exception as e:
            LOG.error(f'Error in wait loop: {e}')

        # Graceful shutdown
        if self.conf.graceful_shutdown_timeout and hasattr(signal, 'SIGALRM'):
            signal.alarm(self.conf.graceful_shutdown_timeout)

        await self.stop()
        return 0

    async def _restart_services(self):
        """Async restart services."""
        # Send SIGTERM to all children
        child_signal = signal.SIGTERM
        for service in {wrap.service for wrap in self.children.values()}:
            try:
                service.reset()
            except Exception as e:
                LOG.error(f'Error resetting service: {e}')

        for pid in list(self.children.keys()):
            try:
                os.kill(pid, child_signal)
            except OSError as e:
                LOG.warning(f'Failed to send signal to child {pid}: {e}')

        # Reset state
        self.running = True
        self.sigcaught = None
        self._shutdown_event.clear()
        self._restart_event.clear()

    async def stop(self):
        """Async stop all children and tasks."""
        LOG.info('Stopping ProcessLauncher')
        self.running = False

        # Stop child process monitor task
        if self._child_monitor_task and not self._child_monitor_task.done():
            LOG.debug('Cancelling child monitor task')
            self._child_monitor_task.cancel()
            try:
                await self._child_monitor_task
            except asyncio.CancelledError:
                LOG.debug('Child monitor task cancelled successfully')

        # Stop all services
        LOG.debug('Stopping services')
        for service in {wrap.service for wrap in self.children.values()}:
            try:
                service.stop()
            except Exception as e:
                LOG.error(f'Error stopping service: {e}')

        # Terminate all children
        LOG.debug('Terminating child processes')
        for pid in list(self.children.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError as exc:
                if exc.errno != errno.ESRCH:
                    LOG.error(f'Error killing child {pid}: {exc}')

        # Async wait for children to exit
        if self.children:
            LOG.info(f'Waiting for {len(self.children)} children to exit')
            timeout = 30  # 30 seconds timeout
            start_time = time.time()

            while self.children and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)  # Async sleep
                self._wait_child()

            # If there are still children, force kill
            if self.children:
                LOG.warning(
                    f'Force killing {len(self.children)} remaining children'
                )
                for pid in list(self.children.keys()):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError as e:
                        LOG.error(f'Error force killing child {pid}: {e}')

        # Cleanup signal handlers
        await self._cleanup_signal_handlers()
        LOG.info('ProcessLauncher stopped')

    async def _cleanup_signal_handlers(self):
        """Cleanup async signal handlers."""
        if not self._signal_handlers_setup:
            return

        try:
            loop = asyncio.get_running_loop()

            # Remove signal handlers
            try:
                loop.remove_signal_handler(signal.SIGTERM)
                loop.remove_signal_handler(signal.SIGHUP)
                loop.remove_signal_handler(signal.SIGINT)
                loop.remove_signal_handler(signal.SIGALRM)
            except (ValueError, OSError):
                pass

            self._signal_handlers_setup = False
            LOG.debug('Signal handlers cleaned up')

        except Exception as e:
            LOG.warning(f'Error cleaning up signal handlers: {e}')
