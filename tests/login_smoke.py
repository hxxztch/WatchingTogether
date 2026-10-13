"""Qt responsiveness and dialog lifecycle without real account credentials."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from app.bili_login import LoginSession
from app.ui.bili_login_dialog import BiliLoginDialog
import app.config as config


class FakeAPI:
    def __init__(self):
        self.generations = 0
        self.polls = 0
        self.profile_started = threading.Event()
        self.profile_release = threading.Event()

    def generate(self):
        self.generations += 1
        if self.generations == 1:
            raise TimeoutError('synthetic request failure')
        return {'url': 'https://example.test/qr', 'qrcode_key': 'test-key'}

    def poll(self, key):
        self.polls += 1
        return {'code': 86090 if self.polls == 1 else 0}

    def complete(self, data, cancelled):
        self.profile_started.set()
        self.profile_release.wait(3)
        return {'bili_cookie': 'synthetic-value', 'bili_uid': '1', 'bili_uname': 'test'}


def main():
    app = QApplication([])
    errors, ticks = [], []
    sys.excepthook = lambda kind, value, tb: errors.append(kind.__name__)
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)

    def wait_for(predicate):
        end = time.monotonic() + 3
        while not predicate():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < end, 'Login dialog timed out'
            time.sleep(.01)
        app.processEvents()

    with tempfile.TemporaryDirectory() as directory, patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
        config.save(bili_cookie='original-synthetic-value')
        original = Path(config.CONFIG_PATH).read_bytes()
        api = FakeAPI()
        session = LoginSession(api, interval=.01, confirm_interval=.01, retry_delay=.01)
        dialog = BiliLoginDialog(session_factory=lambda: session)
        wait_for(api.profile_started.is_set)
        before = len(ticks)
        wait_for(lambda: len(ticks) >= before + 5)
        started = time.monotonic()
        dialog.reject()
        assert time.monotonic() - started < .1
        api.profile_release.set()
        session.thread.join(1)
        app.processEvents()
        assert Path(config.CONFIG_PATH).read_bytes() == original
        assert dialog.login_result is None
        print('PASS: generation retry, Qt responsive during slow profile, cancel immediate, late result not saved')

        api2 = FakeAPI()
        api2.profile_release.set()
        session2 = LoginSession(api2, interval=.01, confirm_interval=.01, retry_delay=.01)
        dialog2 = BiliLoginDialog(session_factory=lambda: session2)
        wait_for(lambda: dialog2.result() == QDialog.Accepted)
        assert config.load()['bili_uname'] == 'test'
        assert session2.cancelled.is_set()
        assert dialog2.login_result['bili_uid'] == '1'
        print('PASS: confirmed login validates and saves before accepting dialog')

        session3 = LoginSession(FakeAPI(), interval=.01, confirm_interval=.01, retry_delay=.01)
        dialog3 = BiliLoginDialog(session_factory=lambda: session3)
        dialog3.reject()
        app.processEvents()
        assert session3.thread is None
        print('PASS: closing before scheduled start creates no request')
    timer.stop()
    assert not errors, errors


if __name__ == '__main__':
    main()
