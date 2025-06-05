from typing import Any

from service.utils.singleton import Base, Singleton


class ConfigOpts(Base, metaclass=Singleton):
    def __init__(self):
        self.service_wait_timeout = 300
        self.service_wait_timeout_max = 300
        self.graceful_shutdown_timeout = 30
        self.health_check_interval = 10
        self.max_restart_rate_per_minute = 5
        self.max_memory_mb = 1024
        self.memory_check_interval = 60
        self.child_monitor_interval = 0.01
        self.child_start_max_retries = 3
        self.child_start_retry_delay = 1.0
        self.log_options = False

    def register_opts(self, opts: dict[str, Any]):
        for key, value in opts.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def __str__(self) -> str:
        s = ''
        for key, value in self.__dict__.items():
            s += f'{key}: {value}\n'
        return f'<ConfigOpts {s}>'
