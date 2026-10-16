"""Non-blocking modal progress: the Qt loop and networking continue running."""
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QLabel, QPushButton


class Spinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.setFixedSize(QSize(44, 44))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(50)

    def advance(self):
        self.angle = (self.angle + 24) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#eadfd4'), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawEllipse(5, 5, 34, 34)
        painter.setPen(QPen(QColor('#b8754c'), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(5, 5, 34, 34, -self.angle * 16, 100 * 16)


class RoomLoadingDialog(QDialog):
    cancelled = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.setWindowTitle('正在创建异地房间')
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setFixedSize(390, 240)
        self._ending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        self.spinner = Spinner()
        layout.addWidget(self.spinner, 0, Qt.AlignCenter)
        title = QLabel('正在建立公共通道…')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        info = QLabel('请稍候，完成前其他操作暂不可用。\n最长等待 60 秒，可取消本次创建。')
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        self.cancel_button = QPushButton('取消')
        self.cancel_button.clicked.connect(self.cancelled)
        layout.addWidget(self.cancel_button)

    def reject(self):
        if not self._ending:
            self.cancelled.emit()

    def finish(self):
        self._ending = True
        self.spinner.timer.stop()
        self.done(0)
