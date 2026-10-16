"""Playback controls bar -- compact redesign V3."""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QLabel,
    QFileDialog, QLineEdit, QComboBox, QMenu, QFrame, QDialog, QDialogButtonBox, QStackedWidget, QToolTip,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QEvent
from PySide6.QtWidgets import QStyle, QStyleOptionSlider
from PySide6.QtGui import QPixmap, QCursor
import os as _os, sys as _sys
from app.timecode import parse_timecode, format_timecode

if getattr(_sys, "frozen", False):
    _B = _sys._MEIPASS
else:
    _B = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_BILI_LOGO = _os.path.join(_B, "assets", "bilibililogo.png")

MENU_STYLE = """
QMenu {
    background-color: #fffaf4; color: #58493c;
    border: 1px solid #d9c8b7; padding: 4px 0;
    font-size: 12px;
}
QMenu::item {
    padding: 5px 24px;
}
QMenu::item:selected {
    background-color: #ede1d4;
}
QMenu::separator {
    height: 1px; background: #ede1d4; margin: 3px 8px;
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

    danmaku_sent = Signal(str)

    bili_login_requested = Signal()
    bili_logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging_seek = False
        self._duration = 0.0
        self._position = 0.0
        self._muted = False
        self._vol_before_mute = 80
        self._audio_tracks = []
        self._page_list = []
        self._quality_list = []
        self._current_quality = ""
        self._bili_logged_in = False
        self._bili_uname = ""

        self._setup_ui()

    # ================================================================
    #  layout
    # ================================================================
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(9)
        timeline = QHBoxLayout()
        timeline.setSpacing(14)
        layout = QHBoxLayout()
        layout.setSpacing(6)
        root.addLayout(timeline)
        root.addLayout(layout)

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
            "QPushButton { background-color: rgba(255, 255, 255, 205); color: #656a70; border: 1px solid rgba(210, 205, 200, 170); "
            "border-radius: 3px; font-size: 14px; padding: 0; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 240); }"
        )
        stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        layout.addWidget(stop_btn)

        # -- time --
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("time_label")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setCursor(Qt.PointingHandCursor)
        self._time_label.setToolTip("点击输入时间跳转（秒数、分:秒、时:分:秒）")
        self._time_label.installEventFilter(self)
        self._time_editor = QLineEdit()
        self._time_editor.setAlignment(Qt.AlignCenter)
        self._time_editor.setMaxLength(12)
        self._time_editor.setAccessibleName("跳转到时间")
        self._time_editor.setToolTip("回车跳转，Esc取消")
        self._time_editor.returnPressed.connect(self._submit_time)
        self._time_editor.installEventFilter(self)
        self._time_stack = QStackedWidget()
        self._time_stack.setFixedWidth(115)
        self._time_stack.addWidget(self._time_label)
        self._time_stack.addWidget(self._time_editor)
        timeline.addWidget(self._time_stack)

        # -- seek --
        self._seek_bar = QSlider(Qt.Horizontal)
        self._seek_bar.setRange(0, 1000)
        self._seek_bar.setValue(0)
        self._seek_bar.sliderPressed.connect(self._on_seek_press)
        self._seek_bar.sliderReleased.connect(self._on_seek_release)
        self._seek_bar.installEventFilter(self)
        timeline.addWidget(self._seek_bar, stretch=1)

        # -- danmaku input --
        self._danmaku_input = QLineEdit()
        self._danmaku_input.setMaxLength(4000)
        self._danmaku_input.setMinimumWidth(70)
        self._danmaku_input.setMaximumWidth(150)
        self._danmaku_input.setStyleSheet("background-color: rgba(255, 255, 255, 210); color: #58493c; border: 1px solid rgba(210, 205, 200, 170); border-radius: 5px; padding: 4px 6px; font-size: 11px;")
        self._danmaku_input.setPlaceholderText("发个弹幕...")
        self._danmaku_input.returnPressed.connect(self._on_danmaku)
        timeline.addWidget(self._danmaku_input)
        self._danmaku_btn = QPushButton("发送")
        self._danmaku_btn.setFixedSize(36, 24)
        self._danmaku_btn.setStyleSheet("QPushButton { background-color: rgba(255, 255, 255, 205); color: #675548; border: 1px solid rgba(210, 205, 200, 170); border-radius: 5px; font-size: 11px; padding: 0; } QPushButton:hover { background-color: rgba(255, 255, 255, 240); }")
        self._danmaku_btn.clicked.connect(self._on_danmaku)
        timeline.addWidget(self._danmaku_btn)

        # -- volume --
        vol_frame = QFrame()
        vol_frame.setFixedSize(32, 32)
        vol_frame.setStyleSheet(
            "QFrame { background-color: rgba(255, 255, 255, 205); border: 1px solid rgba(210, 205, 200, 170); border-radius: 5px; }"
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
        self._vol_popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self._vol_popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._vol_popup.setStyleSheet(
            "QFrame { background-color: #fffaf4; border: 1px solid #d9c8b7; border-radius: 3px; }"
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

        self._vol_hide_timer = QTimer(self)
        self._vol_hide_timer.timeout.connect(self._vol_hide_check)

        layout.addWidget(vol_frame)
        layout.addStretch()

        # -- quality --
        self._quality_label = QLabel("\u753B\u8D28:")
        self._quality_label.setStyleSheet("background: rgba(255, 255, 255, 210); border-radius: 5px; font-size: 11px; color: #675d54; padding: 5px 8px; min-width: 80px;")
        self._quality_label.setMaximumWidth(150)
        layout.addWidget(self._quality_label)

        self._quality_combo = QComboBox()
        self._quality_combo.setFixedWidth(68)
        self._quality_combo.setStyleSheet("""
            QComboBox {
                background-color: #fffaf4; color: #58493c;
                border: 1px solid #d9c8b7; border-radius: 3px;
                padding: 2px 4px; font-size: 11px;
            }
            QComboBox:hover { border-color: #927b66; }
            QComboBox QAbstractItemView {
                background-color: #fffaf4; color: #58493c;
                selection-background-color: #ede1d4; outline: none;
            }
        """)
        self._quality_combo.currentTextChanged.connect(self._on_quality_change)
        self._quality_combo.hide()
        timeline.addWidget(self._quality_combo)

        # -- more --
        self._more_btn = QPushButton("\u5176\u4ED6\u529F\u80FD")
        self._more_btn.setFixedSize(72, 26)
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
            "QPushButton { background: rgba(255, 255, 255, 205); border: 1px solid rgba(210, 205, 200, 170); "
            "border-radius: 3px; font-size: 13px; padding: 1px; }"
            "QPushButton:hover { background-color: #d9c8b7; }"
        )
        fs_btn.clicked.connect(lambda: self.fullscreen_toggled.emit())
        layout.addWidget(fs_btn)

    # ================================================================
    #  event filter (volume popup)
    # ================================================================
    def eventFilter(self, obj, event):
        if obj is getattr(self, "_time_label", None) and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self._time_editor.setText(format_timecode(self._position))
                self._time_editor.setStyleSheet("")
                self._time_stack.setCurrentWidget(self._time_editor)
                self._time_editor.setFocus()
                self._time_editor.selectAll()
                return True
        if obj is getattr(self, "_time_editor", None):
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._cancel_time()
                return True
            if event.type() == QEvent.FocusOut:
                self._cancel_time()
        if obj == getattr(self, "_seek_bar", None) and event.type() == QEvent.MouseButtonPress:
            # Check if clicking on handle (allow drag) or track (click-to-seek)
            pos_x = event.position().x()
            opt = QStyleOptionSlider()
            self._seek_bar.initStyleOption(opt)
            handle_rect = self._seek_bar.style().subControlRect(
                QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self._seek_bar)
            margin = 8  # px tolerance around handle for drag
            handle_rect = handle_rect.adjusted(-margin, -margin, margin, margin)
            if handle_rect.contains(int(pos_x), handle_rect.center().y()):
                # Click near handle - let slider handle dragging natively
                return False
            # Click on track - do click-to-seek
            if self._duration > 0:
                val = QStyle.sliderValueFromPosition(
                    self._seek_bar.minimum(), self._seek_bar.maximum(),
                    int(pos_x), self._seek_bar.width())
                self._seek_bar.setValue(val)
                pos = val / 1000.0 * self._duration
                self.seek_requested.emit(pos)
            return True
        if hasattr(self, '_vol_btn') and obj == self._vol_btn:
            if event.type() == QEvent.Enter:
                if not self._vol_popup.isVisible():
                    self._show_vol_popup()
                self._vol_hide_timer.start(500)
            return False
        if hasattr(self, "_vol_popup") and obj == self._vol_popup:
            if event.type() == QEvent.Enter:
                self._vol_hide_timer.stop()
            elif event.type() == QEvent.Leave:
                self._vol_hide_timer.start(500)
        return super().eventFilter(obj, event)

    @property
    def is_editing_time(self):
        return self._time_stack.currentWidget() is self._time_editor

    def _cancel_time(self):
        self._time_stack.setCurrentWidget(self._time_label)
        QToolTip.hideText()

    def _submit_time(self):
        try:
            position = parse_timecode(self._time_editor.text(), self._duration)
        except ValueError as exc:
            self._time_editor.setStyleSheet("border: 1px solid #f44336;")
            QToolTip.showText(self._time_editor.mapToGlobal(QPoint(0, 0)), str(exc), self._time_editor)
            self._time_editor.selectAll()
            return
        self._cancel_time()
        self.seek_requested.emit(position)

    def _show_vol_popup(self):
        pos = self._vol_btn.mapToGlobal(QPoint(0, 0))
        self._vol_popup.move(pos.x(), pos.y() - self._vol_popup.height())
        self._vol_popup.show()

    def _vol_hide_check(self):
        gpos = self.mapFromGlobal(QCursor.pos()) if hasattr(self, 'mapFromGlobal') else QCursor.pos()
        in_btn = self._vol_btn.rect().contains(self._vol_btn.mapFromGlobal(QCursor.pos()))
        in_popup = self._vol_popup.isVisible() and self._vol_popup.rect().contains(self._vol_popup.mapFromGlobal(QCursor.pos()))
        if not in_btn and not in_popup:
            self._vol_popup.hide()
            self._vol_hide_timer.stop()

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
        dlg = QDialog(self.parentWidget() or self.window())
        dlg.setWindowTitle("URL\u6253\u5F00\u89C6\u9891")
        dlg.setMinimumSize(480, 210)
        dlg.setStyleSheet(
            "QDialog { background-color: #f8f5f1; color: #58493c; }"
            "QLabel { color: #675548; }"
        )
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)
        lay.addWidget(QLabel("\u8F93\u5165\u89C6\u9891\u7F51\u5740\uFF08\u652F\u6301B\u7AD9\u3001YouTube\u7B49\uFF09\uFF1A"))
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://...")
        url_input.setStyleSheet(
            "QLineEdit { background-color: #fffaf4; color: #58493c; "
            "border: 1px solid #d9c8b7; border-radius: 3px; padding: 6px 8px; }"
        )
        lay.addWidget(url_input)
        login_hint = QLabel("在其他功能中登录bilibili账号以获取更高的B站视频清晰度")
        login_hint.setStyleSheet("color: #927b66; font-size: 11px;")
        lay.addWidget(login_hint)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(
            "QPushButton { padding: 4px 16px; }"
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and url_input.text().strip():
            self.url_submitted.emit(url_input.text().strip())


    def _on_danmaku(self):
        msg = self._danmaku_input.text().strip()
        if msg:
            self.danmaku_sent.emit(msg)
            self._danmaku_input.clear()
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
        # valueChanged emits once and records the last nonzero volume.
        self._vol_slider_v.setValue(self._vol_before_mute if self._muted else 0)

    def _update_vol_icon(self, vol):
        if vol > 0:
            self._vol_before_mute = vol
        if vol == 0:
            self._vol_btn.setText("\U0001F507")
            self._muted = True
        elif vol < 40:
            self._vol_btn.setText("\U0001F508")
            self._muted = False
        else:
            self._vol_btn.setText("\U0001F50A")
            self._muted = False
        self._vol_btn.setToolTip("点击恢复音量: {}".format(self._vol_before_mute) if vol == 0
                                else "音量: {}，点击静音".format(vol))

    # ================================================================
    #  more menu rebuild
    # ================================================================
    def _rebuild_more_menu(self):
        self._more_menu.clear()


        # Bilibili login
        bili_text = "登录bilibili"
        if self._bili_logged_in:
            bili_text += " (已登录)"
        self._more_menu.addAction(bili_text, self._on_bili_menu)
        self._more_menu.addSeparator()
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
            self._quality_list = list(qualities.values()) if isinstance(qualities, dict) else list(qualities)
            self._current_quality = label
            if isinstance(qualities, dict):
                for qn, description in qualities.items():
                    self._quality_combo.addItem(description, str(qn))
            else:
                self._quality_combo.addItems(qualities)
            idx = self._quality_combo.findText(label)
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
        self.quality_selected.emit(self._quality_combo.currentData() or text)

    def set_quality_busy(self, busy):
        self._quality_combo.setEnabled(not busy)

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
        self._position = pos
        if not self._dragging_seek and duration > 0:
            self._seek_bar.blockSignals(True)
            self._seek_bar.setValue(int(pos / duration * 1000))
            self._seek_bar.blockSignals(False)
        self._time_label.setText(format_timecode(pos) + " / " + format_timecode(duration))
        self._time_stack.setFixedWidth(155 if max(pos, duration) >= 3600 else 115)


    # ================================================================
    #  bilibili login dialog
    # ================================================================
    def set_bili_status(self, logged_in, uname=""):
        self._bili_logged_in = logged_in
        self._bili_uname = uname
        self._rebuild_more_menu()

    def _on_bili_menu(self):
        dlg = QDialog(self.parentWidget() or self.window())
        dlg.setWindowTitle("bilibili登录")
        dlg.setFixedSize(300, 250)
        dlg.setStyleSheet("QDialog { background-color: #f8f5f1; }")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        # Logo
        logo = QLabel()
        if _os.path.exists(_BILI_LOGO):
            pm = QPixmap(_BILI_LOGO)
            logo.setPixmap(pm.scaledToWidth(160, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        # Status label
        status_text = "已登录: " + self._bili_uname if self._bili_logged_in else "未登录"
        status_label = QLabel(status_text)
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: #927b66; font-size: 12px;")
        lay.addWidget(status_label)
        lay.addStretch()
        # Buttons
        if self._bili_logged_in:
            logout_btn = QPushButton("退出登录")
            logout_btn.setStyleSheet("QPushButton { background-color: #c0392b; color: #fff; border-radius: 3px; padding: 6px 16px; font-size: 12px; } QPushButton:hover { background-color: #e74c3c; }")
            logout_btn.clicked.connect(lambda: (self.bili_logout_requested.emit(), dlg.accept()))
            lay.addWidget(logout_btn)
        else:
            login_btn = QPushButton("登录")
            login_btn.setStyleSheet("QPushButton { background-color: #FB7299; color: #fff; border-radius: 3px; padding: 6px 16px; font-size: 12px; } QPushButton:hover { background-color: #FC8EAC; }")
            login_btn.clicked.connect(lambda: (self.bili_login_requested.emit(), dlg.accept()))
            lay.addWidget(login_btn)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("QPushButton { background-color: #ede1d4; color: #675548; border-radius: 3px; padding: 6px 16px; font-size: 12px; } QPushButton:hover { background-color: #d9c8b7; }")
        close_btn.clicked.connect(dlg.reject)
        lay.addWidget(close_btn)
        dlg.exec()

    def set_volume(self, vol: int):
        self._vol_slider_v.blockSignals(True)
        self._vol_slider_v.setValue(vol)
        self._vol_slider_v.blockSignals(False)
        self._update_vol_icon(vol)
