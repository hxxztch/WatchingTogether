"""WebSocket networking; all session and queue state belongs to the worker loop."""
import asyncio
from collections import OrderedDict
import json
import logging
import random
import threading
import time
import uuid

from PySide6.QtCore import QThread, Signal, QObject
from websockets.asyncio.client import connect

log = logging.getLogger(__name__)


class NetworkSignals(QObject):
    connected = Signal()
    disconnected = Signal()
    message_received = Signal(dict)
    error_occurred = Signal(str)
    latency_updated = Signal(float)


class NetworkClient(QThread):
    CHAT_TTL = 60
    COMMAND_TTL = 5
    SYNC_INTERVAL = 2

    def __init__(self, url="ws://localhost:9877", parent=None):
        super().__init__(parent)
        self.url = url
        self.signals = NetworkSignals()
        self._ws = None
        self._loop = None
        self._runner = None
        self._stopping = threading.Event()
        self._send_queue = None
        self._generation = 0
        self._session = None
        self._ready = False
        self._membership_pending = False
        self._leaving = False
        self._pending_chats = OrderedDict()
        self._pending_controls = {}
        self._sync_requests = {}
        self._clock_offset = None
        self._best_rtt = None
        self._protocol = 1

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._runner = self._loop.create_task(self._connect_loop())
        if self._stopping.is_set():
            self._runner.cancel()
        try:
            self._loop.run_until_complete(self._runner)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Network worker stopped unexpectedly")
            self.signals.error_occurred.emit("网络线程异常，请刷新连接")
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    async def _connect_loop(self):
        failures = 0
        while not self._stopping.is_set():
            connected_at = None
            tasks = []
            try:
                async with connect(self.url, ping_interval=10, ping_timeout=30,
                                   open_timeout=5, close_timeout=2, max_size=65536) as ws:
                    connected_at = time.monotonic()
                    self._ws = ws
                    self._generation += 1
                    self._send_queue = asyncio.Queue(maxsize=128)
                    self._protocol = 1
                    self._clock_offset = self._best_rtt = None
                    self.signals.connected.emit()
                    if self._session:
                        self._membership_pending = True
                        if self._session.get("token"):
                            self._put({"type": "resume_room", "protocol": 2, **self._session})
                        else:
                            self._put({"type": "join_room", "protocol": 2, **self._session})
                    tasks = [asyncio.create_task(self._receive_loop(ws)),
                             asyncio.create_task(self._send_loop(ws)),
                             asyncio.create_task(self._sync_loop())]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Avoid logging URLs / session tokens from exception payloads.
                log.info("Connection interrupted: %s", type(exc).__name__)
            finally:
                self._ready = False
                self._membership_pending = False
                self._leaving = False
                self._ws = None
                self._send_queue = None
                self._pending_controls.clear()
                self._sync_requests.clear()
                if connected_at is not None:
                    self.signals.disconnected.emit()
            if self._stopping.is_set():
                break
            if connected_at is not None and time.monotonic() - connected_at >= 10:
                failures = 0
            delay = min(8, 0.5 * 2 ** min(failures, 4)) * random.uniform(0.8, 1.2)
            failures += 1
            self.signals.error_occurred.emit(f"连接中断，{delay:.1f}秒后重连")
            await asyncio.sleep(delay)

    def _put(self, message):
        if self._send_queue is None:
            return False
        try:
            self._send_queue.put_nowait((time.monotonic(), message))
            return True
        except asyncio.QueueFull:
            self.signals.error_occurred.emit("发送队列已满，请稍后重试")
            return False

    def send(self, message):
        """Schedule without blocking Qt; the worker checks membership and generation."""
        loop = self._loop
        if loop is None or loop.is_closed() or self._stopping.is_set():
            self.signals.error_occurred.emit("尚未连接服务器")
            return
        try:
            loop.call_soon_threadsafe(self._enqueue_command, dict(message), self._generation)
        except RuntimeError:
            self.signals.error_occurred.emit("连接已关闭")

    def _delivery_failed(self, text):
        self.signals.message_received.emit({"type": "delivery_failed", "message": text})

    def _forget_session(self):
        if self._pending_chats:
            self._delivery_failed("部分聊天未获服务器确认，已停止补发")
        self._session = None
        self._ready = False
        self._pending_chats.clear()
        self._pending_controls.clear()
        self._sync_requests.clear()

    def _enqueue_command(self, message, generation):
        mtype = message.get("type")
        if mtype == "leave_room":
            self._forget_session()
            self._membership_pending = False
            self._leaving = self._ws is not None
            if self._ws is not None:
                # Purge unsent actions before leaving; none can leak into another room.
                while self._send_queue is not None and not self._send_queue.empty():
                    self._send_queue.get_nowait()
                self._put(message)
            self.signals.message_received.emit({"type": "left_room"})
            return
        if mtype == "chat" and self._session:
            self._expire_chats()
            if len(self._pending_chats) >= 32:
                self._delivery_failed("待发送聊天已达上限，本条未发送")
                return
            message["id"] = uuid.uuid4().hex
            self._pending_chats[message["id"]] = (time.monotonic(), message)
            if self._ready:
                self._put(message)
            return
        if generation != self._generation or self._ws is None:
            self.signals.error_occurred.emit("尚未连接，操作未发送")
            return
        if mtype in ("create_room", "join_room"):
            if self._session or self._membership_pending or self._leaving:
                self.signals.error_occurred.emit("请先离开当前房间或等待连接完成")
                return
            message["protocol"] = 2
            self._membership_pending = self._put(message)
            return
        if not self._ready:
            self.signals.error_occurred.emit("正在恢复房间，播放操作未发送")
            return
        message["id"] = uuid.uuid4().hex
        if self._put(message) and self._protocol >= 2:
            self._pending_controls[message["id"]] = time.monotonic()

    def _expire_chats(self):
        now = time.monotonic()
        expired = [key for key, (created, _) in self._pending_chats.items()
                   if now - created >= self.CHAT_TTL]
        for key in expired:
            del self._pending_chats[key]
        if expired:
            self._delivery_failed("聊天发送确认超时，已停止补发")

    def _request_state(self):
        if not self._ready or self._protocol < 2:
            return
        request_id = uuid.uuid4().hex
        self._sync_requests[request_id] = time.monotonic()
        while len(self._sync_requests) > 8:
            del self._sync_requests[next(iter(self._sync_requests))]
        self._put({"type": "sync_request", "request_id": request_id})

    async def _sync_loop(self):
        while True:
            await asyncio.sleep(self.SYNC_INTERVAL)
            self._expire_chats()
            self._request_state()
            now = time.monotonic()
            for message_id, created in list(self._pending_controls.items()):
                if now - created >= self.COMMAND_TTL:
                    del self._pending_controls[message_id]
                    self.signals.error_occurred.emit("播放操作未获确认，正在恢复房间状态")
            # Only chat is replayable, with server-side per-session deduplication.
            if self._ready and self._protocol >= 2:
                for created, message in self._pending_chats.values():
                    if now - created >= 4:
                        self._put(message)

    async def _receive_loop(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
            except (ValueError, TypeError):
                continue
            self._handle_message(msg)

    def _handle_message(self, msg):
        mtype = msg.get("type")
        if mtype == "hello":
            self._protocol = msg.get("protocol", 1)
            return
        if mtype in ("room_created", "room_joined"):
            # A leave click can race a join response; don't resurrect the session.
            if self._leaving:
                return
            if not self._membership_pending:
                self._put({"type": "leave_room"})
                return
            self._membership_pending = False
            self._session = {"room": msg["room"], "name": msg.get("name", ""),
                             "token": msg.get("token"), "chat_seq": msg.get("chat_seq", 0)}
            self._protocol = msg.get("protocol", 1)
            self._ready = True
            self._expire_chats()
            if self._protocol >= 2:
                for _, message in self._pending_chats.values():
                    self._put(message)
            self._request_state()
        elif mtype == "session_expired":
            self._forget_session()
            self._membership_pending = False
        elif mtype == "left_room":
            self._forget_session()
            self._membership_pending = False
            self._leaving = False
        elif mtype == "ack":
            self._pending_chats.pop(msg.get("id"), None)
            self._pending_controls.pop(msg.get("id"), None)
            return
        elif mtype == "chat" and self._session and "seq" in msg:
            if msg["seq"] <= self._session["chat_seq"]:
                return
            self._session["chat_seq"] = msg["seq"]
        elif mtype == "error":
            self._pending_chats.pop(msg.get("id"), None)
            self._pending_controls.pop(msg.get("id"), None)
            if self._membership_pending:
                restoring = self._session is not None
                self._membership_pending = False
                self._forget_session()
                if restoring:
                    self.signals.message_received.emit({"type": "session_expired"})
                    return
        if isinstance(msg.get("state"), dict):
            now = time.monotonic()
            state = msg["state"]
            sent = self._sync_requests.pop(msg.get("request_id"), None)
            if sent is not None and "server_time" in state:
                rtt = now - sent
                if self._best_rtt is None or rtt <= self._best_rtt:
                    self._best_rtt = rtt
                    self._clock_offset = (sent + now) / 2 - state["server_time"]
                self.signals.latency_updated.emit(rtt * 1000)
            state["local_time"] = (state["server_time"] + self._clock_offset
                                   if self._clock_offset is not None and "server_time" in state else now)
            self._pending_controls.pop(msg.get("applied_id"), None)
            if mtype == "sync_state" and self._pending_controls:
                return  # Don't undo an optimistic local control with an older snapshot.
        self.signals.message_received.emit(msg)

    async def _send_loop(self, ws):
        while True:
            created, message = await self._send_queue.get()
            if time.monotonic() - created > self.COMMAND_TTL and message.get("type") != "chat":
                self._pending_controls.pop(message.get("id"), None)
                self.signals.error_occurred.emit("过期操作已丢弃")
                if message.get("type") in ("create_room", "join_room", "resume_room", "leave_room"):
                    raise ConnectionError("Room operation expired")
                continue
            if message.get("type") == "chat" and message.get("id") not in self._pending_chats:
                continue
            await asyncio.wait_for(ws.send(json.dumps(message, ensure_ascii=False)), 5)
            if self._protocol < 2 and message.get("type") == "chat":
                self._pending_chats.pop(message.get("id"), None)

    def _cancel_runner(self):
        if self._runner is not None:
            self._runner.cancel()

    def stop(self):
        self._stopping.set()
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._cancel_runner)
            except RuntimeError:
                pass
        return self.wait(5000)
