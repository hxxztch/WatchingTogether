"""WebSocket client for room communication - runs in a background thread."""
import asyncio
import json
import logging
import queue
from PySide6.QtCore import QThread, Signal, QObject

log = logging.getLogger(__name__)


class NetworkSignals(QObject):
    connected = Signal()
    disconnected = Signal()
    message_received = Signal(dict)
    error_occurred = Signal(str)


class NetworkClient(QThread):
    """Background thread that manages the WebSocket connection."""

    def __init__(self, url: str = "ws://localhost:9876", parent=None):
        super().__init__(parent)
        self.url = url
        self.signals = NetworkSignals()
        self._ws = None
        self._running = False
        self._send_queue = queue.Queue()
        self._loop = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._running = True
        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as e:
            log.error(f"Network thread error: {e}")
            self.signals.error_occurred.emit(str(e))
        finally:
            self._loop.close()

    async def _connect_loop(self):
        from websockets.asyncio.client import connect

        while self._running:
            try:
                async with connect(self.url, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    self.signals.connected.emit()
                    log.info(f"Connected to {self.url}")
                    receive_task = asyncio.create_task(self._receive_loop(ws))
                    send_task = asyncio.create_task(self._send_loop(ws))
                    done, pending = await asyncio.wait(
                        [receive_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    self._ws = None
                    self.signals.disconnected.emit()
            except Exception as e:
                if self._running:
                    log.warning(f"Connection failed: {e}, retrying in 3s...")
                    self.signals.error_occurred.emit(f"Connection failed, retrying in 3s")
                    await asyncio.sleep(3)

    async def _receive_loop(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
                self.signals.message_received.emit(msg)
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON: {raw[:100]}")

    async def _send_loop(self, ws):
        while self._running:
            try:
                msg = self._send_queue.get(timeout=0.1)
                await ws.send(json.dumps(msg, ensure_ascii=False))
            except queue.Empty:
                await asyncio.sleep(0)
            except Exception as e:
                log.error(f"Send failed: {e}")

    def send(self, msg: dict):
        """Thread-safe send. Called from the main thread."""
        self._send_queue.put(msg)

    def stop(self):
        self._running = False
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._cancel_all(), self._loop)
        self.quit()
        self.wait(3000)

    async def _cancel_all(self):
        for task in asyncio.all_tasks(self._loop):
            task.cancel()