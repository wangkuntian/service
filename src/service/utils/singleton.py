from service.utils import lock as lockutils


class Singleton(type):
    _instances = {}
    _semaphores = lockutils.Semaphores()

    def __call__(cls, *args, **kwargs):
        with lockutils.lock('singleton_lock', semaphores=cls._semaphores):
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class Base:
    def __init__(self, *args, **kwargs):
        for key, value in kwargs.items():
            if key in self.__dict__:
                self.__dict__[key] = value
