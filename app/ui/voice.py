"""Optional room voice controls. Audio devices are opened only on demand."""
from collections import deque
import time

from PySide6.QtCore import QEvent, QTimer, Qt, QUrl
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from app.voice_codec import MAX_PACKET, RATE, SAMPLES
from app.voice_relay import VOICE_LIMIT


class RoomVoice(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = self.ticket = ''
        self.socket = self.codec = self.sink = self.source = None
        self.output = self.capture = None
        self.ready = False
        self.frames = {}
        self.pcm = bytearray()
        self.input_rate_state = self.output_rate_state = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.join = QPushButton('加入语音')
        self.join.clicked.connect(self.toggle)
        row.addWidget(self.join)
        self.talk = QPushButton('按住说话')
        self.talk.pressed.connect(self.start_capture)
        self.talk.released.connect(self.stop_capture)
        self.talk.installEventFilter(self)
        self.talk.hide()
        row.addWidget(self.talk)
        layout.addLayout(row)
        self.devices = QWidget(self)
        devices = QVBoxLayout(self.devices)
        devices.setContentsMargins(0, 0, 0, 0)
        for title, name in (('麦克风', 'mic'), ('扬声器', 'speaker')):
            device_row = QHBoxLayout()
            device_row.addWidget(QLabel(title))
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            setattr(self, name, combo)
            device_row.addWidget(combo, 1)
            devices.addLayout(device_row)
        self.speaker.currentIndexChanged.connect(self.change_output)
        self.mic.currentIndexChanged.connect(self.stop_capture)
        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel('语音音量'))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.valueChanged.connect(self.set_volume)
        volume_row.addWidget(self.volume, 1)
        devices.addLayout(volume_row)
        self.devices.hide()
        layout.addWidget(self.devices)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.timer = QTimer(self, interval=20, timerType=Qt.PreciseTimer)
        self.timer.timeout.connect(self.play_frame)
        self.deadline = QTimer(self, singleShot=True, interval=8000)
        self.deadline.timeout.connect(lambda: self.stop('语音连接超时，请重试'))
        QApplication.instance().applicationStateChanged.connect(self.application_state)
        self.hide()

    def application_state(self, state):
        if state != Qt.ApplicationActive:
            self.stop_capture()

    def eventFilter(self, watched, event):
        if watched is self.talk and event.type() in (QEvent.Hide, QEvent.FocusOut, QEvent.UngrabMouse):
            self.stop_capture()
        return super().eventFilter(watched, event)

    def set_room(self, url='', ticket=''):
        self.stop()
        self.url, self.ticket = url, ticket
        self.setVisible(bool(ticket))

    def toggle(self):
        if self.socket:
            self.stop()
            return
        if not self.ticket:
            return
        try:
            from PySide6.QtMultimedia import QMediaDevices
            from PySide6.QtWebSockets import QWebSocket
            from app.runtime import configure_qt_tls
            from app.voice_codec import Opus

            if self.url.startswith('wss:') and not configure_qt_tls():
                raise OSError('TLS unavailable')
            self.codec = Opus()
            for combo, choices, default in (
                (self.mic, QMediaDevices.audioInputs(), QMediaDevices.defaultAudioInput()),
                (self.speaker, QMediaDevices.audioOutputs(), QMediaDevices.defaultAudioOutput()),
            ):
                combo.blockSignals(True)
                combo.clear()
                for device in choices:
                    combo.addItem(device.description(), device)
                    if device.id() == default.id():
                        combo.setCurrentIndex(combo.count() - 1)
                combo.blockSignals(False)
            self.socket = QWebSocket(parent=self)
            self.socket.connected.connect(self.authenticate)
            self.socket.disconnected.connect(self.disconnected)
            self.socket.errorOccurred.connect(self.connection_error)
            self.socket.textMessageReceived.connect(self.on_text)
            self.socket.binaryMessageReceived.connect(self.on_audio)
            self.socket.setMaxAllowedIncomingMessageSize(1024)
            self.deadline.start()
            self.join.setText('取消连接')
            self.status.setText('正在连接语音…')
            self.socket.open(QUrl(self.url + '/voice'))
        except (ImportError, OSError, RuntimeError):
            self.stop('无法启动语音，请检查完整客户端和音频设备')

    def authenticate(self):
        if self.sender() is self.socket:
            self.socket.sendTextMessage(self.ticket)

    def disconnected(self):
        if self.sender() is self.socket:
            full = self.socket.closeCode() == 1013
            self.stop('语音人数已满（最多 6 人）' if full else '语音已断开，请重新加入')

    def connection_error(self, error):
        if self.sender() is self.socket:
            self.stop('语音连接失败，请检查网络后重试')

    def on_text(self, message):
        if self.sender() is not self.socket or message != 'ready' or self.ready:
            return
        self.ready = True
        self.deadline.stop()
        self.join.setText('退出语音')
        self.talk.show()
        self.devices.show()
        self.status.setText('语音已连接 · 麦克风关闭')
        self.change_output()
        self.timer.start()

    @staticmethod
    def audio_format(device):
        from PySide6.QtMultimedia import QAudioFormat
        fmt = device.preferredFormat()
        fmt.setSampleFormat(QAudioFormat.Int16)
        if fmt.channelCount() not in (1, 2) or not device.isFormatSupported(fmt):
            raise OSError('Unsupported audio device format')
        return fmt

    def change_output(self):
        if not self.ready:
            return
        from PySide6.QtMultimedia import QAudioSink
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = self.output = None
        self.frames.clear()
        self.output_rate_state = None
        device = self.speaker.currentData()
        try:
            if device is None:
                raise OSError('No output')
            self.output_format = self.audio_format(device)
            self.sink = QAudioSink(device, self.output_format, self)
            self.sink.setBufferSize(self.output_format.bytesForDuration(60000))
            self.set_volume(self.volume.value())
            self.output = self.sink.start()
            if self.output is None:
                raise OSError('Cannot open output')
            self.status.setText('语音已连接 · 麦克风关闭')
        except OSError:
            self.status.setText('无法打开扬声器，请选择其他设备')

    def set_volume(self, value):
        if self.sink:
            self.sink.setVolume(value / 100)

    def start_capture(self):
        if not self.ready or self.source:
            return
        from PySide6.QtMultimedia import QAudioSource
        device = self.mic.currentData()
        try:
            if device is None:
                raise OSError('No microphone')
            self.input_format = self.audio_format(device)
            self.codec.start_capture()
            self.source = QAudioSource(device, self.input_format, self)
            self.capture = self.source.start()
            if self.capture is None:
                raise OSError('Cannot open microphone')
            self.capture.readyRead.connect(self.read_capture)
            self.status.setText('麦克风开启 · 松开停止')
        except OSError:
            self.stop_capture()
            self.status.setText('无法打开麦克风，请检查设备和 Windows 权限')

    def read_capture(self):
        if not self.capture or not self.ready:
            return
        import audioop
        pcm = bytes(self.capture.readAll())
        channels = self.input_format.channelCount()
        if not pcm or len(pcm) % (2 * channels):
            return
        if channels == 2:
            pcm = audioop.tomono(pcm, 2, .5, .5)
        pcm, self.input_rate_state = audioop.ratecv(
            pcm, 2, 1, self.input_format.sampleRate(), RATE, self.input_rate_state)
        self.pcm.extend(pcm)
        size = SAMPLES * 2
        if len(self.pcm) >= size * 4 or self.socket.bytesToWrite() > 4096:
            self.pcm.clear()
            return
        while len(self.pcm) >= size:
            packet = self.codec.encode(bytes(self.pcm[:size]))
            del self.pcm[:size]
            if packet:
                self.socket.sendBinaryMessage(packet)

    def stop_capture(self):
        if self.source:
            source, self.source = self.source, None
            self.capture = None
            source.stop()
            source.deleteLater()
            if self.ready:
                self.status.setText('语音已连接 · 麦克风关闭')
        if self.codec:
            self.codec.stop_capture()
        self.pcm.clear()
        self.input_rate_state = None

    def on_audio(self, message):
        if self.sender() is not self.socket or not self.output or not 2 <= len(message) <= MAX_PACKET + 1:
            return
        packet = bytes(message)
        slot = packet[0]
        if slot < VOICE_LIMIT:
            self.frames.setdefault(slot, deque(maxlen=3)).append((time.monotonic(), packet[1:]))

    def play_frame(self):
        if not self.output:
            return
        import audioop
        now = time.monotonic()
        frames = []
        for slot, queue in self.frames.items():
            while queue and now - queue[0][0] > .1:
                queue.popleft()
            if queue:
                pcm = self.codec.decode(slot, queue.popleft()[1])
                if pcm:
                    frames.append(pcm)
        mixed = bytes(SAMPLES * 2)
        for pcm in frames:
            mixed = audioop.add(mixed, audioop.mul(pcm, 2, 1 / len(frames)), 2)
        mixed, self.output_rate_state = audioop.ratecv(
            mixed, 2, 1, RATE, self.output_format.sampleRate(), self.output_rate_state)
        if self.output_format.channelCount() == 2:
            mixed = audioop.tostereo(mixed, 2, 1, 1)
        if self.sink.bytesFree() >= len(mixed):
            self.output.write(mixed)

    def stop(self, message=''):
        self.ready = False
        self.timer.stop()
        self.deadline.stop()
        self.stop_capture()
        if self.socket:
            socket, self.socket = self.socket, None
            socket.abort()
            socket.deleteLater()
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = self.output = None
        if self.codec:
            self.codec.close()
            self.codec = None
        self.frames.clear()
        self.devices.hide()
        self.talk.hide()
        self.join.setText('加入语音')
        self.status.setText(message)
