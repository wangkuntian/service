import asyncio
from collections.abc import Callable
from typing import Any

from service import loopingcall
from service.utils.log import LOG


class AsyncTask:
    """Wrapper class for asyncio tasks"""

    def __init__(self, task: asyncio.Task, name: str | None = None):
        self.task = task
        self.name = name or f'Task-{id(task)}'
        self._stopped = False

    def stop(self):
        """Stop the task"""
        if not self._stopped and not self.task.done():
            self.task.cancel()
            self._stopped = True

    async def wait(self):
        """Wait for the task to complete"""
        if not self.task.done():
            try:
                current_task = asyncio.current_task()
                if current_task == self.task:
                    LOG.warning(f'Task {self.name} trying to wait for itself')
                    return

                result = await self.task
                return result
            except asyncio.CancelledError:
                LOG.debug(f'Task {self.name} was cancelled')
                raise
            except Exception as e:
                LOG.exception(f'Task {self.name} failed: {e}')
                raise

    @property
    def done(self):
        """Check if the task is completed"""
        return self.task.done()


class TaskGroup:
    """Task group and timer management class using asyncio

    The purpose of this class is:

    * Track timers and tasks (making it easier to stop them when needed)
    * Provide an easy-to-use timer API

    """

    def __init__(self, max_concurrent_tasks: int):
        """Create a TaskGroup using asyncio task pool

        :param max_concurrent_tasks:
        Maximum number of tasks allowed to run concurrently
        """
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.tasks: set[AsyncTask] = set()
        self.timers: list[loopingcall.LoopingCallBase] = []
        self._stats = {
            'tasks_created': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'timers_created': 0,
        }

    def add_dynamic_timer(
        self,
        callback: Callable,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        initial_delay: float | None = None,
        periodic_interval_max: float | None = None,
        stop_on_exception: bool = True,
    ) -> loopingcall.DynamicLoopingCall:
        """Add a timer with dynamically controlled periods

        :param callback: Callback function to run when the timer triggers
        :param args: List of positional arguments for the callback function
        :param kwargs: Dictionary of keyword arguments
        for the callback function
        :param initial_delay: Delay in seconds before the first timer trigger
        :param periodic_interval_max: Maximum interval in seconds
        that the callback function can request
        :param stop_on_exception: Pass False to let the timer continue running
        when the callback function throws an exception
        :returns: DynamicLoopingCall instance
        """
        args = args or []
        kwargs = kwargs or {}
        timer = loopingcall.DynamicLoopingCall(callback, *args, **kwargs)
        timer.start(
            initial_delay=initial_delay,
            periodic_interval_max=periodic_interval_max,
            stop_on_exception=stop_on_exception,
        )
        self.timers.append(timer)
        self._stats['timers_created'] += 1
        return timer

    def add_timer(
        self,
        interval: float,
        callback: Callable,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        initial_delay: float | None = None,
        stop_on_exception: bool = True,
    ) -> loopingcall.FixedIntervalLoopingCall:
        """Add a fixed-period timer

        :param interval: Minimum period in seconds
        between callback function calls
        :param callback: Callback function to run when the timer triggers
        :param args: List of positional arguments for the callback function
        :param kwargs: Dictionary of keyword arguments
        for the callback function
        :param initial_delay: Delay in seconds before the first timer trigger
        :param stop_on_exception: Pass False to let the timer continue running
        when the callback function throws an exception
        :returns: FixedIntervalLoopingCall instance
        """
        args = args or []
        kwargs = kwargs or {}
        pulse = loopingcall.FixedIntervalLoopingCall(callback, *args, **kwargs)
        pulse.start(
            interval=interval,
            initial_delay=initial_delay,
            stop_on_exception=stop_on_exception,
        )
        self.timers.append(pulse)
        self._stats['timers_created'] += 1
        return pulse

    async def add_task(
        self,
        callback: Callable,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AsyncTask:
        """Start a new asynchronous task

        This call will block until there is available capacity
        in the task pool.
        After that, it returns immediately (before the new task is scheduled).

        :param callback: Function to run in the new task
        :param args: Positional arguments for the callback function
        :param timeout: Timeout in seconds for the task
        :param kwargs: Keyword arguments for the callback function
        :returns: AsyncTask object
        """
        task_wrapper = None

        async def _run_with_semaphore():
            async with self.semaphore:
                try:
                    self._stats['tasks_created'] += 1
                    if timeout:

                        def actual_callback():
                            return asyncio.wait_for(
                                callback(*args, **kwargs)
                                if asyncio.iscoroutinefunction(callback)
                                else callback(*args, **kwargs),
                                timeout=timeout,
                            )
                    else:
                        actual_callback = callback

                    if asyncio.iscoroutinefunction(
                        actual_callback if not timeout else callback
                    ):
                        if timeout:
                            result = await asyncio.wait_for(
                                callback(*args, **kwargs), timeout=timeout
                            )
                        else:
                            result = await callback(*args, **kwargs)
                    else:
                        # For synchronous functions, run in thread pool
                        loop = asyncio.get_event_loop()
                        if timeout:
                            result = await asyncio.wait_for(
                                loop.run_in_executor(
                                    None, lambda: callback(*args, **kwargs)
                                ),
                                timeout=timeout,
                            )
                        else:
                            result = await loop.run_in_executor(
                                None, lambda: callback(*args, **kwargs)
                            )

                    self._stats['tasks_completed'] += 1
                    return result

                except Exception as e:
                    self._stats['tasks_failed'] += 1
                    LOG.exception(f'Task failed: {e}')
                    raise
                finally:
                    # Remove task from set after completion
                    if task_wrapper and task_wrapper in self.tasks:
                        self.tasks.discard(task_wrapper)

        task = asyncio.create_task(_run_with_semaphore())
        task_wrapper = AsyncTask(task)

        self.tasks.add(task_wrapper)
        return task_wrapper

    def task_done(self, task: AsyncTask):
        """Remove completed task from the group

        This method is automatically called when a task in the group completes
        and should not be called explicitly.
        """
        self.tasks.discard(task)

    def timer_done(self, timer: loopingcall.LoopingCallBase):
        """Remove timer from the group

        :param timer: Timer object returned from add_timer or similar methods
        """
        if timer in self.timers:
            self.timers.remove(timer)

    async def _stop_tasks(self):
        """Stop all tasks"""
        # Copy the task set to avoid modification during iteration
        tasks_to_stop = self.tasks.copy()
        for task in tasks_to_stop:
            try:
                task.stop()
            except Exception:
                LOG.exception('Error stopping task.')

    async def stop_timers(self, wait: bool = False):
        """Stop all timers in the group and remove them from the group

        After stopping timers, no new calls will be triggered,
        but ongoing calls will not be interrupted.

        To wait for ongoing calls to complete, pass wait=True

        :param wait: If True,
        block until all timers have stopped before returning
        """
        timers_to_stop = self.timers.copy()
        for timer in timers_to_stop:
            await timer.stop()

        if wait:
            await self._wait_for_timers_stop(timers_to_stop)

        self.timers = []

    async def _wait_for_timers_stop(
        self, timers: list[loopingcall.LoopingCallBase]
    ):
        """Wait for timers to stop"""
        for timer in timers:
            try:
                await timer.wait()
            except Exception:
                LOG.exception('Error waiting for timer to stop.')
        self.timers = []

    async def stop(self, graceful: bool = False):
        """Stop all timers and tasks in the group

        :param graceful:
        If True, wait for all timers to stop and all tasks to complete;
        otherwise, immediately cancel tasks and return
        """
        await self.stop_timers(wait=graceful)
        if graceful:
            await self._wait_tasks()
        else:
            await self._stop_tasks()

    async def _wait_timers(self):
        """Wait for all timers to complete"""
        for timer in self.timers[:]:
            # Use copy to avoid modifying list during iteration
            try:
                await timer.wait()
            except Exception:
                LOG.exception('Error waiting on timer.')

    async def _wait_tasks(self):
        """Wait for all tasks to complete"""
        # Copy the task set to avoid modification during iteration
        tasks_to_wait = list(self.tasks)
        for task in tasks_to_wait:
            try:
                await task.wait()
            except Exception:
                LOG.exception('Error waiting on task.')

    async def wait(self):
        """Block until all timers and tasks in the group complete
        Before calling this method,
        you should first stop any timers by calling stop_timers, stop.
        Otherwise this will block forever.
        Any exceptions thrown by tasks will be logged but suppressed.
        """
        await self._wait_timers()
        await self._wait_tasks()

    def _any_tasks_alive(self):
        """Check if any tasks are still running"""
        return any(not task.done for task in self.tasks)

    async def cancel(self, timeout: float | None = None, wait_time: float = 1):
        """Cancel tasks in the group, optionally stopping remaining tasks

        :param timeout: Time to wait for running tasks to complete,
        after which tasks are cancelled
        :param wait_time:
        Interval time (seconds) to check if tasks are still alive
        """
        if timeout is None:
            # Immediately cancel all tasks
            await self._stop_tasks()
            return

        # Wait for timeout duration to let tasks complete
        elapsed = 0
        while self._any_tasks_alive() and elapsed < timeout:
            await asyncio.sleep(wait_time)
            elapsed += wait_time

        if self._any_tasks_alive():
            LOG.debug('Cancel timeout reached, stopping tasks.')
            await self.stop()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop(graceful=True)

    async def gather_results(self, timeout: float | None = None) -> list:
        """Gather results from all tasks"""
        tasks = list(self.tasks)
        results = []

        for task_wrapper in tasks:
            try:
                if timeout:
                    result = await asyncio.wait_for(task_wrapper.task, timeout)
                else:
                    result = await task_wrapper.task
                results.append(result)
            except Exception as e:
                results.append(e)

        return results

    @property
    def stats(self) -> dict:
        """Get statistics"""
        return {
            **self._stats,
            'active_tasks': len(self.tasks),
            'active_timers': len(self.timers),
            'semaphore_available': self.semaphore._value,
        }
