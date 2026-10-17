"""Personal preferences share the existing nickname and Bilibili login state."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from app.config import load, save


class ProfilePage(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setObjectName('roomCard')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumWidth(840)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel('个人中心')
        title.setObjectName('heading')
        layout.addWidget(title)
        layout.addWidget(QLabel('房间昵称'))
        row = QHBoxLayout()
        self.nickname = QLineEdit(owner._room_panel.get_name())
        self.nickname.setMaxLength(16)
        self.nickname.setPlaceholderText('输入你的昵称')
        self.save_button = QPushButton('保存昵称')
        self.save_button.clicked.connect(self.save_name)
        self.nickname.editingFinished.connect(self.save_name)
        row.addWidget(self.nickname, 1)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        note = QLabel('离开输入框或按回车自动保存，用于下一次创建或加入房间；当前房间里的名称保持不变。')
        note.setWordWrap(True)
        note.setObjectName('subtle')
        layout.addWidget(note)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.PlainText)
        layout.addWidget(self.feedback)
        self.feedback.setWordWrap(True)
        self.nickname.textChanged.connect(self._name_edited)
        owner._room_panel.nickname_provider = self.name_for_room
        layout.addWidget(QLabel('bilibili 账号'))
        self.account = QLabel()
        self.account.setTextFormat(Qt.PlainText)
        self.account.setWordWrap(True)
        layout.addWidget(self.account)
        buttons = QHBoxLayout()
        self.login = QPushButton('扫码登录')
        self.logout = QPushButton('退出登录')
        self.login.clicked.connect(owner._on_bili_login)
        self.logout.clicked.connect(owner._on_bili_logout)
        buttons.addWidget(self.login)
        buttons.addWidget(self.logout)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        owner._controls.bili_status_changed.connect(self.set_bili_status)
        self.set_bili_status(owner._controls._bili_logged_in, owner._controls._bili_uname)

    def _name_edited(self):
        self.feedback.setText('昵称不能为空，请输入昵称。' if not self.nickname.text().strip() else '离开输入框自动保存。')

    def name_for_room(self):
        # Validate the current edit, including a failed save, rather than falling
        # back to an older persisted identity when starting a room action.
        return self.nickname.text().strip() if self.save_name() else ''

    def save_name(self):
        name = self.nickname.text().strip()
        if load().get('nickname', '') != name and not save(nickname=name):
            self.feedback.setText('保存失败，请检查配置目录的写入权限；暂时无法创建或加入房间。')
            return False
        if not name:
            self.feedback.setText('昵称不能为空，请输入昵称后再创建或加入房间。')
            return False
        self.feedback.setText('昵称已保存。')
        return True

    def set_bili_status(self, logged_in, name=''):
        self.account.setText('已登录 · ' + name if logged_in else '尚未登录')
        self.login.setVisible(not logged_in)
        self.logout.setVisible(logged_in)
