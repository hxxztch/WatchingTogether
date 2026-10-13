"""QR dialog kept responsive while its independent login session does HTTP work."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from app.bili_login import LoginSession
from app.config import save


class BiliLoginDialog(QDialog):
    def __init__(self, parent=None, session_factory=LoginSession):
        super().__init__(parent)
        self.setWindowTitle('bilibili登录')
        self.setFixedSize(360, 450)
        self.setStyleSheet('QDialog {background:#1a1a1a;} QLabel {color:#ddd;}')
        self._session_factory = session_factory
        self._session = None
        self._active = True
        self.login_result = None
        layout = QVBoxLayout(self)
        hint = QLabel('请用 bilibili APP 扫码并确认登录')
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(260, 260)
        self.qr_label.setStyleSheet('background:white; padding:8px;')
        layout.addWidget(self.qr_label)
        self.status_label = QLabel('正在生成二维码…')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status_label)
        self.retry_button = QPushButton('重新生成')
        self.retry_button.clicked.connect(self._restart)
        layout.addWidget(self.retry_button)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.finished.connect(self._finish)
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._restart)
        self._start_timer.start(0)

    def _restart(self):
        if not self._active:
            return
        if self._session:
            self._session.cancel()
        self.qr_label.clear()
        self.retry_button.setEnabled(False)
        self._session = self._session_factory()
        self._session.qr_ready.connect(self._show_qr)
        self._session.status_changed.connect(self._status)
        self._session.succeeded.connect(self._success)
        self._session.failed.connect(self._failure)
        self._session.start()

    def _is_current(self):
        return self._active and self.sender() is self._session

    def _show_qr(self, png):
        if self._is_current():
            pixmap = QPixmap()
            pixmap.loadFromData(png)
            self.qr_label.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _status(self, text):
        if self._is_current():
            self.status_label.setText(text)

    def _failure(self, text):
        if self._is_current():
            self.status_label.setText(text)
            self.retry_button.setEnabled(True)

    def _success(self, result):
        if not self._is_current():
            return
        if not save(**result):
            self.status_label.setText('登录信息保存失败，请检查目录写入权限后重试')
            self.retry_button.setEnabled(True)
            return
        self.login_result = result
        self.accept()

    def _finish(self, *_):
        self._active = False
        self._start_timer.stop()
        if self._session:
            self._session.cancel()
