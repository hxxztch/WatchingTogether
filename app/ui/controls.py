"""Playback controls bar -- compact redesign V3."""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QLabel,
    QFileDialog, QLineEdit, QComboBox, QMenu, QFrame, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QEvent

MENU_STYLE = """
QMenu {
    background-color: #2a2a2a; color: #e0e0e0;
    border: 1px solid #555; padding: 4px 0;
    font-size: 12px;
}
QMenu::item {
    padding: 5px 24px;
}
QMenu::item:selected {
    background-color: #444;
}
QMenu::separator {
    height: 1px; background: #444; margin: 3px 8px;
}
"""


class ControlsBar(QWidget):

    play_toggled = Signal()
    seek_requested = Signal(float)
    volume_changed = Signal(int)
    file_selected = Signal(str)
    url_submitted = Signal(str)
    quality_selected = Signal(str)
    fullscreen_toggled = Signal()
    stop_requested = Signal()
    audio_selected = Signal(int)
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging_seek = False
        self._duration = 0.0
        self._muted = False
        self._vol_before_mute = 80
        self._audio_tracks = []
        self._page_list = []
        self._quality_list = []
        self._current_quality = ""
        self._setup_ui()

    # ================================================================
    #  layout
    # ================================================================
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        # -- open video --
        open_btn = QPushButton("\u6253\u5F00\u89C6\u9891")
        open_btn.setFixedSize(72, 26)
        open_btn.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 4px; }")
        open_menu = QMenu(self)
        open_menu.setStyleSheet(MENU_STYLE)
        open_menu.addAction("\u6253\u5F00\u672C\u5730\u89C6\u9891...", self._on_open_file)
        open_menu.addAction("URL\u6253\u5F00\u89C6\u9891...", self._on_url_dialog)
        open_btn.setMenu(open_menu)
        layout.addWidget(open_btn)

        # -- play --
        self._play_btn = QPushButton("\u25B6")
        self._play_btn.setFixedSize(30, 30)
        self._play_btn.setObjectName("play_btn")
        self._play_btn.setStyleSheet("font-size: 14px;")
        self._play_btn.clicked.connect(self._on_toggle_play)
        layout.addWidget(self._play_btn)

        # -- stop --
        stop_btn = QPushButton("■")
        stop_btn.setFixedSize(30, 30)
        stop_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; border: none; "
            "border-radius: 3px; font-size: 14px; padding: 0; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        layout.addWidget(stop_btn)

        # -- time --
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("time_label")
        self._time_label.setFixedWidth(105)
        self._time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._time_label)

        # -- seek --
        self._seek_bar = QSlider(Qt.Horizontal)
        self._seek_bar.setRange(0, 1000)
        self._seek_bar.setValue(0)
        self._seek_bar.sliderPressed.connect(self._on_seek_press)
        self._seek_bar.sliderReleased.connect(self._on_seek_release)
        layout.addWidget(self._seek_bar, stretch=1)

        # -- volume --
        vol_frame = QFrame()
        vol_frame.setFixedSize(32, 32)
        vol_frame.setStyleSheet(
            "QFrame { background-color: #2a2a2a; border: 1px solid #555; border-radius: 3px; }"
        )
        vol_layout = QVBoxLayout(vol_frame)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        vol_layout.setSpacing(0)

        self._vol_btn = QPushButton("\U0001F50A")
        self._vol_btn.setFixedSize(30, 30)
        f = self._vol_btn.font()
        f.setFamily("Segoe UI Emoji")
        f.setPointSize(12)
        self._vol_btn.setFont(f)
        self._vol_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; }"
        )
        self._vol_btn.setToolTip("\u97F3\u91CF: 80")
        self._vol_btn.clicked.connect(self._on_vol_toggle)
        self._vol_btn.installEventFilter(self)
        vol_layout.addWidget(self._vol_btn, alignment=Qt.AlignCenter)

        # Volume popup
        self._vol_popup = QFrame(self.window())
        self._vol_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._vol_popup.setStyleSheet(
            "QFrame { background-color: #2a2a2a; border: 1px solid #555; border-radius: 3px; }"
        )
        self._vol_popup.setFixedSize(32, 100)
        self._vol_popup.installEventFilter(self)
        vlay = QVBoxLayout(self._vol_popup)
        vlay.setContentsMargins(4, 4, 4, 4)

        self._vol_slider_v = QSlider(Qt.Vertical)
        self._vol_slider_v.setRange(0, 100)
        self._vol_slider_v.setValue(80)
        self._vol_slider_v.valueChanged.connect(self._on_volume)
        vlay.addWidget(self._vol_slider_v)

        layout.addWidget(vol_frame)

        # -- quality --
        self._quality_label = QLabel("\u753B\u8D28:")
        self._quality_label.setStyleSheet("font-size: 11px; color: #aaa; padding: 0 2px; min-width: 80px;")
        layout.addWidget(self._quality_label)

        self._quality_combo = QComboBox()
        self._quality_combo.setFixedWidth(68)
        self._quality_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a; color: #e0e0e0;
                border: 1px solid #555; border-radius: 3px;
                padding: 2px 4px; font-size: 11px;
            }
            QComboBox:hover { border-color: #888; }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a; color: #e0e0e0;
                selection-background-color: #444; outline: none;
            }
        """)
        self._quality_combo.currentTextChanged.connect(self._on_quality_change)
        self._quality_combo.hide()
        layout.addWidget(self._quality_combo)

        # -- more --
        self._more_btn = QPushButton("\u5176\u4ED6\u529F\u80FD")
        self._more_btn.setFixedSize(60, 26)
        self._more_btn.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 4px; }")
        self._more_menu = QMenu(self)
        self._more_menu.setStyleSheet(MENU_STYLE)
        self._more_btn.setMenu(self._more_menu)
        layout.addWidget(self._more_btn)
        self._rebuild_more_menu()

        # -- fullscreen --
        fs_btn = QPushButton("\u26F6")
        fs_btn.setFixedSize(28, 28)
        fs_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #555; "
            "border-radius: 3px; font-size: 13px; padding: 1px; }"
            "QPushButton:hover { background-color: #555; }"
        )
        fs_btn.clicked.connect(lambda: self.fullscreen_toggled.emit())
        layout.addWidget(fs_btn)

    # ================================================================
    #  event filter (volume popup)
    # ================================================================
    def eventFilter(self, obj, event):
        if obj == self._vol_btn:
            if event.type() == QEvent.Enter:
                self._show_vol_popup()
                return True
            elif event.type() == QEvent.Leave:
                QTimer.singleShot(200, self._check_vol_popup_hide)
                return True
            return False
        if hasattr(self, "_vol_popup") and obj == self._vol_popup:
            if event.type() == QEvent.Leave:
                self._vol_popup.hide()
                return True
        return super().eventFilter(obj, event)

    def _show_vol_popup(self):
        pos = self._vol_btn.mapToGlobal(QPoint(0, 0))
        self._vol_popup.move(pos.x(), pos.y() - self._vol_popup.height())
        self._vol_popup.show()

    def _check_vol_popup_hide(self):
        if not self._vol_popup.underMouse() and not self._vol_btn.underMouse():
            self._vol_popup.hide()

    # ================================================================
    #  button actions
    # ================================================================
    def _on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "\u6253\u5F00\u89C6\u9891\u6587\u4EF6", "",
            "\u89C6\u9891\u6587\u4EF6 (*.mp4 *.mkv *.avi *.flv *.webm *.mov *.m3u8);;\u6240\u6709\u6587\u4EF6 (*)"
        )
        if path:
            self.file_selected.emit(path)

    def _on_url_dialog(self):
        dlg = QDialog(self.window())
        dlg.setWindowTitle("URL\u6253\u5F00\u89C6\u9891")
        dlg.setFixedSize(420, 120)
        dlg.setStyleSheet(
            "QDialog { background-color: #1e1e1e; color: #e0e0e0; }"
            "QLabel { color: #d0d0d0; }"
        )
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)
        lay.addWidget(QLabel("\u8F93\u5165\u89C6\u9891\u7F51\u5740\uFF08\u652F\u6301B\u7AD9\u3001YouTube\u7B49\uFF09\uFF1A"))
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://...")
        url_input.setStyleSheet(
            "QLineEdit { background-color: #2a2a2a; color: #e0e0e0; "
            "border: 1px solid #555; border-radius: 3px; padding: 6px 8px; }"
        )
        lay.addWidget(url_input)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(
            "QPushButton { padding: 4px 16px; }"
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and url_input.text().strip():
            self.url_submitted.emit(url_input.text().strip())

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
        self._update_vol_icon(value)

    def _on_vol_toggle(self):
        if self._muted:
            self._muted = False
            self._vol_slider_v.setValue(self._vol_before_mute)
            self.volume_changed.emit(self._vol_before_mute)
        else:
            self._muted = True
            self._vol_before_mute = self._vol_slider_v.value()
            self._vol_slider_v.setValue(0)
            self.volume_changed.emit(0)
        self._update_vol_icon(self._vol_slider_v.value())

    def _update_vol_icon(self, vol):
        if vol == 0:
            self._vol_btn.setText("\U0001F507")
            self._muted = True
        elif vol < 40:
            self._vol_btn.setText("\U0001F508")
            self._muted = False
        else:
            self._vol_btn.setText("\U0001F50A")
            self._muted = False
        self._vol_btn.setToolTip("\u97F3\u91CF: {}".format(vol))

    # ================================================================
    #  more menu rebuild
    # ================================================================
    def _rebuild_more_menu(self):
        self._more_menu.clear()

        # Audio
        a_m = self._more_menu.addMenu("\u97F3\u8F68")
        if self._audio_tracks:
            for tid, label in self._audio_tracks:
                a_m.addAction(label, lambda checked=False, t=tid: self.audio_selected.emit(t))
        else:
            act = a_m.addAction("\u6682\u65E0\u97F3\u8F68")
            act.setEnabled(False)
        self._more_menu.addSeparator()

        # Page
        p_m = self._more_menu.addMenu("\u5206P")
        if self._page_list and len(self._page_list) > 1:
            for idx, title in self._page_list:
                p_m.addAction(title, lambda checked=False, i=idx: self.page_changed.emit(i))
        else:
            act = p_m.addAction("\u6682\u65E0\u5206P")
            act.setEnabled(False)

    # ================================================================
    #  public setters
    # ================================================================
    def set_audio_tracks(self, tracks, current_id=-1):
        self._audio_tracks = tracks[:] if tracks else []
        self._rebuild_more_menu()

    def set_video_quality(self, label="", qualities=None):
        self._quality_label.setText("\u753B\u8D28: " + (label if label else ""))
        self._quality_combo.blockSignals(True)
        self._quality_combo.clear()
        if qualities:
            self._quality_list = list(qualities)
            self._current_quality = label
            self._quality_combo.addItems(qualities)
            idx = self._quality_combo.findText(label)
            if idx >= 0:
                self._quality_combo.setCurrentIndex(idx)
            self._quality_combo.show()
        else:
            self._quality_list = []
            self._current_quality = ""
            self._quality_combo.hide()
        self._quality_combo.blockSignals(False)
        self._rebuild_more_menu()

    def _on_quality_change(self, text):
        if not text:
            return
        self._current_quality = text
        self._quality_label.setText("\u753B\u8D28: " + text)
        self.quality_selected.emit(text)

    def set_pages(self, pages, current_idx=0):
        self._page_list = pages[:] if pages else []
        self._rebuild_more_menu()

    # ================================================================
    #  state updates
    # ================================================================
    def set_playing(self, playing: bool):
        self._play_btn.setText("\u23F8" if playing else "\u25B6")

    def set_position(self, pos: float, duration: float):
        self._duration = duration
        if not self._dragging_seek and duration > 0:
            self._seek_bar.blockSignals(True)
            self._seek_bar.setValue(int(pos / duration * 1000))
            self._seek_bar.blockSignals(False)
        p_m, p_s = int(pos // 60), int(pos % 60)
        d_m = int(duration // 60) if duration > 0 else 0
        d_s = int(duration % 60) if duration > 0 else 0
        self._time_label.setText(f"{p_m:02d}:{p_s:02d} / {d_m:02d}:{d_s:02d}")

    def set_volume(self, vol: int):
        self._vol_slider_v.blockSignals(True)
        self._vol_slider_v.setValue(vol)
        self._vol_slider_v.blockSignals(False)
        self._update_vol_icon(vol)
