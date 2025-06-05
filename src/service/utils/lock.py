import contextlib
import os
import threading
import weakref
from collections.abc import Generator

import fasteners

from service.utils.log import LOG


class AcquireLockFailedException(Exception):
    def __init__(self, lock_name):
        self.message = f'Failed to acquire the lock {lock_name}'

    def __str__(self):
        return self.message


class Semaphores:
    """A garbage collected container of semaphores.

    This collection internally uses a weak value dictionary so that when a
    semaphore is no longer in use (by any threads) it will automatically be
    removed from this container by the garbage collector.

    .. versionadded:: 0.3
    """

    def __init__(self):
        self._semaphores = weakref.WeakValueDictionary()
        self._lock = threading.Lock()

    def get(self, name: str) -> threading.Semaphore:
        """Gets (or creates) a semaphore with a given name.

        :param name: The semaphore name to get/create (used to associate
                     previously created names with the same semaphore).

        Returns an newly constructed semaphore (or an existing one if it was
        already created for the given name).
        """
        with self._lock:
            try:
                return self._semaphores[name]
            except KeyError:
                sem = threading.Semaphore()
                self._semaphores[name] = sem
                return sem

    def __len__(self) -> int:
        """Returns how many semaphores exist at the current time."""
        return len(self._semaphores)


_semaphores = Semaphores()


class FairLocks:
    """A garbage collected container of fair locks.

    With a fair lock, contending lockers will get the lock in the order in
    which they tried to acquire it.

    This collection internally uses a weak value dictionary so that when a
    lock is no longer in use (by any threads) it will automatically be
    removed from this container by the garbage collector.
    """

    def __init__(self):
        self._locks = weakref.WeakValueDictionary()
        self._lock = threading.Lock()

    def get(self, name: str) -> fasteners.ReaderWriterLock:
        """Gets (or creates) a lock with a given name.

        :param name: The lock name to get/create (used to associate
                     previously created names with the same lock).

        Returns an newly constructed lock (or an existing one if it was
        already created for the given name).
        """
        with self._lock:
            try:
                return self._locks[name]
            except KeyError:
                rwlock = fasteners.ReaderWriterLock()
                self._locks[name] = rwlock
                return rwlock


_fair_locks = FairLocks()


def internal_fair_lock(name: str) -> fasteners.ReaderWriterLock:
    return _fair_locks.get(name)


def internal_lock(name, semaphores=None, blocking=True):
    @contextlib.contextmanager
    def nonblocking(lock):
        """Try to acquire the internal lock without blocking."""
        if not lock.acquire(blocking=False):
            raise AcquireLockFailedException(name)
        try:
            yield lock
        finally:
            lock.release()

    if semaphores is None:
        semaphores = _semaphores
    lock = semaphores.get(name)

    return nonblocking(lock) if not blocking else lock


def _get_lock_path(
    name: str,
    lock_file_prefix: str | None = None,
    lock_path: str | None = None,
) -> str:
    # NOTE(mikal): the lock name cannot contain directory
    # separators
    name = name.replace(os.sep, '_')
    if lock_file_prefix:
        sep = '' if lock_file_prefix.endswith('-') else '-'
        name = f'{lock_file_prefix}{sep}{name}'

    if not lock_path:
        raise ValueError('lock_path is required')

    return os.path.join(lock_path, name)


def external_lock(
    name: str,
    lock_file_prefix: str | None = None,
    lock_path: str | None = None,
) -> fasteners.InterProcessLock:
    lock_file_path = _get_lock_path(name, lock_file_prefix, lock_path)

    return fasteners.InterProcessLock(lock_file_path)


@contextlib.contextmanager
def lock(
    name: str,
    lock_file_prefix: str | None = None,
    external: bool = False,
    lock_path: str | None = None,
    do_log: bool = True,
    semaphores: Semaphores | None = None,
    delay: float = 0.01,
    fair: bool = False,
    blocking: bool = True,
) -> Generator[threading.Semaphore | fasteners.ReaderWriterLock]:
    """Context based lock

    This function yields a `threading.Semaphore` instance (if we don't use
    eventlet.monkey_patch(), else `semaphore.Semaphore`) unless external is
    True, in which case, it'll yield an InterProcessLock instance.

    :param lock_file_prefix: The lock_file_prefix argument is used to provide
      lock files on disk with a meaningful prefix.

    :param external: The external keyword argument denotes whether this lock
      should work across multiple processes. This means that if two different
      workers both run a method decorated with @synchronized('mylock',
      external=True), only one of them will execute at a time.

    :param lock_path: The path in which to store external lock files.  For
      external locking to work properly, this must be the same for all
      references to the lock.

    :param do_log: Whether to log acquire/release messages.  This is primarily
      intended to reduce log message duplication when `lock` is used from the
      `synchronized` decorator.

    :param semaphores: Container that provides semaphores to use when locking.
        This ensures that threads inside the same application can not collide,
        due to the fact that external process locks are unaware of a processes
        active threads.

    :param delay: Delay between acquisition attempts (in seconds).

    :param fair: Whether or not we want a "fair" lock where contending lockers
        will get the lock in the order in which they tried to acquire it.

    :param blocking: Whether to wait forever to try to acquire the lock.
        Incompatible with fair locks because those provided by the fasteners
        module doesn't implements a non-blocking behavior.

    .. versionchanged:: 0.2
       Added *do_log* optional parameter.

    .. versionchanged:: 0.3
       Added *delay* and *semaphores* optional parameters.
    """
    if fair:
        if semaphores is not None:
            raise NotImplementedError(
                'Specifying semaphores is not supported when using fair locks.'
            )
        if blocking is not True:
            raise NotImplementedError(
                'Disabling blocking is not supported when using fair locks.'
            )
        # The fasteners module specifies that write_lock() provides fairness.
        int_lock = internal_fair_lock(name).write_lock()
    else:
        int_lock = internal_lock(
            name, semaphores=semaphores, blocking=blocking
        )
    if do_log:
        LOG.debug(f'Acquiring lock "{name}"')
    with int_lock:
        if do_log:
            LOG.debug(f'Acquired lock "{name}"')
        try:
            if external:
                ext_lock = external_lock(name, lock_file_prefix, lock_path)
                gotten = ext_lock.acquire(delay=delay, blocking=blocking)
                if not gotten:
                    raise AcquireLockFailedException(name)
                if do_log:
                    LOG.debug(
                        f'Acquired external semaphore "{name}"',
                    )
                try:
                    yield ext_lock
                finally:
                    ext_lock.release()
            else:
                yield int_lock
        finally:
            if do_log:
                LOG.debug(f'Releasing lock "{name}"')
