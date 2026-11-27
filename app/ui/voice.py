"""Optional room voice controls. Audio devices are opened only on demand."""
from array import array
import logging
import math
import time

from PySide6.QtCore import QEvent, QTimer, Qt, QUrl
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from app.voice_codec import MAX_PACKET, RATE, SAMPLES
from app.voice_buffer import VoiceBuffer
from app.voice_relay import VOICE_LIMIT


PTT_KEY = Qt.Key_F8
UNITY_VOLUME = 50


class RoomVoice(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = self.ticket = ''
        self.socket = self.codec = self.sink = self.source = None
        self.output = self.capture = None
        self.media_devices = None
        self.selected_input = self.selected_output = None
        self.ready = False
        self.phase = 'idle'
        self.attempt = 0
        self.phase_started = 0.0
        self.ping_started = None
        self.rtt = None
        self.capture_drops = 0
        self.key_held = False
        self.frames = {}
        self.pcm = bytearray()
        self.input_rate_state = self.output_rate_state = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.join = QPushButton('加入语音')
        self.join.clicked.connect(self.toggle)
        row.addWidget(self.join)
        self.talk = QPushButton('按住说话 · F8')
        self.talk.pressed.connect(self.press_to_talk)
        self.talk.released.connect(self.release_to_talk)
        self.talk.clicked.connect(self.toggle_microphone)
        self.talk.hide()
        row.addWidget(self.talk)
        self.settings_button = QPushButton('设置')
        self.settings_button.setToolTip('语音设置')
        self.settings_button.setAccessibleName('语音设置')
        self.settings_button.clicked.connect(self.settings_dialog_open)
        self.settings_button.hide()
        row.addWidget(self.settings_button)
        layout.addLayout(row)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle('语音设置')
        devices = QVBoxLayout(self.settings_dialog)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel('发言方式'))
        self.speech_mode = QComboBox()
        self.speech_mode.addItem('按键发言（F8）', 'ptt')
        self.speech_mode.addItem('常驻麦克风', 'open')
        self.speech_mode.currentIndexChanged.connect(self.change_speech_mode)
        mode_row.addWidget(self.speech_mode, 1)
        devices.addLayout(mode_row)
        for title, name in (('麦克风', 'mic'), ('扬声器', 'speaker')):
            device_row = QHBoxLayout()
            device_row.addWidget(QLabel(title))
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            setattr(self, name, combo)
            device_row.addWidget(combo, 1)
            devices.addLayout(device_row)
        self.speaker.currentIndexChanged.connect(self.select_output)
        self.mic.currentIndexChanged.connect(self.select_input)
        self.input_volume = QSlider(Qt.Horizontal)
        self.output_volume = QSlider(Qt.Horizontal)
        volumes = QGridLayout()
        volumes.setColumnStretch(1, 1)
        for row_index, (title, slider) in enumerate((
            ('麦克风输入', self.input_volume),
            ('语音输出', self.output_volume),
        )):
            volumes.addWidget(QLabel(title), row_index, 0)
            slider.setAccessibleName(title)
            slider.setRange(0, 100)
            slider.setValue(UNITY_VOLUME)
            slider.setToolTip('50% 为原始音量，向右增强，向左减弱')
            volumes.addWidget(slider, row_index, 1)
            percent = QLabel(f'{UNITY_VOLUME}%')
            percent.setMinimumWidth(percent.fontMetrics().horizontalAdvance('100%'))
            slider.valueChanged.connect(lambda value, display=percent: display.setText(f'{value}%'))
            volumes.addWidget(percent, row_index, 2, Qt.AlignRight)
        devices.addLayout(volumes)
        buttons = QDialogButtonBox(self.settings_dialog)
        buttons.addButton('关闭', QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.settings_dialog.reject)
        devices.addWidget(buttons)
        self.settings_dialog.resize(460, devices.sizeHint().height())
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.timer = QTimer(self, interval=20, timerType=Qt.PreciseTimer)
        self.timer.timeout.connect(self.audio_tick)
        self.deadline = QTimer(self, singleShot=True)
        self.deadline.timeout.connect(lambda: self.connection_failed('timeout'))
        self.retry = QTimer(self, singleShot=True)
        self.retry.timeout.connect(self.connect_voice)
        self.health_timer = QTimer(self, interval=5000)
        self.health_timer.timeout.connect(self.check_health)
        QApplication.instance().applicationStateChanged.connect(self.application_state)
        self.hide()

    def application_state(self, state):
        if state != Qt.ApplicationActive and self.push_to_talk:
            self.stop_capture()

    def settings_dialog_open(self):
        if self.ready:
            self.settings_dialog.open()

    def eventFilter(self, watched, event):
        if self.ready and self.push_to_talk:
            kind = event.type()
            if watched is self.window() and kind == QEvent.WindowDeactivate:
                self.stop_capture()
            elif watched is self.talk and kind in (QEvent.Hide, QEvent.FocusOut, QEvent.UngrabMouse):
                if not self.key_held:
                    self.stop_capture()
            elif kind in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease) and event.key() == PTT_KEY:
                if kind == QEvent.KeyRelease and self.key_held:
                    if not event.isAutoRepeat():
                        self.key_held = False
                        if not self.talk.isDown():
                            self.stop_capture()
                    return True
                if QApplication.activeWindow() is self.window() and event.modifiers() == Qt.NoModifier:
                    event.accept()
                    if kind == QEvent.KeyPress and not event.isAutoRepeat() and not self.key_held:
                        self.key_held = True
                        self.start_capture()
                    return True
        return super().eventFilter(watched, event)

    @property
    def push_to_talk(self):
        return self.speech_mode.currentData() == 'ptt'

    def change_speech_mode(self):
        self.stop_capture()
        self.update_talk_button()

    def update_talk_button(self):
        if self.push_to_talk:
            text = '按住说话 · F8'
        else:
            text = '关闭麦克风' if self.source else '开启麦克风'
        self.talk.setText(text)

    def press_to_talk(self):
        if self.push_to_talk:
            self.start_capture()

    def release_to_talk(self):
        if self.push_to_talk and not self.key_held:
            self.stop_capture()

    def toggle_microphone(self):
        if not self.push_to_talk:
            if self.source:
                self.stop_capture()
            else:
                self.start_capture()

    def set_room(self, url='', ticket=''):
        self.stop()
        self.url, self.ticket = url, ticket
        self.setVisible(bool(ticket))

    def toggle(self):
        if self.socket or self.retry.isActive():
            self.stop()
        elif self.ticket:
            self.attempt = 0
            self.connect_voice()

    def connect_voice(self):
        if not self.ticket:
            return
        self.attempt += 1
        try:
            from PySide6.QtMultimedia import QMediaDevices
            from PySide6.QtWebSockets import QWebSocket
            from app.runtime import configure_qt_tls
            from app.voice_codec import Opus

            if self.url.startswith('wss:') and not configure_qt_tls():
                raise OSError('TLS unavailable')
            self.codec = Opus()
            if self.media_devices is None:
                self.media_devices = QMediaDevices(self)
                self.media_devices.audioInputsChanged.connect(self.refresh_inputs)
                self.media_devices.audioOutputsChanged.connect(self.refresh_outputs)
            self.refresh_inputs()
            self.refresh_outputs()
            self.socket = QWebSocket(parent=self)
            self.socket.connected.connect(self.authenticate)
            self.socket.disconnected.connect(self.disconnected)
            self.socket.errorOccurred.connect(self.connection_error)
            self.socket.textMessageReceived.connect(self.on_text)
            self.socket.binaryMessageReceived.connect(self.on_audio)
            self.socket.pong.connect(self.on_pong)
            self.socket.setMaxAllowedIncomingMessageSize(1024)
            self.phase = 'connect'
            self.phase_started = time.monotonic()
            self.deadline.start(15000 if self.url.startswith('wss:') else 5000)
            self.join.setText('取消连接')
            self.status.setText('正在连接语音…')
            self.socket.open(QUrl(self.url + '/voice'))
        except (ImportError, OSError, RuntimeError):
            self.stop('无法启动语音，请检查完整客户端和音频设备')

    def authenticate(self):
        if self.sender() is self.socket:
            logging.info('Voice transport connected duration_ms=%d', (time.monotonic() - self.phase_started) * 1000)
            self.phase = 'authenticate'
            self.phase_started = time.monotonic()
            self.deadline.start(6000)
            self.socket.sendTextMessage(self.ticket)

    def disconnected(self):
        if self.sender() is self.socket:
            code = self.socket.closeCode()
            code = getattr(code, 'value', code)
            if code == 1008:
                self.stop('房间语音会话已失效，请重新加入房间')
            else:
                self.connection_failed('close_' + str(code))

    def connection_error(self, error):
        if self.sender() is self.socket:
            from PySide6.QtNetwork import QAbstractSocket
            # A graceful server close may carry an admission or capacity error.
            if error == QAbstractSocket.RemoteHostClosedError:
                return
            if error == QAbstractSocket.SslHandshakeFailedError:
                self.stop('语音安全连接失败，请检查网络与系统时间')
                logging.warning('Voice TLS handshake failed')
                return
            self.connection_failed(getattr(error, 'name', 'socket_error'))

    def connection_failed(self, reason):
        logging.info('Voice failed phase=%s reason=%s attempt=%d', self.phase, reason, self.attempt)
        message = '语音人数已满或已有连接，请稍后重试' if reason == 'close_1013' else '语音连接失败，请检查网络后重试'
        self.stop(message)
        if self.ticket and self.attempt < 3:
            self.join.setText('取消重连')
            self.status.setText('语音连接中断，正在重试…')
            self.retry.start(1000 * self.attempt)

    def check_health(self):
        if not self.ready:
            return
        now = time.monotonic()
        if self.ping_started is not None:
            if now - self.ping_started >= 10:
                self.connection_failed('pong_timeout')
            return
        self.ping_started = now
        self.socket.ping()
        self.health_ticks += 1
        if self.health_ticks % 3 == 0:
            self.attempt = 1
            logging.info('Voice stats rtt_ms=%s capture_drops=%d playback_drops=%d underruns=%d',
                         self.rtt, self.capture_drops, sum(x.dropped for x in self.frames.values()),
                         sum(x.underruns for x in self.frames.values()))

    def on_pong(self, elapsed, _payload):
        if self.sender() is self.socket:
            self.ping_started = None
            self.rtt = elapsed

    def on_text(self, message):
        if self.sender() is not self.socket or message != 'ready' or self.ready:
            return
        self.ready = True
        logging.info('Voice ready auth_ms=%d', (time.monotonic() - self.phase_started) * 1000)
        self.phase = 'stream'
        self.health_ticks = self.capture_drops = 0
        QApplication.instance().installEventFilter(self)
        self.deadline.stop()
        self.join.setText('退出语音')
        self.talk.show()
        self.settings_button.show()
        self.status.setText('语音已连接 · 麦克风关闭')
        self.change_output()
        self.timer.start()
        self.health_timer.start()

    @staticmethod
    def refresh_devices(combo, devices, default):
        chosen = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        detail = ' · ' + default.description() if not default.isNull() else ''
        combo.addItem('系统默认' + detail, None)
        for device in devices:
            combo.addItem(device.description(), device.id())
        index = combo.findData(chosen) if chosen is not None else 0
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def refresh_inputs(self):
        self.refresh_devices(self.mic, self.media_devices.audioInputs(), self.media_devices.defaultAudioInput())
        self.select_input()

    def refresh_outputs(self):
        self.refresh_devices(self.speaker, self.media_devices.audioOutputs(), self.media_devices.defaultAudioOutput())
        self.select_output()

    @staticmethod
    def selected_device(combo, devices, default):
        chosen = combo.currentData()
        return next((device for device in devices if device.id() == chosen), default)

    def select_input(self):
        device = self.selected_device(self.mic, self.media_devices.audioInputs(), self.media_devices.defaultAudioInput())
        if device != self.selected_input:
            self.stop_capture()
            self.selected_input = device

    def select_output(self):
        device = self.selected_device(self.speaker, self.media_devices.audioOutputs(), self.media_devices.defaultAudioOutput())
        if device != self.selected_output:
            self.selected_output = device
            self.change_output()

    @staticmethod
    def audio_format(device):
        from PySide6.QtMultimedia import QAudioFormat
        fmt = device.preferredFormat()
        formats = (QAudioFormat.Int16, QAudioFormat.Float, QAudioFormat.Int32, QAudioFormat.UInt8)
        if (not fmt.isValid() or not 1 <= fmt.channelCount() <= 32
                or fmt.sampleFormat() not in formats):
            raise OSError('Unsupported audio device format')
        return fmt

    @staticmethod
    def device_to_pcm16(data, fmt):
        import audioop
        from PySide6.QtMultimedia import QAudioFormat

        sample_format = fmt.sampleFormat()
        if sample_format == QAudioFormat.Float:
            samples = array('f')
            samples.frombytes(data)
            return array('h', (int(max(-32768, min(32767, sample * 32768)))
                               if math.isfinite(sample) else 0
                               for sample in samples)).tobytes()
        if sample_format == QAudioFormat.Int32:
            return audioop.lin2lin(data, 4, 2)
        if sample_format == QAudioFormat.UInt8:
            return audioop.lin2lin(audioop.bias(data, 1, -128), 1, 2)
        return data

    @staticmethod
    def capture_mono(pcm, channels):
        import audioop
        if channels == 1:
            return pcm
        if channels == 2:
            return audioop.tomono(pcm, 2, .5, .5)
        samples = array('h')
        samples.frombytes(pcm)
        return array('h', (int(sum(samples[i:i + channels]) / channels)
                           for i in range(0, len(samples), channels))).tobytes()

    @staticmethod
    def output_channels(pcm, fmt):
        import audioop
        from PySide6.QtMultimedia import QAudioFormat
        channels = fmt.channelCount()
        if channels == 1:
            return pcm
        if channels == 2:
            return audioop.tostereo(pcm, 2, 1, 1)
        samples = array('h')
        samples.frombytes(pcm)
        output = array('h', [0]) * (len(samples) * channels)
        positions = (QAudioFormat.FrontLeft, QAudioFormat.FrontRight)
        offsets = [fmt.channelOffset(position) for position in positions]
        for offset in [offset for offset in offsets if 0 <= offset < channels] or [0, 1]:
            output[offset::channels] = samples
        return output.tobytes()

    @staticmethod
    def pcm16_to_device(data, fmt):
        import audioop
        from PySide6.QtMultimedia import QAudioFormat

        sample_format = fmt.sampleFormat()
        if sample_format == QAudioFormat.Float:
            samples = array('h')
            samples.frombytes(data)
            return array('f', (sample / 32768 for sample in samples)).tobytes()
        if sample_format == QAudioFormat.Int32:
            return audioop.lin2lin(data, 2, 4)
        if sample_format == QAudioFormat.UInt8:
            return audioop.bias(audioop.lin2lin(data, 2, 1), 1, 128)
        return data

    def change_output(self):
        if not self.ready:
            return
        from PySide6.QtMultimedia import QAudio, QAudioSink
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = self.output = None
        self.frames.clear()
        self.output_rate_state = None
        device = self.selected_output
        try:
            if device is None or device.isNull():
                raise OSError('No output')
            self.output_format = self.audio_format(device)
            self.sink = QAudioSink(device, self.output_format, self)
            self.sink.setBufferSize(self.output_format.bytesForDuration(60000))
            self.output = self.sink.start()
            if self.output is None or self.sink.error() != QAudio.NoError:
                raise OSError('Cannot start audio stream: ' + self.sink.error().name)
            self.status.setText('语音已连接 · 麦克风' + ('开启' if self.source else '关闭'))
        except OSError as exc:
            logging.warning('Voice output unavailable: %s', exc)
            if self.sink:
                self.sink.stop()
                self.sink.deleteLater()
                self.sink = self.output = None
            self.status.setText('无法打开扬声器，请选择其他设备')

    def start_capture(self):
        if not self.ready or self.source:
            return
        from PySide6.QtMultimedia import QAudio, QAudioSource
        device = self.selected_input
        try:
            if device is None or device.isNull():
                raise OSError('No microphone')
            self.input_format = self.audio_format(device)
            self.codec.start_capture()
            self.source = QAudioSource(device, self.input_format, self)
            self.source.setBufferSize(self.input_format.bytesForDuration(40000))
            self.capture = self.source.start()
            if self.capture is None or self.source.error() != QAudio.NoError:
                raise OSError('Cannot start audio stream: ' + self.source.error().name)
            self.capture.readyRead.connect(self.read_capture)
            self.status.setText('麦克风开启 · 松开停止' if self.push_to_talk else '麦克风已常驻开启')
            self.update_talk_button()
        except OSError as exc:
            logging.warning('Voice capture unavailable: %s', exc)
            self.stop_capture()
            self.status.setText('无法打开麦克风，请检查设备和 Windows 权限')

    def read_capture(self):
        if not self.capture or not self.ready:
            return
        import audioop
        pcm = bytes(self.capture.readAll())
        channels = self.input_format.channelCount()
        if not pcm or len(pcm) % self.input_format.bytesPerFrame():
            return
        pcm = self.capture_mono(self.device_to_pcm16(pcm, self.input_format), channels)
        pcm, self.input_rate_state = audioop.ratecv(
            pcm, 2, 1, self.input_format.sampleRate(), RATE, self.input_rate_state)
        self.pcm.extend(pcm)
        self.trim_capture(5)

    def trim_capture(self, keep_frames):
        size = SAMPLES * 2
        excess = len(self.pcm) // size - keep_frames
        if excess > 0:
            del self.pcm[:excess * size]
            self.capture_drops += excess

    def audio_tick(self):
        if self.capture and self.ready and len(self.pcm) >= SAMPLES * 2:
            self.send_frame()
        self.play_frame()

    def send_frame(self):
        import audioop
        if self.socket.bytesToWrite() > 384:
            self.trim_capture(2)
            return
        size = SAMPLES * 2
        frame = bytes(self.pcm[:size])
        del self.pcm[:size]
        gain = self.input_volume.value() / UNITY_VOLUME
        if gain != 1.0:
            frame = audioop.mul(frame, 2, gain)
        packet = self.codec.encode(frame)
        if packet:
            self.socket.sendBinaryMessage(packet)

    def stop_capture(self):
        self.key_held = False
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
        self.update_talk_button()

    def on_audio(self, message):
        if self.sender() is not self.socket or not self.output or not 2 <= len(message) <= MAX_PACKET + 1:
            return
        packet = bytes(message)
        slot = packet[0]
        if slot < VOICE_LIMIT:
            buffer = self.frames.get(slot)
            if buffer is None:
                buffer = self.frames[slot] = VoiceBuffer()
            buffer.put(time.monotonic(), packet[1:])

    def play_frame(self):
        if not self.output or self.sink.bytesFree() < self.output_format.bytesForDuration(20000):
            return
        import audioop
        now = time.monotonic()
        frames = []
        for slot, buffer in self.frames.items():
            packet = buffer.take(now)
            if packet is not None:
                pcm = self.codec.decode(slot, packet)
                if pcm:
                    frames.append(pcm)
        mixed = bytes(SAMPLES * 2)
        for pcm in frames:
            mixed = audioop.add(mixed, audioop.mul(pcm, 2, 1 / len(frames)), 2)
        mixed, self.output_rate_state = audioop.ratecv(
            mixed, 2, 1, RATE, self.output_format.sampleRate(), self.output_rate_state)
        gain = self.output_volume.value() / UNITY_VOLUME
        if gain != 1.0:
            mixed = audioop.mul(mixed, 2, gain)
        mixed = self.pcm16_to_device(self.output_channels(mixed, self.output_format), self.output_format)
        if self.sink.bytesFree() >= len(mixed):
            self.output.write(mixed)

    def stop(self, message=''):
        if self.ready:
            QApplication.instance().removeEventFilter(self)
        self.ready = False
        self.phase = 'idle'
        self.ping_started = self.rtt = None
        self.timer.stop()
        self.deadline.stop()
        self.retry.stop()
        self.health_timer.stop()
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
        if self.settings_dialog.isVisible():
            self.settings_dialog.reject()
        self.settings_button.hide()
        self.talk.hide()
        self.join.setText('加入语音')
        self.status.setText(message)
