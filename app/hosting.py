"""Owned in-process room service. No system service or virtual adapter is installed."""
import asyncio
import secrets
import threading
from http import HTTPStatus
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit

from PySide6.QtCore import QThread, Signal
from websockets.asyncio.server import serve
from server import Server


def make_invitation(endpoint, room):
    """Keep the existing WebSocket URL usable without registering a URL handler."""
    parts = urlsplit(endpoint)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({'room': room}), ''))


def parse_invitation(value):
    try:
        parts = urlsplit(value.strip())
        room = parse_qs(parts.query, strict_parsing=True).get('room', [''])[0]
        if (parts.scheme not in ('ws', 'wss') or not parts.hostname or
                parts.username or parts.password or parts.fragment or
                not parts.path.startswith('/room/') or len(parts.path) > 100 or
                len(room) != 4 or not room.isascii() or not room.isdigit()):
            raise ValueError()
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError()
        return urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')), room
    except (ValueError, TypeError):
        raise ValueError('请粘贴房主分享的完整邀请链接') from None


class EmbeddedHost(QThread):
    ready = Signal(str, int)
    failed = Signal(str)

    def __init__(self, lan=False, parent=None):
        super().__init__(parent)
        self.lan = lan
        self.host_path = '/host/' + secrets.token_urlsafe(32)
        self.guest_path = '/room/' + secrets.token_urlsafe(32)
        self.port = 0
        self._loop = None
        self._shutdown = None
        self._stopping = threading.Event()

    def run(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            # Never include socket URLs or invitation secrets in logs/UI errors.
            self.failed.emit('房主服务启动失败：' + type(exc).__name__)

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._shutdown = asyncio.Event()
        async with Server(hosted=True) as server:
            async def authenticate(connection, request):
                # Browser cross-origin access is unnecessary; accept only our app.
                remote = connection.remote_address
                owner = (request.path == self.host_path and remote and
                         remote[0] in ('127.0.0.1', '::1'))
                if request.headers.get('Origin') or not (owner or request.path == self.guest_path):
                    return connection.respond(HTTPStatus.FORBIDDEN, 'Forbidden\n')
                # Never accept owner credentials through a public reverse proxy.
                if owner and ('CF-Connecting-IP' in request.headers or 'X-Forwarded-For' in request.headers):
                    return connection.respond(HTTPStatus.FORBIDDEN, 'Forbidden\n')

            async def handle(ws):
                await server.handle(ws, is_host=ws.request.path == self.host_path)

            async with serve(handle, '0.0.0.0' if self.lan else '127.0.0.1', 0,
                             process_request=authenticate, ping_interval=10, ping_timeout=30,
                             close_timeout=1, max_size=65536, max_queue=16) as listener:
                self.port = listener.sockets[0].getsockname()[1]
                if not self._stopping.is_set():
                    self.ready.emit('ws://127.0.0.1:' + str(self.port) + self.host_path, self.port)
                    await self._shutdown.wait()
                for room in list(server.rooms.values()):
                    server.disband(room)
                # Allow the bounded outboxes to deliver the terminal event.
                await asyncio.sleep(.15)
        self._loop = None

    def stop(self):
        self._stopping.set()
        loop = self._loop
        if loop and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._shutdown.set)
            except RuntimeError:
                pass
        return self.wait(4000)
