from time import monotonic as now

from service.utils import reflection


class Split:
    """A *immutable* stopwatch split.

    See: http://en.wikipedia.org/wiki/Stopwatch for what this is/represents.

    """

    __slots__ = ['_elapsed', '_length']

    def __init__(self, elapsed: float, length: float):
        self._elapsed = elapsed
        self._length = length

    @property
    def elapsed(self) -> float:
        """Duration from stopwatch start."""
        return self._elapsed

    @property
    def length(self) -> float:
        """Seconds from last split (or the elapsed time if no prior split)."""
        return self._length

    def __repr__(self) -> str:
        r = reflection.get_class_name(self, fully_qualified=False)
        r += f'(elapsed={self._elapsed}, length={self._length})'
        return r


class StopWatch:
    """A simple timer/stopwatch helper class.

    Inspired by: apache-commons-lang java stopwatch.

    Not thread-safe (when a single watch is mutated by multiple threads at
    the same time). Thread-safe when used by a single thread (not shared) or
    when operations are performed in a thread-safe manner on these objects by
    wrapping those operations with locks.

    .. versionadded:: 1.4
    """

    _STARTED = 'STARTED'
    _STOPPED = 'STOPPED'

    def __init__(self, duration: float | None = None):
        if duration is not None and duration < 0:
            raise ValueError(
                f'Duration must be greater or equal to zero and not {duration}'
            )
        self._duration = duration
        self._started_at = None
        self._stopped_at = None
        self._state = None
        self._splits = ()

    def start(self) -> 'StopWatch':
        """Starts the watch (if not already started).

        Resets any splits previously captured (if any).
        """
        if self._state == self._STARTED:
            return self
        self._started_at = now()
        self._stopped_at = None
        self._state = self._STARTED
        self._splits = ()
        return self

    @property
    def splits(self) -> tuple[Split, ...]:
        """Accessor to all/any splits that have been captured."""
        return self._splits

    def split(self) -> Split:
        """Captures a split/elapsed since start time (and doesn't stop)."""
        if self._state == self._STARTED:
            elapsed = self.elapsed()
            if self._splits:
                length = self._delta_seconds(self._splits[-1].elapsed, elapsed)
            else:
                length = elapsed
            self._splits = self._splits + (Split(elapsed, length),)
            return self._splits[-1]
        else:
            raise RuntimeError(
                'Can not create a split time of a stopwatch'
                ' if it has not been started or if it has been'
                ' stopped'
            )

    def restart(self) -> 'StopWatch':
        """Restarts the watch from a started/stopped state."""
        if self._state == self._STARTED:
            self.stop()
        self.start()
        return self

    @staticmethod
    def _delta_seconds(earlier: float, later: float) -> float:
        # Uses max to avoid the delta/time going backwards (and thus negative).
        return max(0.0, later - earlier)

    def elapsed(self, maximum: float | None = None) -> float:
        """Returns how many seconds have elapsed."""
        if self._state not in (self._STARTED, self._STOPPED):
            raise RuntimeError(
                'Can not get the elapsed time of a stopwatch'
                ' if it has not been started/stopped'
            )
        if self._state == self._STOPPED:
            elapsed = self._delta_seconds(self._started_at, self._stopped_at)
        else:
            elapsed = self._delta_seconds(self._started_at, now())
        if maximum is not None and elapsed > maximum:
            elapsed = max(0.0, maximum)
        return elapsed

    def __enter__(self) -> 'StopWatch':
        """Starts the watch."""
        self.start()
        return self

    def __exit__(self, type, value, traceback) -> None:
        """Stops the watch (ignoring errors if stop fails)."""
        try:
            self.stop()
        except RuntimeError:  # nosec: errors are meant to be ignored
            pass

    def leftover(self, return_none: bool = False) -> float | None:
        """Returns how many seconds are left until the watch expires.

        :param return_none: when ``True`` instead of raising a ``RuntimeError``
                            when no duration has been set this call will
                            return ``None`` instead.
        :type return_none: boolean
        """
        if self._state != self._STARTED:
            raise RuntimeError(
                'Can not get the leftover time of a stopwatch'
                ' that has not been started'
            )
        if self._duration is None:
            if not return_none:
                raise RuntimeError(
                    'Can not get the leftover time of a watch'
                    ' that has no duration'
                )
            return None
        return max(0.0, self._duration - self.elapsed())

    def expired(self) -> bool:
        """Returns if the watch has expired (ie, duration provided elapsed)."""
        if self._state not in (self._STARTED, self._STOPPED):
            raise RuntimeError(
                'Can not check if a stopwatch has expired'
                ' if it has not been started/stopped'
            )
        if self._duration is None:
            return False
        return self.elapsed() > self._duration

    def has_started(self) -> bool:
        """Returns True if the watch is in a started state."""
        return self._state == self._STARTED

    def has_stopped(self) -> bool:
        """Returns True if the watch is in a stopped state."""
        return self._state == self._STOPPED

    def resume(self) -> 'StopWatch':
        """Resumes the watch from a stopped state."""
        if self._state == self._STOPPED:
            self._state = self._STARTED
            return self
        else:
            raise RuntimeError(
                'Can not resume a stopwatch that has not been stopped'
            )

    def stop(self) -> 'StopWatch':
        """Stops the watch."""
        if self._state == self._STOPPED:
            return self
        if self._state != self._STARTED:
            raise RuntimeError(
                'Can not stop a stopwatch that has not been started'
            )
        self._stopped_at = now()
        self._state = self._STOPPED
        return self
