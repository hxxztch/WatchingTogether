"""Playback controls bar."""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSlider, QLabel, QFileDialog, QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt, Signal


class ControlsBar(QWidget):
    """Bottom bar with playback controls and video source input."""

    play_toggled = Signal()
    seek_requested = Signal(float)
    volume_changed = Signal(int)
    file_selected = Signal(str)
    url_submitted = Signal(str)
    fullscreen_toggled = Signal()
    stop_requested = Signal()
    audio_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._dragging_seek = False
        self._duration = 0.0

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        file_btn = QPushButton("文件")
        file_btn.setFixedWidth(72)
        file_btn.clicked.connect(self._on_open_file)
        layout.addWidget(file_btn)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("粘贴URL...")
        self._url_input.returnPressed.connect(self._on_url)
        layout.addWidget(self._url_input)

        url_btn = QPushButton("转到")
        url_btn.setFixedWidth(50)
        url_btn.clicked.connect(self._on_url)
        layout.addWidget(url_btn)

        layout.addSpacing(12)

        self._play_btn = QPushButton("\u25b6")
        self._play_btn.setFixedWidth(44)
        self._play_btn.setObjectName("play_btn")
        self._play_btn.clicked.connect(self._on_toggle_play)
        layout.addWidget(self._play_btn)

        stop_btn = QPushButton("停止")
        stop_btn.setFixedWidth(44)
        stop_btn.setStyleSheet("background-color: #f44336; color: white; border: none; border-radius: 3px; padding: 4px; font-size: 12px;")
        stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        layout.addWidget(stop_btn)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setObjectName("time_label")
        layout.addWidget(self._time_label)

        self._seek_bar = QSlider(Qt.Horizontal)
        self._seek_bar.setRange(0, 1000)
        self._seek_bar.sliderPressed.connect(self._on_seek_press)
        self._seek_bar.sliderReleased.connect(self._on_seek_release)
        layout.addWidget(self._seek_bar)

        vol_label = QLabel("音量")
        layout.addWidget(vol_label)

        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 130)
        self._vol_slider.setValue(80)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.valueChanged.connect(self._on_volume)
        layout.addWidget(self._vol_slider)

        aud_label = QLabel("音轨")
        layout.addWidget(aud_label)
        self._audio_combo = QComboBox()
        self._audio_combo.setFixedWidth(70)
        self._audio_combo.setStyleSheet("background: #2a2a2a; color: #ccc; border: 1px solid #444; font-size: 11px;")
        self._audio_combo.currentIndexChanged.connect(self._on_audio_change)
        layout.addWidget(self._audio_combo)

        fs_btn = QPushButton("全屏")
        fs_btn.setFixedWidth(44)
        fs_btn.clicked.connect(lambda: self.fullscreen_toggled.emit())
        layout.addWidget(fs_btn)

    def _on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.ts);;所有文件 (*.*)"
        )
        if path:
            self.file_selected.emit(path)

    def _on_url(self):
        url = self._url_input.text().strip()
        if url:
            self.url_submitted.emit(url)
            self._url_input.clear()

    def _on_toggle_play(self):
        self.play_toggled.emit()

    def _on_seek_press(self):
        self._dragging_seek = True

    def _on_seek_release(self):
        self._dragging_seek = False
        pos = self._seek_bar.value() / 1000.0 * self._duration
        self.seek_requested.emit(pos)

    def _on_volume(self, value: int):
        self.volume_changed.emit(value)

    _audio_lock = False

    def set_audio_tracks(self, tracks, current_id=-1):
        self._audio_lock = True
        self._audio_combo.clear()
        for tid, label in tracks:
            self._audio_combo.addItem(label, tid)
            if tid == current_id:
                self._audio_combo.setCurrentIndex(self._audio_combo.count() - 1)
        self._audio_lock = False

    def _on_audio_change(self, idx):
        if self._audio_lock or idx < 0:
            return
        tid = self._audio_combo.itemData(idx)
        if tid is not None:
            self.audio_selected.emit(tid)

    def set_playing(self, playing: bool):
        self._play_btn.setText("\u23f8" if playing else "\u25b6")

    def set_position(self, pos: float, duration: float):
        self._duration = duration
        if not self._dragging_seek and duration > 0:
            self._seek_bar.blockSignals(True)
            self._seek_bar.setValue(int(pos / duration * 1000))
            self._seek_bar.blockSignals(False)

        p_m, p_s = int(pos // 60), int(pos % 60)
        d_m, d_s = int(duration // 60) if duration > 0 else 0, int(duration % 60) if duration > 0 else 0
        self._time_label.setText(f"{p_m:02d}:{p_s:02d} / {d_m:02d}:{d_s:02d}")

    def set_volume(self, vol: int):
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(vol)
        self._vol_slider.blockSignals(False)