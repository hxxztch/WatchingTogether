"""Optional Quick Tunnel, owned by the desktop app and started only by the host."""
import hashlib
import re
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QTimer, Signal

CLOUDFLARED_SHA256 = '4d2490e74082c5d48dbfedaf92576fa5bd1702379ab88eb7faa0cfbe8dc891b6'


class PublicTunnel(QObject):
    ready = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self._temp = None
        self._buffer = ''
        self._url = ''
        self._registered = False
        self._announced = False
        self._stopping = False
        self._job = None
        self.process.started.connect(self._own_process)

    def start(self, port):
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        executable = root / 'tools' / 'cloudflared.exe'
        try:
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            if digest != CLOUDFLARED_SHA256:
                raise ValueError('checksum')
        except (OSError, ValueError):
            self.failed.emit('内置连接组件缺失或校验失败，请使用完整安装包；仍可使用局域网或原服务器方式。')
            return
        self._temp = tempfile.TemporaryDirectory(prefix='film-tunnel-')
        config = Path(self._temp.name) / 'config.yml'
        config.write_text('{}\n', encoding='utf-8')
        self.process.setProgram(str(executable))
        self.process.setWorkingDirectory(self._temp.name)
        self.process.setArguments(['tunnel', '--config', str(config), '--no-autoupdate',
                                   '--protocol', 'http2', '--metrics', '127.0.0.1:0',
                                   '--url', 'http://127.0.0.1:' + str(port)])
        self.process.start()
        self.timer.start(60000)

    def _own_process(self):
        if sys.platform == 'win32':
            from app.windows_job import own_process
            try:
                self._job = own_process(int(self.process.processId()))
            except OSError:
                self.failed.emit('无法安全管理连接组件，已停止异地连接；可使用局域网或原服务器方式。')
                self.stop()

    def _read(self):
        self._buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        lines = self._buffer.split('\n')
        self._buffer = lines.pop()[-4096:]
        for line in lines:
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b', line)
            if match:
                self._url = match.group().replace('https://', 'wss://', 1)
            if 'Registered tunnel connection' in line:
                self._registered = True
            if self._announced and ('Retrying connection' in line or 'connection terminated' in line):
                self.status.emit('公共通道中断，组件正在重连；局域网连接不受影响。')
            if self._announced and 'Registered tunnel connection' in line:
                self.status.emit('公共通道已连接')
        if self._url and self._registered and not self._announced and not self._stopping:
            self._announced = True
            self.timer.stop()
            self.ready.emit(self._url)

    def _timeout(self):
        self.failed.emit('公共通道连接超时。请重试，或使用局域网 / 原服务器连接。')
        self.stop()

    def _error(self, error):
        if not self._stopping and error == QProcess.FailedToStart:
            self.timer.stop()
            self.failed.emit('连接组件无法启动，请检查完整安装包。')

    def _finished(self, *args):
        self.timer.stop()
        if not self._stopping:
            self.failed.emit('公共通道已停止，请重新创建邀请或使用原服务器连接。')
        self._cleanup()

    def _cleanup(self):
        if self._job is not None:
            from app.windows_job import close_job
            close_job(self._job)
            self._job = None
        if self._temp:
            self._temp.cleanup()
            self._temp = None

    def stop(self):
        self._stopping = True
        self.timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(2000)
        self._cleanup()
