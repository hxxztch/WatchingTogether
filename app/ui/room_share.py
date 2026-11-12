"""Foreground-only clipboard detection and explicit room-switch confirmation."""
from collections import OrderedDict
from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit,
                               QPushButton, QHBoxLayout, QMessageBox)
from app.room_share import parse_share, make_share, make_legacy_invitation


class RoomShareController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.dirty = True
        self.seen = OrderedDict()
        self.dialog = None
        self.pending = None
        panel = owner._room_panel
        panel.share_requested.connect(self.copy_share)
        panel.invitation_detected.connect(self.manual)
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        QApplication.instance().applicationStateChanged.connect(self.application_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def clipboard_changed(self):
        self.dirty = True

    def application_changed(self, state):
        if state == Qt.ApplicationActive:
            self.dirty = True

    def remember(self, identity):
        self.seen[identity] = True
        while len(self.seen) > 128:
            self.seen.popitem(last=False)

    def current(self):
        owner = self.owner
        if not owner._room_code:
            return None
        link = owner._room_panel.invitation.text()
        if owner._room_panel.mode.currentIndex() == 2:
            try:
                return parse_share(make_legacy_invitation(owner._network.url, owner._room_code)).identity
            except ValueError:
                return None
        try:
            return parse_share(link).identity
        except ValueError:
            try:
                from app.hosting import make_invitation
                return parse_share(make_invitation(owner._network.url, owner._room_code)).identity
            except ValueError:
                return None

    def copy_share(self):
        owner = self.owner
        try:
            link = owner._room_panel.invitation.text()
            legacy = owner._room_panel.mode.currentIndex() == 2
            if legacy:
                link = make_legacy_invitation(owner._network.url, owner._room_code)
            invite = parse_share(link)
            p2p = getattr(owner, '_p2p', None)
            watching = '房主推流 · P2P' if p2p and p2p.active else '同步观影'
            connection = '局域网' if owner._room_panel.mode.currentIndex() == 1 else '公共通道'
            if legacy:
                connection = '原服务器 / 外部内网穿透（需可访问分享者的服务器地址）'
            text = make_share(link, owner._my_name, watching, connection)
        except ValueError:
            owner._room_panel.set_status('请等待完整邀请链接生成后再分享', '#95724f')
            return
        self.remember(invite.identity)
        QApplication.clipboard().setText(text)
        owner._room_panel.set_status('房间邀请已复制，可直接发送给朋友', '#4CAF50')

    def manual(self, text):
        try:
            self.pending = parse_share(text)
        except ValueError as exc:
            self.owner._room_panel.set_status(str(exc), '#95724f')
            return
        self.check()

    def busy(self):
        owner = self.owner
        return bool(owner._rooms.pending or owner._rooms.timer.isActive() or
                    owner._network._membership_pending or owner._network._leaving or
                    (owner._room_code and not owner._room_ready))

    def check(self):
        owner = self.owner
        if owner._closing or self.dialog or self.busy():
            return
        # Do not read the clipboard while another application/window is active.
        if QApplication.applicationState() != Qt.ApplicationActive or not owner.isActiveWindow():
            return
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            return
        invite, manual = self.pending, self.pending is not None
        if invite is None:
            if not self.dirty:
                return
            self.dirty = False
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if not mime or not mime.hasText():
                return
            try:
                invite = parse_share(clipboard.text())
            except ValueError:
                return
        self.pending = None
        if invite.identity == self.current():
            if manual:
                owner._room_panel.set_status('你已在该房间，无需重复加入', '#95724f')
            return
        if not manual and invite.identity in self.seen:
            return
        self.present(invite)

    def present(self, invite):
        owner = self.owner
        dialog = self.dialog = QDialog(owner)
        dialog.setWindowTitle('检测到房间分享信息')
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)
        def text(value):
            widget = QLabel(value)
            widget.setWordWrap(True)
            widget.setTextFormat(Qt.PlainText)
            layout.addWidget(widget)
            return widget
        text('检测到房间分享信息，是否加入该房间？')
        text('房间号：' + invite.room + '\n连接地址：' + invite.public_address)
        if invite.endpoint.startswith('ws://'):
            text('此邀请使用未加密连接；局域网邀请需要能访问房主所在网络。')
        text('房主名称和观影模式将在连接后由房间确认。')
        name = QLineEdit(owner._shell.profile.nickname.text().strip(), dialog)
        name.setMaxLength(16)
        name.setPlaceholderText('填写加入房间使用的昵称')
        name.setAccessibleName('加入昵称')
        layout.addWidget(name)
        feedback = text('')
        hosting = owner._rooms.host is not None
        previous = (owner._network, owner._room_code, owner._rooms.host)
        if hosting:
            text('加入后会解散你当前主持的房间，其他成员将离开该房间。')
            caption = '解散当前房间并加入'
        elif owner._room_code:
            text('加入后会离开你当前所在的房间。')
            caption = '离开当前房间并加入'
        else:
            caption = '加入房间'
        row = QHBoxLayout()
        cancel = QPushButton('暂不加入')
        join = QPushButton(caption)
        join.setObjectName('primary')
        row.addWidget(cancel)
        row.addWidget(join)
        layout.addLayout(row)
        cancel.clicked.connect(dialog.reject)
        def accept():
            if owner._closing or self.busy():
                feedback.setText('当前连接状态正在变化，请稍后重试。')
                return
            if previous != (owner._network, owner._room_code, owner._rooms.host):
                feedback.setText('当前房间已变化，请关闭提示后重新粘贴邀请。')
                return
            nickname = name.text().strip()
            if not nickname:
                feedback.setText('请填写昵称后再加入。')
                name.setFocus()
                return
            profile = owner._shell.profile
            profile.nickname.setText(nickname)
            if not profile.save_name():
                feedback.setText('昵称未能保存，请检查配置目录写入权限。')
                return
            self.remember(invite.identity)
            # Only the explicit button authorizes leaving/disbanding a current room.
            owner._my_name = nickname
            owner._room_panel.mode.setCurrentIndex(2 if invite.legacy else (0 if invite.endpoint.startswith('wss://') else 1))
            if invite.legacy:
                owner._room_panel._server_input.setText(invite.endpoint)
                owner._rooms.join_legacy(invite.endpoint, invite.room, nickname)
            else:
                owner._rooms.join(invite.link, nickname)
            owner._room_panel._room_input.setText(invite.link)
            owner._switch_page(2)
            dialog.accept()
        join.clicked.connect(accept)
        def finished(result):
            self.remember(invite.identity)
            self.dialog = None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.open()
        # Named fields make accessibility and focused UI verification straightforward.
        dialog.nickname = name
        dialog.join_button = join
        dialog.cancel_button = cancel
        dialog.feedback = feedback

    def stop(self):
        self.timer.stop()
        if self.dialog:
            self.dialog.reject()
