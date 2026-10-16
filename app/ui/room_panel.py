"""Room panel UI - create and join watching rooms."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QListWidget, QStackedWidget, QMessageBox, QComboBox, QApplication,
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
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._setup_ui()
        self._in_room = False
        self._load_config()
        self._last_applied_server = self.get_server_url()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        self.management = QWidget()
        self.management.setObjectName('roomCard')
        self.management.setAttribute(Qt.WA_StyledBackground, True)
        self.management.setMaximumWidth(840)
        management = QVBoxLayout(self.management)
        management.setContentsMargins(24, 24, 24, 24)
        management.setSpacing(14)
        heading = QLabel('房间')
        heading.setObjectName('heading')
        management.addWidget(heading)
        explanation = QLabel('创建房间后分享邀请链接，朋友粘贴即可加入。房主退出时房间解散。\n每位成员自行打开视频，房间同步播放进度和聊天。')
        explanation.setWordWrap(True)
        management.addWidget(explanation)
        self.mode = QComboBox()
        self.mode.addItems(['异地联机 · 公共通道（试用）', '同一局域网 · 直接连接', '原服务器 / 外部内网穿透'])
        management.addWidget(self.mode)

        title = QLabel("成员与聊天")
        title.setAlignment(Qt.AlignLeft)
        title.setObjectName("panel_title")
        layout.addWidget(title)

        self._connection_toggle = QPushButton('连接设置  ▾')
        self._connection_toggle.setCheckable(True)
        self._connection_toggle.setChecked(True)
        self._connection_body = QWidget()
        connection = QVBoxLayout(self._connection_body)
        connection.setContentsMargins(0, 0, 0, 0)
        connection.setSpacing(8)
        self._connection_toggle.toggled.connect(self._connection_body.setVisible)
        management.addWidget(self._connection_toggle)
        management.addWidget(self._connection_body)
        server_label = QLabel("服务器:")
        connection.addWidget(server_label)
        self._server_input = QLineEdit()
        self._server_input.setPlaceholderText("ws://localhost:9877")
        connection.addWidget(self._server_input)
        self._server_input.textChanged.connect(self._on_server_changed)
        self._server_input.editingFinished.connect(self._on_server_edited)

        self._current_server = QLabel("当前服务器: -")
        self._current_server.setObjectName("current_server_label")
        self._current_server.setWordWrap(True)
        connection.addWidget(self._current_server)

        refresh_btn = QPushButton("刷新连接")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        refresh_btn.setObjectName("refresh_btn")
        connection.addWidget(refresh_btn)

        layout.addSpacing(4)

        self._stack = QStackedWidget()

        no_room = QWidget()
        nr_layout = QVBoxLayout(no_room)
        nr_layout.setSpacing(8)
        nr_layout.setContentsMargins(0, 12, 0, 0)

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
        self._entry = no_room
        self._stack.removeWidget(no_room)
        management.addWidget(no_room)
        no_room.show()
        self._stack.addWidget(QLabel('前往侧栏「房间」邀请朋友一起看。'))
        self.invitation = QLineEdit()
        self.invitation.setReadOnly(True)
        self.invitation.setPlaceholderText('创建成功后显示邀请链接')
        self.lan_address = QComboBox()
        self.lan_address.setToolTip('选择朋友可以连接的网卡地址；多网卡时可切换后重新复制邀请。')
        self.lan_address.hide()
        management.addWidget(self.lan_address)
        management.addWidget(self.invitation)
        self.copy_invitation = QPushButton('复制邀请链接')
        self.copy_invitation.setEnabled(False)
        self.copy_invitation.clicked.connect(lambda: QApplication.clipboard().setText(self.invitation.text()))
        management.addWidget(self.copy_invitation)
        self.retry_tunnel = QPushButton('重新生成异地邀请')
        self.retry_tunnel.hide()
        management.addWidget(self.retry_tunnel)
        self.tunnel_status = QLabel()
        self.tunnel_status.setWordWrap(True)
        self.tunnel_status.setTextFormat(Qt.PlainText)
        management.addWidget(self.tunnel_status)
        self.cancel_button = QPushButton('离开 / 取消连接')
        self.cancel_button.clicked.connect(self.cancel_requested)
        management.addWidget(self.cancel_button)
        self.management_status = QLabel('尚未加入房间')
        self.management_status.setWordWrap(True)
        self.management_status.setTextFormat(Qt.PlainText)
        management.addWidget(self.management_status)
        management.addStretch()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

        in_room = QWidget()
        ir_layout = QVBoxLayout(in_room)
        ir_layout.setContentsMargins(0, 12, 0, 0)
        ir_layout.setSpacing(8)
        self._room_label = QLabel()
        self._room_label.setObjectName("room_label")
        ir_layout.addWidget(self._room_label)
        ir_layout.addWidget(QLabel("成员:"))
        self._member_list = QListWidget()
        self._member_list.setWordWrap(True)
        self._member_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._member_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._member_list.setMaximumHeight(80)
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
        self._chat_input.setMaxLength(4000)
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
        self._status.setTextFormat(Qt.PlainText)
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setObjectName("status_label")
        layout.addWidget(self._status)

    def _on_refresh_clicked(self):
        self._last_applied_server = self.get_server_url()
        self.refresh_connection.emit(self.get_server_url())

    def _on_server_edited(self):
        # Moving focus between the translucent controls and the main window
        # must not reconnect (and leave the room) for an unchanged address.
        if self.mode.currentIndex() == 2 and self.get_server_url() != self._last_applied_server:
            self._on_refresh_clicked()

    def _mode_changed(self):
        legacy = self.mode.currentIndex() == 2
        self._connection_toggle.setVisible(legacy)
        self._connection_body.setVisible(legacy and self._connection_toggle.isChecked())
        self._room_input.setMaxLength(4 if legacy else 2048)
        self._room_input.setPlaceholderText('例如 1234' if legacy else '粘贴完整邀请链接')

    def set_invitation(self, value):
        self.invitation.setText(value)
        self.copy_invitation.setEnabled(bool(value))

    def set_busy(self, busy):
        self._entry.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self._connection_body.setEnabled(not busy)

    def update_server_label(self, url: str):
        self._current_server.setText(f"当前服务器: {url}")

    def _on_name_changed(self, text=None):
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
        self._server_input.blockSignals(True)
        self._name_input.blockSignals(True)
        self._server_input.setText(cfg.get("server", "ws://localhost:9877"))
        self._name_input.setText(cfg.get("nickname", ""))
        self._server_input.blockSignals(False)
        self._name_input.blockSignals(False)

    def _save_config(self):
        if not _cfg_save(server=self._server_input.text().strip(), nickname=self._name_input.text().strip()):
            self.set_status("配置保存失败，请检查目录写入权限", "#f44336")

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
        if self.mode.currentIndex() == 2 and (len(room) != 4 or not room.isdigit()):
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
        if in_room and not self._in_room:
            self._connection_toggle.setChecked(False)
        self._in_room = in_room
        self._entry.setVisible(not in_room)
        self.set_busy(in_room)
        if in_room:
            self._stack.setCurrentIndex(1)
            self._room_label.setText(f"Room {room_code}")
            self._member_list.clear()
            for m in (members or []):
                self._member_list.addItem(f"  {m}")
        else:
            self._stack.setCurrentIndex(0)
            self._chat_list.clear()
            self._member_list.clear()

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
        while self._chat_list.count() > 1000:
            self._chat_list.takeItem(0)
        self._chat_list.scrollToBottom()

    def set_status(self, text: str, color: str = "#999"):
        self._status.setText(text)
        self.management_status.setText(text)
        self._status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def get_name(self) -> str:
        return self._name_input.text().strip()
