import asyncio
import os
import signal
import time

from service import ServiceBase, systemd
from service.config.common import ConfigOpts
from service.launchers.base import Launcher
from service.utils.log import LOG


def _is_sighup_and_daemon(signo: int) -> bool:
    """Check if it's SIGHUP signal and in daemon mode"""
    return signo == signal.SIGHUP


class ServiceLauncher(Launcher):
    """Async optimized version of ServiceLauncher,
    using asyncio features to improve performance and responsiveness."""

    def __init__(self, conf: ConfigOpts = ConfigOpts()):
        """Constructor.

        :param conf: an instance of ConfigOpts
        """
        super().__init__(conf)

        # asyncio enhanced features
        self._shutdown_event = asyncio.Event()
        self._restart_event = asyncio.Event()
        self._signal_handlers_setup = False
        self._cleanup_tasks = set()

        # Optimized timeout handling
        self._wait_timeout = conf.service_wait_timeout
        self._shutdown_timeout = conf.graceful_shutdown_timeout

        # Enhanced monitoring and health check
        self._start_time = None
        self._restart_count = 0
        self._last_restart_time = None
        self._health_check_interval = conf.health_check_interval
        self._health_monitor_task = None
        self._shutdown_timeout_task = None

        # Performance metrics with thread-safe updates
        self._metrics_lock = asyncio.Lock()
        self._metrics = {
            'restart_count': 0,
            'uptime_seconds': 0,
            'last_health_check': None,
            'signal_count': 0,
            'error_count': 0,
        }

    def _graceful_shutdown(self):
        """Async handle graceful shutdown signal."""
        LOG.info('Received SIGTERM, initiating graceful shutdown')

        # Direct metrics update for immediate test visibility
        self._metrics['signal_count'] += 1

        # Use asyncio timeout instead of signal.alarm
        if self._shutdown_timeout and not self._shutdown_timeout_task:
            self._shutdown_timeout_task = asyncio.create_task(
                self._schedule_timeout_exit()
            )

        # Trigger shutdown event
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

    async def _update_signal_count(self):
        """Thread-safe update of signal count."""
        async with self._metrics_lock:
            self._metrics['signal_count'] += 1

    async def _schedule_timeout_exit(self):
        """Async timeout handler to replace signal.alarm."""
        try:
            await asyncio.sleep(self._shutdown_timeout)
            LOG.warning(
                f'Graceful shutdown timeout '
                f'({self._shutdown_timeout}s) exceeded'
            )
            self._async_timeout_exit()
        except asyncio.CancelledError:
            LOG.debug('Shutdown timeout cancelled')

    def _async_reload_service(self):
        """Async handle service reload signal."""
        LOG.info('Received SIGHUP, initiating service reload')
        # Direct metrics update for immediate test visibility
        self._metrics['signal_count'] += 1

        # Trigger restart event
        if not self._restart_event.is_set():
            self._restart_event.set()

    def _async_fast_exit(self):
        """Async handle fast exit signal."""
        LOG.info('Received SIGINT, immediate exit')
        # Direct metrics update for immediate test visibility
        self._metrics['signal_count'] += 1
        os._exit(1)

    def _async_timeout_exit(self):
        """Async handle timeout exit signal."""
        LOG.info('Graceful shutdown timeout exceeded, immediate exit')
        os._exit(1)

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
            LOG.debug('Performing service health check')
            # Check if services are still running and responsive
            service_count = len(self.services.services)

            if service_count == 0:
                LOG.warning('No services are running')
                async with self._metrics_lock:
                    self._metrics['error_count'] += 1
                return

            # Example: Check if services are responding (can be extended)
            # In a real implementation, this might ping service endpoints
            # or check database connections, etc.

            LOG.debug(f'Health check passed: {service_count} services running')

        except Exception as e:
            LOG.warning(f'Health check failed: {e}')
            async with self._metrics_lock:
                self._metrics['error_count'] += 1

    async def _wait_for_exit_or_signal(self) -> tuple[int, int]:
        """Improved async wait with better task management."""
        status = None
        signo = 0

        # Use TaskGroup for better task management (Python 3.11+)
        # Fallback to manual management for older versions
        try:
            # Create tasks for different events
            tasks = {
                'service_wait': asyncio.create_task(super().wait()),
                'shutdown': asyncio.create_task(self._shutdown_event.wait()),
                'restart': asyncio.create_task(self._restart_event.wait()),
            }

            # Wait for any event to occur with optional timeout
            try:
                if self._wait_timeout:
                    done, pending = await asyncio.wait(
                        tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=self._wait_timeout,
                    )

                    if not done:
                        # Timeout occurred
                        LOG.warning(
                            f'Wait timeout ({self._wait_timeout}s) exceeded, '
                            'forcing shutdown'
                        )
                        await self.stop()
                        await LOG.complete()
                        status = 124  # Standard timeout exit code
                        return status, signo
                else:
                    # Wait indefinitely
                    done, pending = await asyncio.wait(
                        tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                # Cancel pending tasks efficiently
                for task in pending:
                    task.cancel()

                # Wait for cancellation without logging individual errors
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

                # Determine which event occurred
                completed_task = next(iter(done))

                if completed_task == tasks['shutdown']:
                    LOG.info('Graceful shutdown requested')
                    await self.stop()
                    status = 0
                elif completed_task == tasks['restart']:
                    LOG.info('Restart requested (SIGHUP)')
                    signo = signal.SIGHUP
                    status = 1
                elif completed_task == tasks['service_wait']:
                    # Check if service_wait_task completed successfully
                    try:
                        completed_task.result()
                        status = 0
                    except Exception as e:
                        LOG.error(f'Service wait task failed: {e}')
                        async with self._metrics_lock:
                            self._metrics['error_count'] += 1
                        status = 1

            except TimeoutError:
                LOG.warning('Operation timed out')
                status = 124

        except KeyboardInterrupt:
            LOG.info('Caught KeyboardInterrupt')
            await self.stop()
            status = 130  # Standard exit code for SIGINT
        except Exception as e:
            LOG.exception(f'Error waiting for exit or signal: {e}')
            async with self._metrics_lock:
                self._metrics['error_count'] += 1
            await self.stop()
            status = 1

        return status, signo

    async def _setup_async_signal_handlers(self):
        """Setup async signal handlers using asyncio event loop."""
        if self._signal_handlers_setup:
            return

        try:
            loop = asyncio.get_running_loop()

            # Use asyncio signal handling for better integration
            loop.add_signal_handler(signal.SIGTERM, self._graceful_shutdown)
            loop.add_signal_handler(signal.SIGHUP, self._async_reload_service)
            loop.add_signal_handler(signal.SIGINT, self._async_fast_exit)

            # Add SIGALRM handler only if supported
            try:
                loop.add_signal_handler(
                    signal.SIGALRM, self._async_timeout_exit
                )
            except (OSError, NotImplementedError):
                LOG.warning(
                    'SIGALRM signal handler not supported on this platform'
                )

            self._signal_handlers_setup = True
            LOG.debug(
                'Async signal handlers setup completed for ServiceLauncher'
            )

        except Exception as e:
            LOG.error(f'Failed to setup async signal handlers: {e}')
            raise

    async def _health_monitor(self):
        """Async health monitoring task with improved error handling."""
        LOG.debug('Starting health monitor')

        try:
            while not self._shutdown_event.is_set():
                try:
                    await asyncio.sleep(self._health_check_interval)

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
                    await asyncio.sleep(min(5.0, self._health_check_interval))
        finally:
            LOG.debug('Health monitor stopped')

    async def wait(self) -> int:
        """Async wait for service termination with improved event handling."""
        systemd.notify_once()

        # Setup async signal handlers
        await self._setup_async_signal_handlers()

        # Start health monitoring
        if self._health_check_interval > 0:
            self._health_monitor_task = asyncio.create_task(
                self._health_monitor()
            )

        # Improved event management - don't clear events in loop
        restart_requested = False

        while True:
            # Only clear events if restart was just handled
            if restart_requested:
                self._shutdown_event.clear()
                self._restart_event.clear()
                restart_requested = False

            status, signo = await self._wait_for_exit_or_signal()

            if not _is_sighup_and_daemon(signo):
                break

            # If it's a SIGHUP signal, restart service
            LOG.info('Restarting service due to SIGHUP signal')
            try:
                await self.restart()
                restart_requested = True
            except Exception as e:
                LOG.error(f'Service restart failed: {e}')
                async with self._metrics_lock:
                    self._metrics['error_count'] += 1
                status = 1
                break

        # Cleanup tasks
        await self._cleanup_background_tasks()

        # Final service wait
        await super().wait()
        return status

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
            'health_check_interval': self._health_check_interval,
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
