import asyncio
import os
import signal
import sys
import threading
import time

from service import ServiceBase, systemd
from service.config.common import ConfigOpts
from service.constants import ExitCodes
from service.launchers.base import Launcher
from service.utils.log import LOG


def _is_sighup_and_daemon(signo: int) -> bool:
    """Check if it's SIGHUP signal and in daemon mode"""
    return signo == signal.SIGHUP


class ServiceLauncher(Launcher):
    """Async optimized version of ServiceLauncher,
    using asyncio features to improve performance and responsiveness."""

    def __init__(self, conf: ConfigOpts):
        """Constructor.

        :param conf: an instance of ConfigOpts
        """
        super().__init__(conf)

        self._cleanup_tasks = set()

        # asyncio enhanced features
        self._shutdown_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._signal_handlers_setup = False

        self._shutdown_timeout = self.conf.graceful_shutdown_timeout

        # Enhanced monitoring and health check
        self._start_time = None
        self._restart_count = 0
        self._last_restart_time = None
        self._health_monitor_task = None
        self._shutdown_timeout_task = None

        # Performance metrics with thread-safe updates
        self._metrics_lock = asyncio.Lock()
        self._metrics = {
            'restart_count': 0,
            'uptime_seconds': 0,
            'last_health_check': None,
            'error_count': 0,
        }

    async def _cleanup_background_tasks(self):
        """Cleanup background tasks gracefully with improved error handling."""
        tasks_to_cleanup = []

        # Add health monitor task
        if self._health_monitor_task and not self._health_monitor_task.done():
            tasks_to_cleanup.append(self._health_monitor_task)

        # Add shutdown timeout task
        if (
            self._shutdown_timeout_task
            and not self._shutdown_timeout_task.done()
        ):
            tasks_to_cleanup.append(self._shutdown_timeout_task)

        # Add any other cleanup tasks
        tasks_to_cleanup.extend(
            [t for t in self._cleanup_tasks if not t.done()]
        )

        if not tasks_to_cleanup:
            LOG.debug('No background tasks to cleanup')
            return

        LOG.debug(f'Cleaning up {len(tasks_to_cleanup)} background tasks')

        # Cancel all tasks
        for task in tasks_to_cleanup:
            if not task.done():
                task.cancel()

        # Wait for cancellation with timeout and proper error handling
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks_to_cleanup, return_exceptions=True),
                timeout=5.0,
            )
            LOG.debug('All background tasks cleaned up successfully')
        except TimeoutError:
            LOG.warning(
                'Some background tasks did not finish cleanup within timeout'
            )
        except Exception as e:
            LOG.error(f'Error during background task cleanup: {e}')

        # Clear the cleanup tasks set
        self._cleanup_tasks.clear()

    async def run(self) -> int:
        """Async run service launcher main method
        with enhanced error handling."""
        try:
            return await self.wait()
        except Exception as e:
            LOG.exception(f'ServiceLauncher run failed: {e}')
            async with self._metrics_lock:
                self._metrics['error_count'] += 1
            await self.stop()
            raise

    async def launch_service(
        self, service: ServiceBase, workers: int = 1
    ) -> None:
        """Load and start the given service with enhanced monitoring."""
        self._start_time = time.time()
        LOG.info(
            f'ServiceLauncher starting service '
            f'at {time.ctime(self._start_time)}'
        )

        # Reset metrics
        async with self._metrics_lock:
            self._metrics['restart_count'] = 0
            self._metrics['error_count'] = 0

        await super().launch_service(service, workers)

    def get_health_status(self) -> dict:
        """Get comprehensive health status of the launcher."""
        current_time = time.time()
        uptime = current_time - self._start_time if self._start_time else 0

        # Create a snapshot of metrics to avoid race conditions
        metrics_snapshot = None
        try:
            # Non-blocking attempt to get metrics
            if not self._metrics_lock.locked():
                # If lock is available, get current metrics
                metrics_snapshot = self._metrics.copy()
            else:
                # If locked, return cached values or defaults
                metrics_snapshot = {
                    'restart_count': self._restart_count,
                    'uptime_seconds': uptime,
                    'last_health_check': 'locked',
                    'signal_count': 'locked',
                    'error_count': 'locked',
                }
        except Exception as e:
            LOG.warning(f'Error getting health metrics: {e}')
            metrics_snapshot = {'error': str(e)}

        return {
            'status': 'running' if self._start_time else 'not_started',
            'uptime_seconds': uptime,
            'restart_count': self._restart_count,
            'last_restart_time': self._last_restart_time,
            'signal_handlers_setup': self._signal_handlers_setup,
            'health_check_interval': self.conf.service_health_check_interval,
            'metrics': metrics_snapshot,
            'background_tasks': {
                'health_monitor_running': (
                    self._health_monitor_task
                    and not self._health_monitor_task.done()
                ),
                'shutdown_timeout_running': (
                    self._shutdown_timeout_task
                    and not self._shutdown_timeout_task.done()
                ),
                'cleanup_tasks_count': len(self._cleanup_tasks),
            },
        }

    async def restart(self):
        """Reload config files and restart service with enhanced monitoring."""
        self._restart_count += 1
        self._last_restart_time = time.time()
        async with self._metrics_lock:
            self._metrics['restart_count'] = self._restart_count

        LOG.info(
            f'AsyncServiceLauncher restart #{self._restart_count} '
            f'at {time.ctime(self._last_restart_time)}'
        )

        try:
            await super().restart()
            LOG.info(
                f'AsyncServiceLauncher restart #{self._restart_count} '
                'completed successfully'
            )
        except Exception as e:
            LOG.error(
                f'AsyncServiceLauncher restart #{self._restart_count} '
                f'failed: {e}'
            )
            async with self._metrics_lock:
                self._metrics['error_count'] += 1
            raise

    async def stop(self):
        """Stop all services and clean up resources asynchronously."""
        LOG.info('Stopping ServiceLauncher')

        # Cancel shutdown timeout task first to prevent unnecessary waiting
        if (
            self._shutdown_timeout_task
            and not self._shutdown_timeout_task.done()
        ):
            LOG.debug('Cancelling shutdown timeout task')
            self._shutdown_timeout_task.cancel()
            try:
                await self._shutdown_timeout_task
            except asyncio.CancelledError:
                LOG.debug('Shutdown timeout task cancelled successfully')

        # Cleanup background tasks first
        await self._cleanup_background_tasks()

        # Stop parent services
        await super().stop()

        # Cleanup signal handlers
        await self._cleanup_signal_handlers()

        LOG.info('ServiceLauncher stopped')

    async def _cleanup_signal_handlers(self):
        """Cleanup async signal handlers with improved error handling."""
        if not self._signal_handlers_setup:
            return

        try:
            loop = asyncio.get_running_loop()

            # List of signals to cleanup
            signals_to_remove = [
                signal.SIGTERM,
                signal.SIGHUP,
                signal.SIGINT,
                signal.SIGALRM,
            ]

            # Remove signal handlers with individual error handling
            for sig in signals_to_remove:
                try:
                    loop.remove_signal_handler(sig)
                except (ValueError, OSError, NotImplementedError) as e:
                    LOG.debug(
                        f'Could not remove signal handler for {sig}: {e}'
                    )

            self._signal_handlers_setup = False
            LOG.debug('Signal handlers cleaned up')

        except RuntimeError as e:
            if 'no running event loop' in str(e).lower():
                LOG.debug(
                    'No event loop running, signal handlers already cleaned'
                )
            else:
                LOG.warning(f'Error cleaning up signal handlers: {e}')
        except Exception as e:
            LOG.warning(f'Error cleaning up signal handlers: {e}')

    def add_cleanup_task(self, task: asyncio.Task):
        """Add a task to be cleaned up on shutdown with improved management."""
        self._cleanup_tasks.add(task)

        # Remove completed tasks automatically with error handling
        def remove_when_done(t):
            try:
                if t in self._cleanup_tasks:
                    self._cleanup_tasks.remove(t)
            except KeyError:
                pass  # Task already removed
            except Exception as e:
                LOG.warning(
                    f'Error removing completed task from cleanup set: {e}'
                )

        task.add_done_callback(remove_when_done)

    async def _save_error(self):
        async with self._metrics_lock:
            self._metrics['error_count'] += 1

    async def _handle_timeout_exit(self):
        """Async timeout handler with improved cleanup - acts as a safety net"""
        try:
            await asyncio.sleep(self._shutdown_timeout)
            LOG.warning(
                f'Graceful shutdown timeout '
                f'({self._shutdown_timeout}s) exceeded'
            )
            LOG.info(
                'Graceful shutdown timeout exceeded, forcing cleanup and exit'
            )

            try:
                await asyncio.wait_for(
                    self._cleanup_background_tasks(), timeout=2.0
                )
            except asyncio.TimeoutError:
                LOG.warning('Background task cleanup timed out')
            except Exception as e:
                LOG.error(f'Error during forced cleanup: {e}')

            # Force exit after timeout
            LOG.critical('Forcing immediate exit due to shutdown timeout')
            os._exit(1)
        except asyncio.CancelledError:
            LOG.debug('Shutdown timeout cancelled - normal shutdown completed')
            # This is expected when normal shutdown completes successfully

    def _handle_exit(self, signum, frame):
        """Handle fast exit signal with minimal cleanup."""
        LOG.info('Received SIGINT, performing fast exit')

        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

        def force_exit():
            time.sleep(1)
            LOG.warning('Fast exit timeout, forcing immediate termination')
            os._exit(1)

        timer = threading.Timer(1.0, force_exit)
        timer.daemon = True
        timer.start()

        sys.exit(1)

    def _handle_reload(self, signum, frame):
        """Handle service reload signal."""
        LOG.info('Received SIGHUP, initiating service reload')

        # Trigger restart event
        if not self._restart_event.is_set():
            self._restart_event.set()

    def _handle_shutdown(self, signum, frame):
        """Async handle graceful shutdown signal."""
        LOG.info('Received SIGTERM, initiating graceful shutdown')

        # Use asyncio timeout instead of signal.alarm
        if self._shutdown_timeout and not self._shutdown_timeout_task:
            self._shutdown_timeout_task = asyncio.create_task(
                self._handle_timeout_exit()
            )

        # Trigger shutdown event
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

    async def _setup_signal_handlers(self):
        """Setup signal handlers using asyncio event loop."""
        if self._signal_handlers_setup:
            return

        try:
            signal.signal(signal.SIGTERM, self._handle_shutdown)
            signal.signal(signal.SIGINT, self._handle_exit)

            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, self._handle_reload)

            self._signal_handlers_setup = True
            LOG.debug('Signal handlers setup completed for ServiceLauncher')

        except Exception as e:
            LOG.error(f'Failed to setup signal handlers: {e}')
            raise

    async def _update_health_metrics(self):
        """Update health metrics thread-safely."""
        current_time = time.time()
        async with self._metrics_lock:
            if self._start_time:
                self._metrics['uptime_seconds'] = (
                    current_time - self._start_time
                )
            self._metrics['last_health_check'] = current_time

    async def _perform_health_check(self):
        """Enhanced health check implementation."""
        try:
            # Check if services are still running and responsive
            service_count = len(self.services.services)

            if service_count == 0:
                LOG.warning('No services are running')
                async with self._metrics_lock:
                    self._metrics['error_count'] += 1
                return
            LOG.debug(f'Health check passed: {service_count} services running')
        except Exception as e:
            LOG.warning(f'Health check failed: {e}')
            async with self._metrics_lock:
                self._metrics['error_count'] += 1

    async def _health_monitor(self):
        """Async health monitoring task with improved error handling."""
        LOG.debug('Starting health monitor')

        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(
                        self.conf.service_health_check_interval
                    )

                    # Update health metrics
                    await self._update_health_metrics()

                    # Perform health checks
                    await self._perform_health_check()

                except asyncio.CancelledError:
                    LOG.debug('Health monitor cancelled')
                    break
                except Exception as e:
                    LOG.error(f'Error in health monitor: {e}')
                    async with self._metrics_lock:
                        self._metrics['error_count'] += 1
                    # Use exponential backoff on error
                    await asyncio.sleep(
                        min(5.0, self.conf.service_health_check_interval)
                    )
        finally:
            LOG.debug('Health monitor stopped')

    async def _wait_for_exit_or_signal(self) -> tuple[int, int]:
        """Improved async wait with better task management."""
        status = None
        signo = None

        try:
            status, signo = await self._wait_for_events()
        except KeyboardInterrupt:
            LOG.info('Caught KeyboardInterrupt')
            await self.stop()
            status = ExitCodes.KILL
        except Exception as e:
            LOG.exception(f'Error waiting for exit or signal: {e}')
            await self._save_error()
            await self.stop()
            status = ExitCodes.ERROR

        return status, signo

    async def _wait_for_events(self) -> tuple[int, int]:
        """Wait for service events"""
        # Create tasks for different events
        tasks = {
            'service_wait': asyncio.create_task(super().wait()),
            'shutdown': asyncio.create_task(self._shutdown_event.wait()),
            'restart': asyncio.create_task(self._restart_event.wait()),
        }

        done, pending = await asyncio.wait(
            tasks.values(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        return await self._process_completed_events(tasks, done, pending)

    async def _process_completed_events(
        self, tasks: dict, done: set, pending: set
    ) -> tuple[int, int]:
        """Process completed events and return status."""
        # Cancel pending tasks
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # Determine which event occurred
        completed_task = next(iter(done))

        if completed_task == tasks['shutdown']:
            LOG.info('Graceful shutdown requested')
            # Cancel timeout task immediately when starting graceful shutdown
            if (
                self._shutdown_timeout_task
                and not self._shutdown_timeout_task.done()
            ):
                self._shutdown_timeout_task.cancel()
                try:
                    await self._shutdown_timeout_task
                except asyncio.CancelledError:
                    pass
            await self.stop()
            return ExitCodes.SUCCESS, None
        elif completed_task == tasks['restart']:
            LOG.info('Restart requested (SIGHUP)')
            return ExitCodes.RESTART, signal.SIGHUP
        elif completed_task == tasks['service_wait']:
            try:
                completed_task.result()
                return ExitCodes.SUCCESS, None
            except Exception as e:
                LOG.error(f'Service wait task failed: {e}')
                await self._save_error()
                return ExitCodes.ERROR, None

        return ExitCodes.ERROR, None

    async def wait(self) -> int:
        """Async wait for service termination with improved event handling."""
        systemd.notify_once()

        # Setup async signal handlers
        await self._setup_signal_handlers()

        # Start health monitoring
        if (
            self.conf.perform_service_health_check
            and self.conf.service_health_check_interval > 0
        ):
            self._health_monitor_task = asyncio.create_task(
                self._health_monitor()
            )

        while True:
            self._shutdown_event.clear()
            self._restart_event.clear()

            status, signo = await self._wait_for_exit_or_signal()

            if not _is_sighup_and_daemon(signo):
                break

            LOG.info('Restarting service due to SIGHUP signal')
            try:
                await self.restart()
            except Exception as e:
                LOG.error(f'Service restart failed: {e}')
                await self._save_error()
                status = ExitCodes.ERROR
                break

        # Cleanup tasks
        await self._cleanup_background_tasks()

        # Final service wait
        await super().wait()
        return status
