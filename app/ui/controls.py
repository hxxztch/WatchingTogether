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
from app.ui.media_controls import media_icon

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
    bili_status_changed = Signal(bool, str)
    media_title_changed = Signal()
    subtitle_requested = Signal()
    subtitle_undo_requested = Signal()

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
        from app.ui.media_controls import build_controls
        build_controls(self, MENU_STYLE)

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
            self._vol_btn.setIcon(media_icon('muted'))
            self._muted = True
        elif vol < 40:
            self._vol_btn.setIcon(media_icon('volume-low'))
            self._muted = False
        else:
            self._vol_btn.setIcon(media_icon('volume'))
            self._muted = False
        self._vol_btn.setToolTip("点击恢复音量: {}".format(self._vol_before_mute) if vol == 0
                                else "音量: {}，点击静音".format(vol))

    # ================================================================
    #  more menu rebuild
    # ================================================================
    def _rebuild_more_menu(self):
        self._bili_btn.setText('bilibili · 已登录' if self._bili_logged_in else '登录 bilibili')
        self._bili_btn.setToolTip(self._bili_uname if self._bili_logged_in else '扫码登录或管理账号')
        for combo, values, empty in ((self._audio_combo, self._audio_tracks, '暂无音轨'),
                                     (self._page_combo, self._page_list, '暂无分 P')):
            selected = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for key, title in values:
                combo.addItem(title, key)
            if not values:
                combo.addItem(empty)
            index = combo.findData(selected)
            combo.setCurrentIndex(max(0, index))
            combo.setEnabled(bool(values))
            combo.blockSignals(False)

    # ================================================================
    #  public setters
    # ================================================================
    def set_audio_tracks(self, tracks, current_id=-1):
        self._audio_tracks = tracks[:] if tracks else []
        self._rebuild_more_menu()
        index = self._audio_combo.findData(current_id)
        if index >= 0:
            self._audio_combo.setCurrentIndex(index)

    def set_video_quality(self, label="", qualities=None):
        self._quality_label.setText("\u753B\u8D28: " + (label if label else "—"))
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
        index = self._page_combo.findData(current_idx)
        if index >= 0:
            self._page_combo.setCurrentIndex(index)

    # ================================================================
    #  state updates
    # ================================================================
    def set_playing(self, playing: bool):
        self._play_btn.setIcon(media_icon('pause' if playing else 'play'))
        self._play_btn.setToolTip('暂停' if playing else '播放')
        self._play_btn.setAccessibleName(self._play_btn.toolTip())

    def set_media_title(self, title, source='当前影片'):
        self._media_title.setText(str(title) or '未命名视频')
        self._media_title.setToolTip(str(title))
        self._media_source.setText(source)
        self.media_title_changed.emit()

    def set_position(self, pos: float, duration: float):
        self._duration = duration
        self._position = pos
        if not self._dragging_seek and duration > 0:
            self._seek_bar.blockSignals(True)
            self._seek_bar.setValue(int(pos / duration * 1000))
            self._seek_bar.blockSignals(False)
        self._time_label.setText(format_timecode(pos) + " / " + format_timecode(duration))
        self._time_stack.setFixedWidth(175 if max(pos, duration) >= 3600 else 125)


    # ================================================================
    #  bilibili login dialog
    # ================================================================
    def set_bili_status(self, logged_in, uname=""):
        self._bili_logged_in = logged_in
        self._bili_uname = uname
        self._rebuild_more_menu()
        self.bili_status_changed.emit(logged_in, uname)

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
