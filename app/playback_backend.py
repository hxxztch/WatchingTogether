"""Qt presentation for bounded WebRTC audio and video, alongside existing mpv."""
import time
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QWidget, QStackedLayout
from app.player import MpvWidget


class StreamSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mailbox = None
        self.image = QImage()
        self.state = {}
        self.updated = time.monotonic()
        self.volume = 80
        self.sink = self.device = None
        self.pending_audio = bytearray()
        self.timer = QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.poll)
        self.audio_checked = False

    def reset(self, mailbox=None):
        self.mailbox = mailbox
        self.image = QImage()
        self.pending_audio.clear()
        self.state = {}
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
        self.sink = self.device = None
        self.audio_checked = False
        if mailbox:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def _start_audio(self):
        self.audio_checked = True
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
        output = QMediaDevices.defaultAudioOutput()
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if output.isNull() or not output.isFormatSupported(fmt):
            return
        self.sink = QAudioSink(output, fmt, self)
        self.sink.setBufferSize(19200)  # 100 ms, independent from movie duration.
        self.sink.setVolume(self.volume / 100)
        self.device = self.sink.start()

    def poll(self):
        if not self.mailbox:
            return
        video, audio = self.mailbox.take()
        if video:
            raw, width, height = video
            self.image = QImage(raw, width, height, width * 3, QImage.Format_RGB888).copy()
            self.update()
        if audio:
            if not self.audio_checked:
                self._start_audio()
            if self.device:
                self.pending_audio.extend(audio)
                if len(self.pending_audio) > 48000:
                    self.pending_audio.clear()  # Drop backlog rather than build seconds of lag.
        if self.device and self.pending_audio:
            amount = min(self.sink.bytesFree(), len(self.pending_audio))
            amount -= amount % 4
            if amount:
                written = self.device.write(bytes(self.pending_audio[:amount]))
                if written > 0:
                    del self.pending_audio[:written]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#16191e'))
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
            painter.drawImage(x, y, self.image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            painter.setPen(QColor('#d9dfe5'))
            painter.drawText(self.rect(), Qt.AlignCenter, '等待房主推流 / 正在建立直连')


class PlaybackWidget(QWidget):
    """Existing mpv API with an optional receive-only WebRTC presentation surface."""
    position_changed = Signal(float)
    duration_changed = Signal(float)
    playback_started = Signal()
    playback_paused = Signal()
    playback_ended = Signal()
    media_load_failed = Signal()
    subtitles_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.local = MpvWidget(self)
        self.stream = StreamSurface(self)
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.local)
        self.stack.addWidget(self.stream)
        self.p2p = False
        for name in ('position_changed', 'duration_changed', 'playback_started', 'playback_paused',
                     'playback_ended', 'media_load_failed', 'subtitles_changed'):
            getattr(self.local, name).connect(getattr(self, name))
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(lambda: self.position_changed.emit(self.position) if self.p2p else None)
        self.timer.start()

    def __getattr__(self, name):
        local = self.__dict__.get('local')
        if local is not None:
            return getattr(local, name)
        raise AttributeError(name)

    @property
    def _player(self):
        return self.local._player

    @_player.setter
    def _player(self, value):
        self.local._player = value

    @property
    def _setup_done(self):
        return self.local._setup_done

    @_setup_done.setter
    def _setup_done(self, value):
        self.local._setup_done = value

    def set_p2p(self, enabled, mailbox=None):
        if enabled:
            self.local.stop()
        self.p2p = enabled
        self.stream.reset(mailbox if enabled else None)
        self.stack.setCurrentIndex(1 if enabled else 0)

    def stream_state(self, state):
        before = self.is_playing
        self.stream.state = dict(state)
        self.stream.updated = time.monotonic()
        self.duration_changed.emit(self.duration)
        if before != self.is_playing:
            (self.playback_started if self.is_playing else self.playback_paused).emit()

    @property
    def position(self):
        if not self.p2p:
            return self.local.position
        state = self.stream.state
        pos = state.get('position', 0) + (time.monotonic() - self.stream.updated if state.get('playing') else 0)
        return min(pos, self.duration) if self.duration else pos

    @property
    def duration(self):
        return self.stream.state.get('duration', 0) if self.p2p else self.local.duration

    @property
    def is_playing(self):
        return bool(self.stream.state.get('active') and self.stream.state.get('playing')) if self.p2p else self.local.is_playing

    @property
    def is_loading(self):
        return self.p2p and not self.stream.state.get('active') if self.p2p else self.local.is_loading

    def set_volume(self, volume):
        self.local.set_volume(volume)
        self.stream.volume = min(100, max(0, volume))
        if self.stream.sink:
            self.stream.sink.setVolume(self.stream.volume / 100)

    def set_speed(self, speed):
        if not self.p2p:
            self.local.set_speed(speed)

    def get_audio_tracks(self):
        return [] if self.p2p else self.local.get_audio_tracks()

    def get_video_info(self):
        return {} if self.p2p else self.local.get_video_info()

    def get_quality_label(self):
        return 'P2P · 最高 720p / 30fps' if self.p2p else self.local.get_quality_label()

    def stop(self):
        if self.p2p:
            self.stream.reset(self.stream.mailbox)
        else:
            self.local.stop()

    def shutdown(self):
        self.timer.stop()
        self.stream.reset()
        self.local.shutdown()
