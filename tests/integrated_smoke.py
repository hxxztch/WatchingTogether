"""Native Qt/mpv integrated-room acceptance. --public exercises real Quick Tunnel."""
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import logging
import gc
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'windows'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from app.ui.main_window import MainWindow
import app.config as config


def main():
    public = '--public' in sys.argv
    app = QApplication([])
    failures = []
    class AsyncErrors(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                failures.append('asyncio: ' + record.getMessage())
    logger = logging.getLogger('asyncio')
    errors_handler = AsyncErrors()
    logger.addHandler(errors_handler)
    def report(kind, value, tb):
        failures.append(kind.__name__)
        traceback.print_exception(kind, value, tb)
    sys.excepthook = report
    def wait(check, timeout=10):
        deadline = time.monotonic() + timeout
        while not check():
            app.processEvents()
            assert not failures, failures
            assert time.monotonic() < deadline, 'Integrated condition timed out'
            time.sleep(.02)
        app.processEvents()
    windows = []
    with tempfile.TemporaryDirectory(prefix='film-integrated-') as tmp:
        config.CONFIG_PATH = str(Path(tmp) / 'config.json')
        media = Path(tmp) / 'integrated.y4m'
        media.write_bytes(b'YUV4MPEG2 W160 H160 F25:1 Ip A1:1 C420jpeg\n' +
                          (b'FRAME\n' + bytes([190]) * 25600 + bytes([128]) * 12800) * 1000)
        try:
            host = MainWindow()
            guest = MainWindow()
            windows.extend((host, guest))
            host.show()
            host._switch_page(2)
            assert not host._network.isRunning(), 'Offline startup must not retry a server'
            host._room_panel.mode.setCurrentIndex(0 if public else 1)
            host._shell.profile.nickname.setText('owner')
            host._shell.profile.save_name()
            assert not hasattr(host._room_panel, '_name_input')
            assert host._room_panel._entry.isVisible(), 'Room entry must be visible'
            panel = host._room_panel
            panel.mode.setCurrentIndex(2)
            assert panel.invitation.isHidden() and panel.copy_invitation.isHidden()
            panel._server_input.setText('ws://127.0.0.1:9877')
            assert panel.get_name() == 'owner', 'Server settings must preserve profile nickname'
            panel.mode.setCurrentIndex(0 if public else 1)
            assert panel.invitation.isHidden() and panel.copy_invitation.isHidden()
            QTest.mouseClick(host._room_panel.management.findChild(QPushButton, 'create_btn'), Qt.LeftButton)
            wait(lambda: host._room_ready)
            wait(lambda: bool(host._room_panel.invitation.text()) or
                         host._rooms.tunnel is not None and host._rooms.loading is None, 70)
            invitation = host._room_panel.invitation.text()
            assert invitation, host._room_panel.tunnel_status.text()
            if public:
                from urllib.parse import urlsplit
                print('Public hostname: ' + str(urlsplit(invitation).hostname), flush=True)
            guest._on_join_room(invitation, 'viewer')
            wait(lambda: guest._room_ready, 95 if public else 35)
            wait(lambda: host._room_panel._member_list.count() == 2)
            assert host._room_panel.room_members.model().rowCount() == 2
            assert guest._room_panel.room_members.model().rowCount() == 2
            assert host._room_code in host._room_panel.room_code_label.text()
            assert guest._room_panel.invitation.text() == invitation
            assert not guest._room_panel.copy_invitation.isHidden()
            guest._room_panel.copy_invitation.click()
            assert QApplication.clipboard().text() == invitation
            for window in windows:
                panel = window._room_panel
                assert panel.room_code_label.parentWidget() is panel.members_card
                assert panel.management_status.parentWidget() is panel.members_card
                assert panel.invitation.parentWidget() is panel.management
                assert panel.copy_invitation.parentWidget() is panel.management
                assert not hasattr(panel, 'retry_tunnel')
                room_before = window._room_code
                with patch.object(QMessageBox, 'information') as prompt:
                    for name in ('create_btn', 'join_btn'):
                        button = panel.management.findChild(QPushButton, name)
                        assert button.isEnabled()
                        button.click()
                    assert prompt.call_count == 2
                    assert all(call.args[2] == '您已在房间中，请先退出' for call in prompt.call_args_list)
                assert window._room_code == room_before and window._room_ready
                assert panel.members_card.findChildren(QPushButton) == [panel.cancel_button]
                assert panel.cancel_button.text() == '离开房间'
                window._on_latency(42)
                assert '2 人' in panel.members_heading.text() and '42 ms' in panel.members_heading.text()
                window._shell.refresh_status()
                assert '42 ms' in window._shell.theatre_status.text()
            print('PASS: actual public WebSocket route' if public else 'PASS: authenticated LAN invitation', flush=True)
            generation = guest._network._generation
            token = guest._network._session['token']
            guest._network._loop.call_soon_threadsafe(guest._network._ws.transport.abort)
            wait(lambda: guest._network._generation > generation and guest._room_ready and guest._network._ready, 20)
            assert guest._network._session['token'] == token
            assert guest._my_name == 'viewer'
            print('PASS: dropped guest connection resumes the same member without suffix', flush=True)
            for window in windows:
                window._on_load_file(media.as_posix())
            wait(lambda: all(w._player.duration > 0 and not w._player.is_loading for w in windows))
            host._network.send({'type': 'pause', 'position': 10})
            wait(lambda: all(abs(w._player.position - 10) < .3 and not w._player.is_playing for w in windows))
            host._switch_page(1)
            QTest.keyClick(host._player, Qt.Key_Right)
            wait(lambda: all(abs(w._player.position - 15) < .3 for w in windows))
            QTest.keyClick(host._player, Qt.Key_Left)
            wait(lambda: all(abs(w._player.position - 10) < .3 for w in windows))
            guest._on_chat('integration-check')
            wait(lambda: any('integration-check' in host._room_panel._chat_list.item(i).text()
                             for i in range(host._room_panel._chat_list.count())))
            controls = host._controls
            controls._bar_danmaku_input.setText('bar-enter-check')
            QTest.keyClick(controls._bar_danmaku_input, Qt.Key_Return)
            controls._bar_danmaku_input.setText('bar-button-check')
            controls._bar_danmaku_btn.click()
            wait(lambda: all(any(text in guest._room_panel._chat_list.item(i).text()
                                 for i in range(guest._room_panel._chat_list.count()))
                             for text in ('bar-enter-check', 'bar-button-check')))
            assert not controls._bar_danmaku_input.text()
            host.resize(1120, 720)
            host._position_controls()
            controls.layout().activate()
            row = [controls._play_btn, controls._time_stack, controls._seek_bar,
                   controls._vol_btn, controls._bar_danmaku_input, controls._bar_danmaku_btn, controls._fs_btn]
            assert max(w.geometry().center().y() for w in row) - min(w.geometry().center().y() for w in row) <= 1
            assert all(controls.rect().contains(w.geometry()) for w in row)
            controls.show()
            controls.activateWindow()
            controls._bar_danmaku_input.setFocus()
            QTest.qWait(100)
            assert host._controls_interacting(), 'Typing must keep controls visible'
            controls._bar_danmaku_input.clearFocus()
            print('PASS: theatre latency; single-row danmaku sends by Enter/button to peer', flush=True)
            host._on_toggle_play()
            wait(lambda: all(w._player.is_playing for w in windows))
            old_player = host._player._player
            host._switch_page(2)
            wait(lambda: host._pip.isVisible())
            assert host._player._player is old_player
            # Screenshots exclude invitations/ephemeral credentials.
            host._room_panel.invitation.setText('[invitation hidden for review]')
            output = ROOT / 'build' / 'integrated-review'
            output.mkdir(parents=True, exist_ok=True)
            host.grab().save(str(output / 'rooms.png'))
            host._switch_page(1)
            QTest.qWait(250)
            host.grab().save(str(output / 'theatre.png'))
            host._on_leave_room()
            wait(lambda: not guest._room_code and not guest._network.isRunning())
            assert host._rooms.host is None and host._rooms.tunnel is None
            assert '解散' in guest._room_panel._status.text()
            assert all(w._room_panel.room_members.model().rowCount() == 0 for w in windows)
            assert all(w._room_panel.room_code_label.text() == '尚未加入房间' for w in windows)
            assert all('0 人' in w._room_panel.members_heading.text() and '—' in w._room_panel.members_heading.text() for w in windows)
            assert all(w._room_panel.invitation.isHidden() and w._room_panel.copy_invitation.isHidden() for w in windows)
            print('PASS: +/-5 sync, chat, Rooms PiP, host disband and worker cleanup', flush=True)
            # Recreate and cancel while startup is pending: no late signals revive a room.
            host._room_panel.mode.setCurrentIndex(1)
            host._on_create_room('owner')
            host._rooms.cancel()
            QTest.qWait(250)
            assert host._rooms.host is None and not host._room_code
            print('PASS: cancel during startup', flush=True)
        finally:
            for window in windows:
                window.close()
                if window._player._player:
                    window._player._player.terminate()
            app.processEvents()
            gc.collect()
    assert not failures
    logger.removeHandler(errors_handler)


if __name__ == '__main__':
    main()
