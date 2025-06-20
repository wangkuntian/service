import contextlib
import os
import socket

from service.utils.log import LOG


def _abstractify(socket_name: str) -> str:
    if socket_name.startswith('@'):
        # abstract namespace socket
        socket_name = f'\0{socket_name[1:]}'
    return socket_name


def _sd_notify(unset_env: bool, msg: bytes) -> None:
    notify_socket = os.getenv('NOTIFY_SOCKET')
    if notify_socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        with contextlib.closing(sock):
            try:
                sock.connect(_abstractify(notify_socket))
                sock.sendall(msg)
                if unset_env:
                    del os.environ['NOTIFY_SOCKET']
            except OSError:
                LOG.debug('Systemd notification failed', exc_info=True)


def notify():
    """Send notification to Systemd that service is ready.

    For details see
    http://www.freedesktop.org/software/systemd/man/sd_notify.html
    """
    _sd_notify(False, b'READY=1')


def notify_once():
    """Send notification once to Systemd that service is ready.

    Systemd sets NOTIFY_SOCKET environment variable with the name of the
    socket listening for notifications from services.
    This method removes the NOTIFY_SOCKET environment variable to ensure
    notification is sent only once.
    """
    _sd_notify(True, b'READY=1')


def onready(notify_socket: str, timeout: float) -> int:
    """Wait for systemd style notification on the socket.

    :param notify_socket: local socket address
    :type notify_socket:  string
    :param timeout:       socket timeout
    :type timeout:        float
    :returns:             0 service ready
                          1 service not ready
                          2 timeout occurred
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.bind(_abstractify(notify_socket))
    with contextlib.closing(sock):
        try:
            msg = sock.recv(512)
        except TimeoutError:
            return 2
        if b'READY=1' == msg:
            return 0
        else:
            return 1
