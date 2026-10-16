"""Room lifecycle glue; playback and the existing sync protocol stay unchanged."""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
from app.hosting import EmbeddedHost, make_invitation, parse_invitation
from app.tunnel import PublicTunnel
import socket


def preferred_lan_address():
    # UDP connect only consults the local route table; no packet is sent.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.settimeout(.2)
            route.connect(('192.0.2.1', 9))
            return route.getsockname()[0]
    except OSError:
        return ''


class RoomController(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.host = None
        self.tunnel = None
        self.integrated = False
        self.pending = None
        self.name = ''
        self.endpoint = ''
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    @property
    def panel(self):
        return self.owner._room_panel

    def connect(self, url, message):
        self.pending = message
        if not self.owner._reconnect_network(url):
            self.pending = None
            return
        self.panel.set_busy(True)
        public = url.startswith('wss://')
        self.timer.start(90000 if public else 30000)
        if public:
            self.panel.set_status('正在连接异地房间；新邀请可能需要等待域名生效，最长等待 90 秒。')

    def connected(self):
        if self.pending:
            message, self.pending = self.pending, None
            self.owner._network.send(message)

    def create(self, name):
        self.cancel()
        self.name = name
        self.integrated = True
        self.panel.set_busy(True)
        self.panel.set_status('正在启动房主服务…')
        self.host = EmbeddedHost(lan=self.panel.mode.currentIndex() == 1, parent=self)
        self.host.ready.connect(self._host_ready)
        self.host.failed.connect(self._failed)
        self.host.start()

    def _host_ready(self, url, port):
        if self.sender() is not self.host:
            return
        self.connect(url, {'type': 'create_room', 'name': self.name})

    def join(self, invitation, name):
        try:
            url, room = parse_invitation(invitation)
        except ValueError as exc:
            self.panel.set_status(str(exc), '#b36b4a')
            return
        self.cancel()
        self.integrated = True
        self.connect(url, {'type': 'join_room', 'room': room, 'name': name})

    def message(self, message):
        kind = message.get('type')
        if kind in ('room_created', 'room_joined'):
            self.timer.stop()
            if self.host and kind == 'room_created':
                self.room = message['room']
                if self.host.lan:
                    addresses = []
                    for interface in QNetworkInterface.allInterfaces():
                        if not interface.flags() & QNetworkInterface.IsUp:
                            continue
                        for entry in interface.addressEntries():
                            address = entry.ip()
                            if (address.protocol() == QAbstractSocket.IPv4Protocol and
                                    not address.isLoopback() and not address.toString().startswith('169.254.')):
                                addresses.append((interface.humanReadableName(), address.toString()))
                    preferred = preferred_lan_address()
                    addresses.sort(key=lambda item: item[1] != preferred)
                    self.panel.lan_address.blockSignals(True)
                    self.panel.lan_address.clear()
                    for title, address in addresses:
                        self.panel.lan_address.addItem(title + ' · ' + address, address)
                    self.panel.lan_address.blockSignals(False)
                    self.panel.lan_address.setVisible(True)
                    self.update_lan_invitation()
                else:
                    self.retry_tunnel()
        elif kind in ('room_closed', 'session_expired'):
            if self.integrated:
                self.cancel()
            else:
                self.timer.stop()
                self.pending = None
                self.panel.set_invitation('')
        elif kind == 'error' and self.timer.isActive():
            self.cancel()

    def update_lan_invitation(self):
        if self.host and self.host.lan:
            address = self.panel.lan_address.currentData()
            if address:
                self.endpoint = 'ws://' + address + ':' + str(self.host.port) + self.host.guest_path
                self.panel.set_invitation(make_invitation(self.endpoint, self.room))
            else:
                self.panel.set_status('未找到可用局域网地址，请连接 Wi-Fi 或网线后重新创建。')

    def retry_tunnel(self):
        if not self.host or self.host.lan:
            return
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel.deleteLater()
        self.panel.set_invitation('')
        self.panel.retry_tunnel.setVisible(True)
        self.panel.retry_tunnel.setEnabled(False)
        self.panel.tunnel_status.setText('正在建立公共通道，最长等待 60 秒…')
        self.tunnel = PublicTunnel(self)
        self.tunnel.ready.connect(self._tunnel_ready)
        self.tunnel.failed.connect(self._tunnel_failed)
        self.tunnel.status.connect(self.panel.tunnel_status.setText)
        self.tunnel.start(self.host.port)

    def _tunnel_ready(self, endpoint):
        if self.sender() is not self.tunnel or not self.host:
            return
        self.endpoint = endpoint + self.host.guest_path
        self.panel.set_invitation(make_invitation(self.endpoint, self.room))
        self.panel.retry_tunnel.setEnabled(True)
        self.panel.tunnel_status.setText('公共通道已连接。临时服务可能中断；重新生成后需分享新链接。')

    def _tunnel_failed(self, text):
        if self.sender() is not self.tunnel:
            return
        self.panel.set_invitation('')
        self.panel.retry_tunnel.setEnabled(True)
        self.panel.tunnel_status.setText(text)

    def _failed(self, text):
        if self.sender() is not self.host:
            return
        self.cancel()
        self.panel.set_status(text, '#b36b4a')

    def _timeout(self):
        self.cancel()
        self.panel.set_status('连接房间超时，请检查邀请链接和网络后重试。', '#b36b4a')

    def cancel(self):
        self.timer.stop()
        self.pending = None
        if self.host:
            host, self.host = self.host, None
            host.stop()
            host.deleteLater()
        if self.tunnel:
            tunnel, self.tunnel = self.tunnel, None
            tunnel.stop()
            tunnel.deleteLater()
        if hasattr(self.owner, '_network'):
            self.owner._network.stop()
        self.integrated = False
        self.endpoint = ''
        self.panel.set_invitation('')
        self.panel.retry_tunnel.hide()
        self.panel.lan_address.hide()
        self.panel.tunnel_status.clear()
        self.panel.set_in_room(False)
        self.owner._room_code = ''
        self.owner._room_ready = False
        if hasattr(self.owner, '_player'):
            self.owner._player.set_speed(1.0)
        self.panel.set_status('已离开房间')
