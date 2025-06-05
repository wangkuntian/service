from typing import Any

from service.utils.singleton import Base, Singleton


class ConfigOpts(Base, metaclass=Singleton):
    def __init__(self):
        self.service_wait_timeout = 300
        self.service_wait_timeout_max = 300
        self.graceful_shutdown_timeout = 30
        self.log_options = False
        self.initial_delay = 3
        # loop call max interval, default 10 seconds
        self.periodic_interval_max = 5

        self.service_health_check_interval = 10
        self.perform_service_health_check = True

    def register_opts(self, opts: dict[str, Any]):
        for key, value in opts.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def __str__(self) -> str:
        s = ''
        for key, value in self.__dict__.items():
            s += f'{key}: {value}\n'
        return f'<ConfigOpts {s}>'
