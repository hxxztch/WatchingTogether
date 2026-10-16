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
    media_load_failed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setStyleSheet("background-color: #f0f1f2;")
        self._player = None
        self._setup_done = False
        self._loading = False
        self._loading_path = None
        self._volume = 80

    def _ensure_player(self):
        if self._setup_done:
            return
        self._player = mpv.MPV(
            wid=str(int(self.winId())),
            keep_open="yes",
            osc="no",
            input_default_bindings=False,
            input_vo_keyboard=False,
            hwdec="auto",
            hr_seek="yes",
            cache="yes",
            demuxer_max_bytes="100M",
            demuxer_readahead_secs="30",
            volume=self._volume,
            volume_max=130,
        )
        self._setup_done = True

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
            if self._same_path(self._player.path, self._loading_path):
                self._loading = False

        @self._player.event_callback("end-file")
        def _on_end(event):
            try:
                d = event.data if hasattr(event, 'data') else event
                reason = (d or {}).get('reason', 0) if isinstance(d, dict) else getattr(d, 'reason', 0)
            except Exception:
                reason = 0
            if reason == 0:
                self.playback_ended.emit()
            elif reason == 4 and self._loading:
                self._loading = False
                self.media_load_failed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_player()

    @property
    def position(self) -> float:
        return (self._player.time_pos or 0.0) if self._player else 0.0

    @property
    def duration(self) -> float:
        return (self._player.duration or 0.0) if self._player else 0.0

    @property
    def is_playing(self) -> bool:
        return not self._player.pause if self._player else False

    @property
    def is_loading(self) -> bool:
        return self._loading

    @staticmethod
    def _same_path(actual, requested):
        if not actual or not requested:
            return False
        if "://" in actual or "://" in requested:
            return actual == requested
        # QFileDialog uses '/', while Windows mpv returns '\\'.
        return os.path.normcase(os.path.abspath(actual)) == os.path.normcase(os.path.abspath(requested))

    def load(self, path: str, start_pos: float = 0.0, resume_play=False):
        self._replace_stream(path, "", start_pos, resume_play)

    def replace(self, path: str):
        """Replace current file (for quality switching). Unlike load(), this stops old video."""
        self._replace_stream(path, "", 0, False)

    def replace_flv(self, path: str, seek_pos: float = 0.0, was_playing: bool = True):
        """Replace a progressive Bilibili stream without blocking the Qt thread."""
        self._replace_stream(path, "", seek_pos, was_playing, bilibili=True)

    def play(self):
        if self._player:
            self._player.pause = False

    def pause(self):
        if self._player:
            self._player.pause = True

    def toggle_play(self):
        if self._player:
            self._player.pause = not self._player.pause

    def _replace_stream(self, path, audio, position, playing, bilibili=False):
        self._ensure_player()
        self._loading, self._loading_path = True, path
        options = {"start": str(max(0, position or 0)), "pause": "no" if playing else "yes",
                   "audio-files": audio or ""}
        if bilibili:
            options["referrer"] = "https://www.bilibili.com/"
            options["user-agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        # python-mpv stringifies dict arguments. Use mpv's byte-length quoting
        # so commas in signed URLs cannot become additional loadfile options.
        encoded_options = ",".join(
            key + "=%" + str(len(value.encode("utf-8"))) + "%" + value
            for key, value in options.items())
        args = ["loadfile", path, "replace"]
        if self._player.mpv_version_tuple >= (0, 38, 0):
            args.append(-1)
        try:
            self._player.command(*args, encoded_options)
        except Exception:
            self._loading = False
            raise

    def load_dash(self, video_url, audio_url, resume_play=True, seek_pos=None):
        """Load video, external audio, seek position and pause state as one operation."""
        position = self.position if seek_pos is None else seek_pos
        self._replace_stream(video_url, audio_url, position, resume_play, bilibili=True)

    def loadfile(self, path: str):
        """Directly replace current file with new URL (for quality switching)."""
        self._replace_stream(path, "", 0, self.is_playing)

    def seek(self, position: float):
        if self._player and not self.is_loading and self.duration > 0:
            self._player.seek(position, "absolute", "exact")

    def seek_relative(self, seconds: float):
        if self._player and not self.is_loading and self.duration > 0:
            self._player.seek(seconds, "relative", "exact")

    def set_speed(self, speed: float):
        if self._player:
            self._player.speed = speed

    def set_volume(self, vol: int):
        self._volume = max(0, min(130, vol))
        if self._player:
            self._player.volume = self._volume

    @property
    def volume(self) -> int:
        return int(self._player.volume) if self._player else self._volume

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
        if info.get('width'):
            parts = [str(int(info['width'])) + '×' + str(h)]
        if fps:
            parts.append('%.0f' % int(round(float(fps))) + 'fps')
        return ' '.join(parts)
    def stop(self):
        self._loading = False
        if self._player:
            self._player.stop()

    def closeEvent(self, event):
        if self._player:
            self._player.stop()
        super().closeEvent(event)
