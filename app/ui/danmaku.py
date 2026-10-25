"""Danmaku (bullet comment) overlay - transparent floating window."""
import random
from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


class DanmakuOverlay(QWidget):
    """Transparent floating window for danmaku, stays on top of the player."""

    def __init__(self, parent=None):
        # Owned tool windows are hidden with their owner on Windows. This
        # overlay also follows the independent mini player while main is minimized.
        super().__init__(None)
        self.setWindowFlags(
            
            Qt.FramelessWindowHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet("background: transparent;")
        self._labels = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)
        self._colors = [
            "#ffffff", "#ffcc00", "#00ccff", "#ff6699",
            "#66ff66", "#ff9900", "#cc66ff", "#66ccff",
        ]
        self._lane = 0
        self._target = None  # QWidget whose position we track
        self.enabled = True

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            for item in self._labels:
                item['label'].hide()
                item['label'].deleteLater()
            self._labels.clear()
            self.hide()

    def track(self, widget):
        """Track this widget's position and size on screen."""
        self._target = widget
        self._sync_position()

    def _sync_position(self):
        if self.enabled and self._target and self._target.isVisible() and not self._target.window().isMinimized():
            pos = self._target.mapToGlobal(self._target.rect().topLeft())
            self.setGeometry(pos.x(), pos.y(),
                             self._target.width(), self._target.height())
            self.show()
            self.raise_()
        else:
            self.hide()

    def show_danmaku(self, sender: str, text: str, image=None):
        if not self.enabled or not self._target or len(self._labels) >= 40:
            return
        self._sync_position()

        label = QLabel(f"{sender}: {text}", self)
        label.setTextFormat(Qt.PlainText)
        color = random.choice(self._colors)
        label.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: bold; "
            f"background: transparent; padding: 2px 0;"
        )
        font = QFont("Microsoft YaHei", 14, QFont.Bold)
        label.setFont(font)
        if image:
            from app.ui.chat_images import image_pixmap
            try:
                label.setPixmap(image_pixmap(image, 64))
            except ValueError:
                label.deleteLater()
                return
        label.adjustSize()

        w = self.width()
        h = self.height()
        if w < 100:
            w = 800
        if h < 100:
            h = 600

        y = 10 + self._lane * 72
        self._lane = (self._lane + 1) % 4
        if y + label.height() > h - 60:
            y = max(10, h - label.height() - 60)

        label.move(w, y)
        label.show()

        self._labels.append({
            "label": label,
            "x": float(w),
            "y": y,
            "speed": random.uniform(1.5, 3.5),
        })

    def _tick(self):
        self._sync_position()
        to_remove = []
        for item in self._labels:
            item["x"] -= item["speed"]
            lbl = item["label"]
            lbl.move(int(item["x"]), item["y"])
            if item["x"] < -lbl.width():
                to_remove.append(item)
        for item in to_remove:
            item["label"].deleteLater()
            self._labels.remove(item)
