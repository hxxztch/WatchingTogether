"""MPV player embedded in a QWidget for PySide6."""
import os
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal

_MPV_DLL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "libmpv", "libmpv-2.dll")
if os.path.exists(_MPV_DLL):
    os.environ["PATH"] = os.path.dirname(_MPV_DLL) + os.pathsep + os.environ.get("PATH", "")

import mpv


class MpvWidget(QWidget):
    """A QWidget that embeds an mpv video player."""

    position_changed = Signal(float)
    duration_changed = Signal(float)
    playback_started = Signal()
    playback_paused = Signal()
    playback_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setStyleSheet("background-color: black;")
        self._player = None
        self._setup_done = False

    def _ensure_player(self):
        if self._setup_done:
            return
        self._setup_done = True

        self._pending_dash_audio = None
        self._dash_seek_pos = 0
        self._dash_was_playing = True

        self._player = mpv.MPV(
            wid=str(int(self.winId())),
            keep_open="yes",
            osc="no",
            input_default_bindings=False,
            input_vo_keyboard=False,
            hwdec="auto",
            volume=80,
            volume_max=130,
        )

        @self._player.property_observer("time-pos")
        def _on_time(_name, value):
            if value is not None:
                self.position_changed.emit(value)

        @self._player.property_observer("duration")
        def _on_duration(_name, value):
            if value is not None:
                self.duration_changed.emit(value)

        @self._player.property_observer("pause")
        def _on_pause(_name, value):
            if value:
                self.playback_paused.emit()
            else:
                self.playback_started.emit()

        @self._player.event_callback("file-loaded")
        def _on_file_loaded(event):
            if self._pending_dash_audio and self._player:
                self._player.command("audio-add", self._pending_dash_audio, "select")
                self._pending_dash_audio = None
                # start property already positioned us; just restore play state
                self._player.pause = not self._dash_was_playing

        @self._player.event_callback("end-file")
        def _on_end(event):
            try:
                d = event.data if hasattr(event, 'data') else event
                reason = (d or {}).get('reason', 0) if isinstance(d, dict) else getattr(d, 'reason', 0)
            except Exception:
                reason = 0
            if reason == 0:
                self.playback_ended.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_player()

    @property
    def position(self) -> float:
        return self._player.time_pos if self._player else 0.0

    @property
    def duration(self) -> float:
        return self._player.duration if self._player else 0.0

    @property
    def is_playing(self) -> bool:
        return not self._player.pause if self._player else False

    def load(self, path: str, start_pos: float = 0.0):
        self._ensure_player()
        self._player.play(path)
        self._player.pause = True
        if start_pos > 0:
            self._player.wait_until_playing()
            self._player.seek(start_pos, "absolute")

    def replace(self, path: str):
        """Replace current file (for quality switching). Unlike load(), this stops old video."""
        self._ensure_player()
        self._player.command("stop")
        self._player.loadfile(path)
        self._player.pause = True

    def play(self):
        if self._player:
            self._player.pause = False

    def pause(self):
        if self._player:
            self._player.pause = True

    def toggle_play(self):
        if self._player:
            self._player.pause = not self._player.pause

    def load_dash(self, video_url, audio_url, resume_play=True, seek_pos=None):
        """Load DASH video and restore play state seamlessly."""
        if self._player:
            # Pause first to freeze the playback position before capturing it
            self._player.pause = True
            if seek_pos is not None:
                self._dash_seek_pos = seek_pos
            else:
                try:
                    self._dash_seek_pos = (self._player.command("get_property", "time-pos") or 0) + 0.15
                except Exception:
                    self._dash_seek_pos = (self._player.time_pos or 0) + 0.15
            self._dash_was_playing = resume_play
            self._player["http-header-fields"] = "Referer: https://www.bilibili.com/"
            self._pending_dash_audio = audio_url
            self._player.start = self._dash_seek_pos  # start at saved position
            self._player.loadfile(video_url)

    def loadfile(self, path: str):
        """Directly replace current file with new URL (for quality switching)."""
        if self._player:
            self._player.loadfile(path)

    def seek(self, position: float):
        if self._player:
            self._player.seek(position, "absolute")

    def seek_relative(self, seconds: float):
        if self._player:
            self._player.seek(seconds, "relative")

    def set_volume(self, vol: int):
        if self._player:
            self._player.volume = max(0, min(130, vol))

    @property
    def volume(self) -> int:
        return int(self._player.volume) if self._player else 80

    def load_subtitle(self, path: str):
        """Load an external subtitle file."""
        if self._player:
            self._player.sub_add(path)

    def get_audio_tracks(self):
        """Return list of audio tracks: [(id, label), ...]"""
        if not self._player:
            return []
        try:
            tracks = self._player.track_list
            return [(t["id"], t.get("lang", "") or t.get("title", "") or "Track " + str(t["id"]))
                    for t in tracks if t.get("type") == "audio"]
        except Exception:
            return []

    def set_audio_track(self, track_id: int):
        if self._player:
            self._player.aid = track_id

    def get_video_info(self) -> dict:
        """Return current video stream info: width, height, fps, codec."""
        if not self._player:
            return {}
        info = {}
        try:
            info['width'] = self._player._get_property('video-params/w')
            info['height'] = self._player._get_property('video-params/h')
            info['fps'] = self._player._get_property('video-params/average-fps')
            info['codec'] = self._player._get_property('video-codec')
        except Exception:
            pass
        return info

    def get_quality_label(self) -> str:
        """Human-readable quality string like '1080P 30fps'."""
        info = self.get_video_info()
        h = info.get('height')
        if not h:
            return ''
        fps = info.get('fps')
        parts = []
        h = int(h)
        if h >= 2160:
            parts.append('4K')
        elif h >= 1440:
            parts.append('2K')
        elif h >= 1080:
            parts.append('1080P')
        elif h >= 720:
            parts.append('720P')
        elif h >= 480:
            parts.append('480P')
        else:
            parts.append(str(h) + 'P')
        if fps:
            parts.append('%.0f' % int(round(float(fps))) + 'fps')
        return ' '.join(parts)
    def stop(self):
        if self._player:
            self._player.stop()

    def closeEvent(self, event):
        if self._player:
            self._player.stop()
        super().closeEvent(event)