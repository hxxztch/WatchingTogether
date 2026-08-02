"""Room panel UI - create and join watching rooms."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QListWidget, QStackedWidget, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from app.config import load as _cfg_load, save as _cfg_save
import os as _os, sys as _sys

if getattr(_sys, 'frozen', False):
    _BASE = _sys._MEIPASS
else:
    _BASE = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

_IMG_PATH = _os.path.join(_BASE, "assets", "img.png")


class RoomPanel(QWidget):
    """Side panel for room management."""

    create_requested = Signal(str)
    join_requested = Signal(str, str)
    leave_requested = Signal()
    chat_message = Signal(str)
    refresh_connection = Signal(str)
    bili_login_requested = Signal()
    bili_logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self._setup_ui()
        self._in_room = False
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("超时空会夜机")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("panel_title")
        layout.addWidget(title)

        # -- B站 account section --
        bili_section = QWidget()
        bili_section.setStyleSheet("background-color: #1a1a1a; border-bottom: 1px solid #333;")
        bli = QHBoxLayout(bili_section)
        bli.setContentsMargins(8, 6, 8, 6)
        bili_logo = QLabel("★")
        bili_logo.setStyleSheet("color: #FB7299; font-weight: bold; font-size: 14px;")
        bili_logo.setFixedWidth(24)
        bli.addWidget(bili_logo)
        bili_title = QLabel("小站账号登录")
        bili_title.setStyleSheet("color: #aaa; font-size: 11px;")
        bli.addWidget(bili_title)
        bli.addStretch()
        self._bili_status = QLabel("未登录")
        self._bili_status.setStyleSheet("color: #888; font-size: 11px;")
        bli.addWidget(self._bili_status)
        self._bili_login_btn = QPushButton("登录")
        self._bili_login_btn.setFixedSize(44, 22)
        self._bili_login_btn.setStyleSheet("QPushButton { background-color: #FB7299; color: #fff; border-radius: 3px; font-size: 11px; } QPushButton:hover { background-color: #FC8EAC; }")
        self._bili_login_btn.clicked.connect(self._on_bili_login)
        bli.addWidget(self._bili_login_btn)
        self._bili_logout_btn = QPushButton("退出")
        self._bili_logout_btn.setFixedSize(44, 22)
        self._bili_logout_btn.setStyleSheet("QPushButton { background-color: #555; color: #ccc; border-radius: 3px; font-size: 11px; } QPushButton:hover { background-color: #777; }")
        self._bili_logout_btn.clicked.connect(self._on_bili_logout)
        self._bili_logout_btn.hide()
        bli.addWidget(self._bili_logout_btn)
        layout.addWidget(bili_section)


        server_label = QLabel("服务器:")
        layout.addWidget(server_label)
        self._server_input = QLineEdit()
        self._server_input.setPlaceholderText("ws://localhost:9877")
        layout.addWidget(self._server_input)
        self._server_input.textChanged.connect(self._on_server_changed)
        self._server_input.editingFinished.connect(self._on_server_edited)

        self._current_server = QLabel("当前服务器: -")
        self._current_server.setObjectName("current_server_label")
        self._current_server.setWordWrap(True)
        layout.addWidget(self._current_server)

        refresh_btn = QPushButton("刷新连接")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        refresh_btn.setObjectName("refresh_btn")
        layout.addWidget(refresh_btn)

        layout.addSpacing(4)

        self._stack = QStackedWidget()

        no_room = QWidget()
        nr_layout = QVBoxLayout(no_room)
        nr_layout.setSpacing(8)
        # Decorative image above nickname label
        if _os.path.exists(_IMG_PATH):
            img_label = QLabel()
            pixmap = QPixmap(_IMG_PATH)
            scaled = pixmap.scaledToWidth(236, Qt.SmoothTransformation)
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            nr_layout.addWidget(img_label)
        else:
            nr_layout.addStretch()

        nr_layout.addWidget(QLabel("你的昵称:"))

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("你的昵称")
        self._name_input.setMaxLength(16)
        nr_layout.addWidget(self._name_input)
        self._name_input.textChanged.connect(self._on_name_changed)
        create_btn = QPushButton("创建房间")
        create_btn.clicked.connect(self._on_create)
        create_btn.setObjectName("create_btn")
        nr_layout.addWidget(create_btn)
        nr_layout.addWidget(QLabel("-- 或 --"))
        join_row = QHBoxLayout()
        self._room_input = QLineEdit()
        self._room_input.setPlaceholderText("例如 1234")
        self._room_input.setMaxLength(4)
        join_row.addWidget(self._room_input)
        join_btn = QPushButton("加入")
        join_btn.clicked.connect(self._on_join)
        join_btn.setObjectName("join_btn")
        join_row.addWidget(join_btn)
        nr_layout.addLayout(join_row)
        nr_layout.addStretch()
        self._stack.addWidget(no_room)

        in_room = QWidget()
        ir_layout = QVBoxLayout(in_room)
        ir_layout.setSpacing(8)
        self._room_label = QLabel()
        self._room_label.setObjectName("room_label")
        ir_layout.addWidget(self._room_label)
        ir_layout.addWidget(QLabel("成员:"))
        self._member_list = QListWidget()
        self._member_list.setWordWrap(True)
        self._member_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._member_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._member_list.setMaximumHeight(120)
        ir_layout.addWidget(self._member_list)
        leave_btn = QPushButton("离开房间")
        leave_btn.clicked.connect(self._on_leave)
        leave_btn.setObjectName("leave_btn")
        ir_layout.addWidget(leave_btn)
        ir_layout.addWidget(QLabel("聊天:"))
        self._chat_list = QListWidget()
        self._chat_list.setWordWrap(True)
        self._chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._chat_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ir_layout.addWidget(self._chat_list)
        chat_row = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入消息...")
        self._chat_input.returnPressed.connect(self._on_send_chat)
        chat_row.addWidget(self._chat_input)
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._on_send_chat)
        send_btn.setObjectName("send_btn")
        chat_row.addWidget(send_btn)
        ir_layout.addLayout(chat_row)
        self._stack.addWidget(in_room)
        layout.addWidget(self._stack)

        self._status = QLabel("未连接")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setObjectName("status_label")
        layout.addWidget(self._status)

    def _on_refresh_clicked(self):
        self.refresh_connection.emit(self.get_server_url())

    def _on_server_edited(self):
        self.refresh_connection.emit(self.get_server_url())

    def update_server_label(self, url: str):
        self._current_server.setText(f"当前服务器: {url}")

    def _on_name_changed(self):
        self._save_config()

    def _on_server_changed(self):
        self._save_config()

    def set_bili_status(self, logged_in: bool, uname: str = ""):
        if logged_in:
            self._bili_status.setText(f"\u5df2\u767b\u5f55: {uname}")
            self._bili_login_btn.hide()
            self._bili_logout_btn.show()
        else:
            self._bili_status.setText("\u672a\u767b\u5f55")
            self._bili_login_btn.show()
            self._bili_logout_btn.hide()

    def _on_bili_login(self):
        self.bili_login_requested.emit()

    def _on_bili_logout(self):
        self.bili_logout_requested.emit()


    def _load_config(self):
        cfg = _cfg_load()
        self._server_input.setText(cfg.get("server", "ws://localhost:9877"))
        self._name_input.setText(cfg.get("nickname", ""))
        self._on_name_changed(cfg.get("nickname", ""))
        uname = cfg.get("bili_uname", "")
        self.set_bili_status(bool(uname), uname)

    def _save_config(self):
        _cfg_save(server=self._server_input.text().strip(), nickname=self._name_input.text().strip())

    def get_server_url(self) -> str:
        return self._server_input.text().strip() or "ws://localhost:9877"

    def _on_create(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入昵称！")
            return
        self._save_config()
        self.create_requested.emit(name)

    def _on_join(self):
        name = self._name_input.text().strip()
        room = self._room_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入昵称！")
            return
        if len(room) != 4 or not room.isdigit():
            QMessageBox.warning(self, "提示", "房间号必须是4位数字！")
            return
        self._save_config()
        self.join_requested.emit(room, name)

    def _on_leave(self):
        self.leave_requested.emit()

    def _on_send_chat(self):
        msg = self._chat_input.text().strip()
        if msg:
            self.chat_message.emit(msg)
            self._chat_input.clear()

    def set_in_room(self, in_room: bool, room_code: str = "", members: list = None):
        self._in_room = in_room
        if in_room:
            self._stack.setCurrentIndex(1)
            self._room_label.setText(f"Room {room_code}")
            self._member_list.clear()
            for m in (members or []):
                self._member_list.addItem(f"  {m}")
        else:
            self._stack.setCurrentIndex(0)
            self._chat_list.clear()

    def add_member(self, name: str):
        self._member_list.addItem(f"  {name}")

    def remove_member(self, name: str):
        for i in range(self._member_list.count()):
            if self._member_list.item(i).text().strip() == name:
                self._member_list.takeItem(i)
                break

    def update_members(self, members: list):
        self._member_list.clear()
        for m in members:
            self._member_list.addItem(f"  {m}")

    def add_chat(self, sender: str, msg: str):
        self._chat_list.addItem(f"[{sender}] {msg}")
        self._chat_list.scrollToBottom()

    def set_status(self, text: str, color: str = "#999"):
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def get_name(self) -> str:
        return self._name_input.text().strip()