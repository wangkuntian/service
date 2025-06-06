import asyncio
import contextlib
import sys
from collections.abc import Callable
from typing import Any

from service.utils import reflection
from service.utils import time as timeutils
from service.utils.log import LOG


class LoopingCallDone(Exception):
    """Exception to break out and stop a LoopingCallBase.

    The poll-function passed to LoopingCallBase can raise this exception to
    break out of the loop normally. This is somewhat analogous to
    StopIteration.

    An optional return-value can be included as the argument to the exception;
    this return-value will be returned by LoopingCallBase.wait()

    """

    def __init__(self, retvalue: Any = True):
        """
        :param retvalue: Value that LoopingCallBase.wait() should return.
        """
        self.retvalue = retvalue


async def _safe_wrapper(
    f: Callable, kind: str, func_name: str, *args: Any, **kwargs: Any
) -> Any:
    """wrapper that calls into wrapped function and logs errors as needed."""
    try:
        if asyncio.iscoroutinefunction(f):
            return await f(*args, **kwargs)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: f(*args, **kwargs))
    except LoopingCallDone:
        raise  # let the outer handler process this
    except Exception:
        LOG.error(f'{kind} {func_name} failed', exc_info=True)
        return 0


class LoopingCallBase:
    _KIND = 'Unknown looping call'

    _RUN_ONLY_ONE_MESSAGE = (
        'A looping call can only run one function at a time'
    )

    def __init__(self, f: Callable | None = None, *args: Any, **kw: Any):
        self.args = args
        self.kw = kw
        self.f = f
        self._task = None
        self._done = None
        self._abort = asyncio.Event()
        self._cleanup_tasks = set()
        self._lock = asyncio.Lock()

    @property
    def _running(self) -> bool:
        return not self._abort.is_set()

    async def stop(self, timeout: float = 5.0):
        """stop the looping call"""
        async with self._lock:
            if self._running:
                self._abort.set()

            if self._task and not self._task.done():
                try:
                    await asyncio.shield(
                        asyncio.wait_for(
                            self._graceful_stop(), timeout=timeout
                        )
                    )
                except asyncio.TimeoutError:
                    LOG.warning(
                        f'Graceful stop timed out after {timeout}s, '
                        'forcing cancellation'
                    )
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass

            await self._cleanup_all_tasks()

    async def _graceful_stop(self):
        """graceful stop implementation"""
        if self._done and not self._done.is_set():
            await self._done.wait()

    async def _cleanup_all_tasks(self):
        """cleanup all related tasks"""
        if self._cleanup_tasks:
            for task in list(self._cleanup_tasks):
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
            self._cleanup_tasks.clear()

    async def wait(self) -> bool:
        if self._done:
            return await self._done.wait()
        return True

    def _on_done(self, task: asyncio.Task):
        self._task = None
        if self._done and not self._done.is_set():
            try:
                result = task.result()
                if hasattr(self._done, 'result'):
                    self._done.result = result
                self._done.set()
            except asyncio.CancelledError:
                # Task was cancelled, this is normal stop behavior
                self._done.set()
            except Exception as e:
                LOG.exception(f'Task failed: {e}')
                self._done.set()

    async def _sleep(self, duration: float):
        """optimized sleep method, supports cancellation"""
        if duration > 0:
            try:
                sleep_task = asyncio.create_task(asyncio.sleep(duration))
                abort_task = asyncio.create_task(self._abort.wait())

                self._cleanup_tasks.add(sleep_task)
                self._cleanup_tasks.add(abort_task)

                try:
                    done, pending = await asyncio.wait(
                        {sleep_task, abort_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for task in pending:
                        task.cancel()

                finally:
                    self._cleanup_tasks.discard(sleep_task)
                    self._cleanup_tasks.discard(abort_task)

            except asyncio.CancelledError:
                # canceling sleep is normal
                pass

    def _start(
        self,
        idle_for: Callable,
        initial_delay: float | None = None,
        stop_on_exception: bool = True,
    ):
        """Start the looping

        :param idle_for: Callable that takes two positional arguments, returns
                         how long to idle for. The first positional argument is
                         the last result from the function being looped and the
                         second positional argument is the time it took to
                         calculate that result.
        :param initial_delay: How long to delay before starting the looping.
                              Value is in seconds.
        :param stop_on_exception: Whether to stop if an exception occurs.
        :returns: asyncio event instance
        """
        if self._task is not None:
            raise RuntimeError(self._RUN_ONLY_ONE_MESSAGE)
        self._done = asyncio.Event()
        self._abort.clear()
        self._task = asyncio.create_task(
            self._run_loop(
                idle_for,
                initial_delay=initial_delay,
                stop_on_exception=stop_on_exception,
            ),
            name=f'{self._KIND}-{reflection.get_callable_name(self.f)}',
        )
        self._task.add_done_callback(self._on_done)
        return self._done

    def _elapsed(self, watch: timeutils.StopWatch) -> float:
        return watch.elapsed()

    async def _execute_function(
        self, stop_on_exception: bool, kind: str, func_name: str
    ):
        """Execute the function with proper error handling."""
        try:
            if stop_on_exception:
                if asyncio.iscoroutinefunction(self.f):
                    return await self.f(*self.args, **self.kw)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None, lambda: self.f(*self.args, **self.kw)
                    )
            else:
                return await _safe_wrapper(
                    self.f, kind, func_name, *self.args, **self.kw
                )
        except LoopingCallDone:
            raise
        except Exception:
            if stop_on_exception:
                exc_info = sys.exc_info()
                try:
                    LOG.error(f'{kind} {func_name} failed', exc_info=exc_info)
                    raise
                finally:
                    del exc_info
            else:
                LOG.error(f'{kind} {func_name} failed', exc_info=True)
                return 0

    async def _run_loop(
        self,
        idle_for_func: Callable,
        initial_delay: float | None = None,
        stop_on_exception: bool = True,
    ):
        kind = self._KIND
        func_name = reflection.get_callable_name(self.f)

        if initial_delay:
            await self._sleep(initial_delay)

        try:
            watch = timeutils.StopWatch()
            while self._running:
                watch.restart()

                try:
                    result = await self._execute_function(
                        stop_on_exception, kind, func_name
                    )
                except LoopingCallDone as e:
                    return e.retvalue

                watch.stop()

                if not self._running:
                    break

                idle = idle_for_func(result, self._elapsed(watch))
                LOG.debug(
                    f'{kind} {func_name} sleeping for {idle:.03f} seconds',
                )
                await self._sleep(idle)

        except asyncio.CancelledError:
            LOG.debug(f'{kind} {func_name} was cancelled')
            raise
        except Exception:
            exc_info = sys.exc_info()
            try:
                LOG.error(f'{kind} {func_name} failed', exc_info=exc_info)
                raise
            finally:
                del exc_info
        else:
            return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def __enter__(self):
        raise RuntimeError(
            "Use 'async with' for LoopingCallBase context management"
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class DynamicLoopingCall(LoopingCallBase):
    """A looping call which sleeps until the next call.

    The function called may specify how long to sleep for by returning a
    float/int. If None is returned, the same sleep interval will be used
    as the one given when the looping call was started. If False is returned,
    the looping call will be stopped.
    """

    _KIND = 'Dynamic looping call'

    def start(
        self,
        initial_delay: float | None = None,
        periodic_interval_max: float | None = None,
        stop_on_exception: bool = True,
    ):
        def _idle_for(suggested_delay: float | None, elapsed: float) -> float:
            delay = suggested_delay
            if delay is None:
                delay = periodic_interval_max
            elif delay is False:
                asyncio.create_task(self.stop())
                return 0
            if periodic_interval_max:
                delay = min(delay, periodic_interval_max)
            return max(0, delay) if delay is not None else 0

        return self._start(_idle_for, initial_delay, stop_on_exception)


class FixedIntervalLoopingCall(LoopingCallBase):
    """A fixed interval looping call."""

    _RUN_ONLY_ONE_MESSAGE = (
        'A fixed interval looping call can only run one function at a time'
    )

    _KIND = 'Fixed interval looping call'

    def start(
        self,
        interval: float,
        initial_delay: float | None = None,
        stop_on_exception: bool = True,
    ):
        def _idle_for(result: Any, elapsed: float) -> float:
            delay = interval - elapsed
            if delay < 0:
                func_name = reflection.get_callable_name(self.f)
                LOG.warning(
                    f'Function {func_name} run outlasted '
                    f'interval by {abs(delay):.2f} sec',
                )
                return 0  # 立即开始下一次调用
            return delay

        return self._start(
            _idle_for,
            initial_delay=initial_delay,
            stop_on_exception=stop_on_exception,
        )


@contextlib.asynccontextmanager
async def dynamic_loop(
    func: Callable,
    *args,
    initial_delay: float | None = None,
    periodic_interval_max: float | None = None,
    stop_on_exception: bool = True,
    **kwargs,
) -> Any:
    """context manager version of dynamic looping call"""
    loop_call = DynamicLoopingCall(func, *args, **kwargs)
    try:
        loop_call.start(
            initial_delay=initial_delay,
            periodic_interval_max=periodic_interval_max,
            stop_on_exception=stop_on_exception,
        )
        yield loop_call
    finally:
        await loop_call.stop()


@contextlib.asynccontextmanager
async def fixed_interval_loop(
    func: Callable,
    interval: float,
    *args,
    initial_delay: float | None = None,
    stop_on_exception: bool = True,
    **kwargs,
) -> Any:
    """context manager version of fixed interval looping call"""
    loop_call = FixedIntervalLoopingCall(func, *args, **kwargs)
    try:
        loop_call.start(
            interval=interval,
            initial_delay=initial_delay,
            stop_on_exception=stop_on_exception,
        )
        yield loop_call
    finally:
        await loop_call.stop()
