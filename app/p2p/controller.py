"""Qt bridge for the optional first-stage LAN P2P engine."""
import asyncio
import threading
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage
from app.p2p.mailbox import MediaMailbox


class P2PWorker(QThread):
    outgoing = Signal(dict)
    status = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mailbox = MediaMailbox()
        self.loop = self.queue = None
        self.lock = threading.Lock()
        self.pending = []
        self.stopping = False

    def run(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self.status.emit('P2P 媒体组件启动失败：' + type(exc).__name__, False)

    async def _run(self):
        from app.p2p.engine import P2PEngine
        engine = P2PEngine(self.outgoing.emit, self.status.emit, self.mailbox)
        with self.lock:
            self.loop = asyncio.get_running_loop()
            self.queue = asyncio.Queue(maxsize=64)
            for item in self.pending:
                self.queue.put_nowait(item)
            self.pending.clear()
        try:
            while True:
                command, payload = await self.queue.get()
                if command == 'close':
                    break
                try:
                    if command == 'load':
                        await engine.load(**payload)
                    elif command == 'seek' and engine.source:
                        await engine.load(engine.source.path, payload['position'], engine.source.playing)
                    elif command == 'pause':
                        await engine.pause(payload['paused'])
                    elif command == 'stop':
                        await engine.stop_source()
                    elif command == 'offer':
                        await engine.offer(payload['peer_id'])
                    elif command == 'remove':
                        await engine.remove(payload['peer_id'])
                    elif command == 'signal':
                        await engine.signal(payload)
                    elif command == 'state':
                        await engine.set_state(payload)
                except Exception as exc:
                    self.status.emit('媒体操作失败：' + type(exc).__name__, False)
                    if command in ('load', 'seek'):
                        await engine.stop_source()
        finally:
            await engine.close()
            with self.lock:
                self.loop = self.queue = None

    def submit(self, command, **payload):
        with self.lock:
            if self.stopping and command != 'close':
                return
            if self.loop is None:
                if len(self.pending) < 64:
                    self.pending.append((command, payload))
                return
            def enqueue():
                if self.queue is not None:
                    if command == 'close':
                        while not self.queue.empty():
                            self.queue.get_nowait()
                    if not self.queue.full():
                        self.queue.put_nowait((command, payload))
            self.loop.call_soon_threadsafe(enqueue)

    def stop(self):
        self.stopping = True
        self.submit('close')
        self.wait(15000)


class P2PController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.worker = None
        self.active = self.host = False

    def enter(self, message):
        self.leave()
        if message.get('watch_mode') != 'p2p':
            return
        from app.p2p import available
        if not available():
            self.owner._room_panel.set_status('请使用 Python 3.11+ 并安装 requirements-p2p.txt', '#b36b4a')
            return
        self.active = True
        self.owner._invalidate_quality_request()
        self.owner._bili_info = None
        self.owner._controls.set_video_quality('', None)
        self.owner._controls.set_audio_tracks([], -1)
        self.owner._controls.set_pages([], 0)
        self.owner._room_panel.watch_mode.setCurrentIndex(1)
        self.host = message['peer_id'] == message['publisher_id']
        worker = self.worker = P2PWorker(self)
        worker.outgoing.connect(self._send)
        worker.status.connect(self._status)
        worker.start()
        self.owner._player.set_p2p(True, worker.mailbox)
        self.owner._empty_stage.hide()
        self.owner._controls.set_media_title('请选择本地视频开始推流' if self.host else '等待房主推流', 'P2P 房主推流')
        self._controls()
        self.owner._room_panel.p2p_retry.setVisible(not self.host)
        if self.host:
            self.owner._network.send({'type': 'p2p_state', 'active': False})
            if message.get('resumed'):
                self.owner._room_panel.p2p_status.setText('房间已恢复，请重新选择本地视频开始推流')
        elif message.get('stream'):
            self.state(message['stream'])
        if not self.host:
            self.retry()

    def _controls(self):
        controls = self.owner._controls
        for name in ('_play_btn', '_stop_btn', '_seek_bar', '_time_stack'):
            getattr(controls, name).setEnabled(not self.active or self.host)
        # File/url menus remain available, but all entry paths enforce permissions.
        for name in ('_audio_combo', '_quality_combo', '_page_combo', '_subtitle_btn'):
            widget = getattr(controls, name, None)
            if widget is not None:
                widget.setEnabled(not self.active)
        controls._subtitle_undo.setEnabled(not self.active and bool(self.owner._player.local._subtitle_history))
        controls._open_btn.setEnabled(not self.active or self.host)
        if hasattr(self.owner, '_pip'):
            self.owner._pip.play.setEnabled(not self.active or self.host)

    def _send(self, message):
        if self.worker and self.sender() is self.worker and self.owner._room_ready:
            self.owner._network.send(message)

    def _status(self, text, connected):
        if self.worker and self.sender() is self.worker:
            self.owner._room_panel.p2p_status.setText(text)

    def retry(self):
        if self.active and not self.host:
            self.owner._network.send({'type': 'p2p_ready'})

    def state(self, state):
        if not self.active:
            return
        surface = self.owner._player.stream
        if surface.state.get('stream_id') != state.get('stream_id'):
            surface.reset(self.worker.mailbox)
        self.owner._player.stream_state(state)
        self.owner._controls.set_media_title(state.get('title', '等待房主推流'), 'P2P 房主推流')
        self.owner._controls.set_position(self.owner._player.position, self.owner._player.duration)
        self.owner._controls.set_playing(self.owner._player.is_playing)
        if not self.host:
            self.worker.submit('state', **state)
        if not state.get('active'):
            self.owner._player.stream.image = QImage()
            self.owner._player.stream.update()

    def message(self, message):
        if not self.active:
            return
        kind = message.get('type')
        if kind == 'p2p_state':
            self.state(message['stream'])
        elif kind == 'p2p_ready' and self.host:
            self.worker.submit('offer', peer_id=message['from_peer'])
        elif kind == 'p2p_signal':
            self.worker.submit('signal', **message)
        elif kind == 'member_left' and self.host:
            self.worker.submit('remove', peer_id=message.get('peer_id'))

    def open(self, path):
        if self.host and self.worker:
            self.worker.submit('load', path=path)
        else:
            self.owner._room_panel.set_status('推流模式由房主选择影片', '#95724f')

    def leave(self):
        worker, self.worker = self.worker, None
        self.active = self.host = False
        if worker:
            worker.stop()
            worker.deleteLater()
        if hasattr(self.owner, '_player'):
            self.owner._player.set_p2p(False)
        if hasattr(self.owner, '_controls'):
            self._controls()
        self.owner._room_panel.p2p_retry.hide()
        self.owner._room_panel.p2p_status.clear()
