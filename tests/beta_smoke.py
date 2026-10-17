"""Profile/title/subtitle/modal regressions with real Qt and libmpv."""
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'windows'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from app.player import mpv
from app.ui.main_window import MainWindow
import app.config as config


class ControlledTunnel(QObject):
    ready = Signal(str)
    failed = Signal(str)
    status = Signal(str)
    def start(self, port):
        self.port = port
    def stop(self):
        pass


def main():
    app = QApplication([])
    errors = []
    def report(kind, value, tb):
        errors.append(kind.__name__)
        traceback.print_exception(kind, value, tb)
    sys.excepthook = report
    def wait(check, timeout=10):
        end = time.monotonic() + timeout
        while not check():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < end, 'Beta acceptance timed out'
            time.sleep(.02)
        app.processEvents()
    original_init = mpv.MPV.__init__
    def null_init(self, *args, **kwargs):
        kwargs.pop('wid', None)
        kwargs.update(vo='null', ao='null', hwdec='no')
        original_init(self, *args, **kwargs)
    output = ROOT / 'build/beta-review'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='film-beta-') as tmp, patch.object(mpv.MPV, '__init__', null_init):
        config.CONFIG_PATH = str(Path(tmp) / 'config.json')
        window = MainWindow()
        try:
            window.show()
            window.resize(1120, 720)
            window._switch_page(3)
            profile = window._shell.profile
            profile.nickname.setText('NewName')
            profile.save_button.click()
            assert config.load()['nickname'] == window._room_panel.get_name() == 'NewName'
            window._my_name = 'ExistingRoomName'
            profile.nickname.setText('NextName')
            profile.save_name()
            assert window._my_name == 'ExistingRoomName'
            # Focus loss saves without clicking Save; invalid drafts must never
            # silently create/join using the previously saved identity.
            window.activateWindow()
            profile.nickname.setFocus()
            QTest.qWait(100)
            profile.nickname.setText('AutoSaved')
            profile.save_button.setFocus()
            QTest.qWait(100)
            assert config.load()['nickname'] == 'AutoSaved'
            panel = window._room_panel
            creates, joins = [], []
            def record_create(name):
                creates.append(name)
            panel.create_requested.connect(record_create)
            def record_join(room, name):
                joins.append((room, name))
            panel.join_requested.connect(record_join)
            panel.create_requested.disconnect(window._on_create_room)
            panel.join_requested.disconnect(window._on_join_room)
            try:
                for blank in ('', '   ', '\u3000'):
                    profile.nickname.setText(blank)
                    assert profile.feedback.text()
                    for mode in range(3):
                        panel.mode.setCurrentIndex(mode)
                        panel._room_input.setText('1234')
                        with patch.object(QMessageBox, 'warning') as warning:
                            panel._on_create()
                            panel._on_join()
                            assert warning.call_count == 2
                    assert config.load()['nickname'] == ''
                assert not creates and not joins
                profile.nickname.setText('NextName')
                with patch('app.ui.profile.save', return_value=False), patch.object(QMessageBox, 'warning'):
                    panel._on_create()
                    panel._on_join()
                    assert not creates and not joins
                panel._on_create()
                panel._on_join()
                assert creates == ['NextName'] and joins == [('1234', 'NextName')]
                assert config.load()['nickname'] == 'NextName'
            finally:
                panel.create_requested.disconnect(record_create)
                panel.join_requested.disconnect(record_join)
                panel.create_requested.connect(window._on_create_room)
                panel.join_requested.connect(window._on_join_room)
                panel.mode.setCurrentIndex(0)
            print('PASS: nickname focus-loss save; all room modes reject blank/whitespace and failed saves', flush=True)
            window._controls.set_bili_status(True, '测试账户')
            assert '测试账户' in profile.account.text() and profile.logout.isVisible()
            profile.logout.click()
            assert not window._controls._bili_logged_in and profile.login.isVisible()
            assert config.load()['bili_cookie'] == ''
            window.grab().save(str(output / 'profile.png'))
            window._switch_page(1)
            long_title = '【MMD】形而上のライブ：エントフィールト ディフォロス [INTEGRALACTIA] 【4K】' * 5
            window._controls.set_media_title(long_title)
            QTest.qWait(200)
            title = window._controls._media_title
            lines = title.display_lines()
            assert title.text() == long_title and len(lines) == 2 and lines[-1].endswith('…'), lines
            assert title.height() >= title.fontMetrics().lineSpacing() * 2
            assert all(title.fontMetrics().horizontalAdvance(line) <= title.width() for line in lines)
            for mixed in ('🎬✨中文字幕🌙日本語' * 40, 'abcdefghijk' * 80):
                title.setText(mixed)
                assert all(title.fontMetrics().horizontalAdvance(line) <= title.width() for line in title.display_lines())
            title.setText(long_title)
            for size in (12, 18, 24):
                font = title.font()
                font.setPointSize(size)
                title.setFont(font)
                assert title.height() >= title.fontMetrics().lineSpacing() * 2
            title.setStyleSheet('font-size: 15px; font-weight: 600; color: #3d4145;')
            media = Path(tmp) / 'local.y4m'
            media.write_bytes(b'YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n' +
                              (b'FRAME\n' + bytes([128]) * 384) * 1000)
            window._on_load_file(media.as_posix())
            wait(lambda: window._player.duration > 0 and not window._player.is_loading)
            window._player.pause()
            subtitles = []
            for index in range(2):
                subtitle = Path(tmp) / ('manual-' + str(index) + '.srt')
                subtitle.write_text('1\n00:00:00,000 --> 00:00:30,000\nExternal subtitle ' + str(index) + '\n', encoding='utf-8')
                subtitles.append(subtitle)
                with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(subtitle), '')):
                    window._controls._subtitle_btn.click()
            assert len(window._player._subtitle_history) == 2
            assert len([t for t in window._player._player.track_list if t.get('type') == 'sub']) == 2
            window._controls._subtitle_undo.click()
            assert len(window._player._subtitle_history) == 1
            assert len([t for t in window._player._player.track_list if t.get('type') == 'sub']) == 1
            window._controls._subtitle_undo.click()
            assert not window._controls._subtitle_undo.isEnabled()
            assert not [t for t in window._player._player.track_list if t.get('type') == 'sub']
            assert all(path.is_file() for path in subtitles)
            assert not window._player.is_playing
            window._import_subtitle(str(subtitles[0]))
            window._on_load_file(media.as_posix())
            wait(lambda: not window._player.is_loading)
            assert not window._player._subtitle_history and not window._controls._subtitle_undo.isEnabled()
            window._controls.set_media_title(long_title)
            window._player.seek(10)
            wait(lambda: window._player.position >= 10)
            window._switch_page(3)
            wait(lambda: window._pip.isVisible() and window._pip.progress.value() > 0)
            assert window._pip.windowTitle().endswith('…')
            assert window._pip.toolTip() == long_title
            assert '/ 00:40' in window._pip.time_label.text(), window._pip.time_label.text()
            window._pip.resize(360, 240)
            QTest.qWait(100)
            assert window._pip.fontMetrics().horizontalAdvance(window._pip.windowTitle()) <= 180
            window._pip.grab().save(str(output / 'mini-title-progress.png'))
            window._switch_page(1)
            window.grab().save(str(output / 'long-title-subtitles.png'))
            print('PASS: profile nickname/login state; complete title lines and ellipsis; mini title/progress; real subtitle add/undo', flush=True)
            window._switch_page(2)
            with patch('app.room_controller.PublicTunnel', ControlledTunnel):
                window._room_panel.mode.setCurrentIndex(0)
                window._on_create_room('host')
                wait(lambda: window._rooms.tunnel is not None)
                dialog = window._rooms.loading
                assert QApplication.activeModalWidget() is dialog and dialog.isModal()
                angle = dialog.spinner.angle
                QTest.qWait(180)
                assert angle != dialog.spinner.angle
                old_page = window._shell.pages.currentIndex()
                QTest.keyClick(dialog, Qt.Key_Right)
                assert window._shell.pages.currentIndex() == old_page
                dialog.grab().save(str(output / 'loading.png'))
                window._rooms.tunnel.ready.emit('wss://test.trycloudflare.com')
                wait(lambda: window._rooms.loading is None)
                assert QApplication.activeModalWidget() is None
                window._rooms.retry_tunnel()
                assert window._rooms.loading is not None
                window._rooms.tunnel.failed.emit('controlled failure')
                wait(lambda: window._rooms.loading is None)
                window._rooms.retry_tunnel()
                window._rooms.loading.cancel_button.click()
                assert window._rooms.loading is None and window._rooms.host is None
                assert QApplication.activeModalWidget() is None
                window._on_create_room('host')
                wait(lambda: window._rooms.loading is not None)
                QTest.keyClick(window._rooms.loading, Qt.Key_Escape)
                assert window._rooms.loading is None and window._rooms.host is None
            print('PASS: animated modal creation, success/failure unlock, cancellation cleans owned workers', flush=True)
        finally:
            window.close()
            if window._player._player:
                window._player._player.terminate()
    assert not errors, errors


if __name__ == '__main__':
    main()
