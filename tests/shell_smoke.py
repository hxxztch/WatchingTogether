"""Native Windows Qt/mpv UI acceptance: navigation, PiP, full screen and sync."""
import asyncio
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time

os.environ['QT_QPA_PLATFORM'] = 'windows'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from websockets.asyncio.server import serve
from app.ui.main_window import MainWindow
from app.player import mpv
import app.config as config
from server import Server


def main():
    if '--logical-pointer' in sys.argv:
        # Shared interactive desktops may move the real pointer during tests.
        # This mode tests Qt behavior, not OS occlusion/hit-testing.
        from unittest.mock import patch
        pointer_position = [QPoint(0, 0)]
        def set_position(*args):
            pointer_position[0] = QPoint(args[0]) if len(args) == 1 else QPoint(*args)
        pointer_patches = [patch.object(QCursor, 'setPos', side_effect=set_position),
                           patch.object(QCursor, 'pos', side_effect=lambda: pointer_position[0]),
                           patch.object(QApplication, 'widgetAt', side_effect=lambda *args: windows[0] if windows else None)]
        for item in pointer_patches:
            item.start()
        print('Logical pointer mode: OS cursor/occlusion excluded from this run', flush=True)
    ready = queue.Queue()
    async def run_server():
        async with Server() as server:
            async with serve(server.handle, '127.0.0.1', 0) as listener:
                stop = asyncio.Event()
                ready.put((asyncio.get_running_loop(), stop, listener.sockets[0].getsockname()[1]))
                await stop.wait()
    thread = threading.Thread(target=lambda: asyncio.run(run_server()), daemon=True)
    thread.start()
    loop, stop, port = ready.get(timeout=5)
    app = QApplication([])
    exceptions = []
    def report(kind, value, tb):
        exceptions.append(value)
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = report
    def wait(predicate, timeout=10):
        end = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            assert not exceptions, repr(exceptions)
            assert time.monotonic() < end, 'Native UI condition timed out'
            time.sleep(.02)
        app.processEvents()
        assert not exceptions, repr(exceptions)
    output = ROOT / 'build' / 'ui-review'
    output.mkdir(parents=True, exist_ok=True)
    def capture(widget, filename):
        QTest.qWait(150)
        origin = widget.mapToGlobal(QPoint(0, 0))
        widget.screen().grabWindow(0, origin.x(), origin.y(), widget.width(), widget.height()).save(str(output / filename))
    def hover_controls(window):
        target = window._player.mapToGlobal(QPoint(window._player.width() // 2, window._player.height() - 24))
        QCursor.setPos(target)
        try:
            wait(lambda: window._controls.isVisible())
        except AssertionError:
            capture(window, 'hover-failure.png')
            print('Hover diagnostic:', target, QCursor.pos(), QApplication.activeWindow(),
                  QApplication.widgetAt(QCursor.pos()), window._controls_hovered(), flush=True)
            raise
    def leave_controls(window):
        QCursor.setPos(window._shell.sidebar.mapToGlobal(QPoint(20, 200)))
    windows = []
    with tempfile.TemporaryDirectory(prefix='film-shell-') as temporary:
        config.CONFIG_PATH = str(Path(temporary) / 'config.json')
        config.save(server='ws://127.0.0.1:' + str(port))
        media = Path(temporary) / 'preview.y4m'
        # A real decoded 40-second video; no browser/network/media mocks.
        width, height = 160, 160
        frame = bytes([200]) * (width * height) + bytes([128]) * (width * height // 2)
        media.write_bytes(b'YUV4MPEG2 W160 H160 F25:1 Ip A1:1 C420jpeg\n' + (b'FRAME\n' + frame) * 1000)
        try:
            host = MainWindow(legacy_autoconnect=True)
            windows.append(host)
            host.resize(1280, 800)
            host.show()
            host.activateWindow()
            QTest.qWait(200)
            assert host._shell.pages.currentIndex() == 0
            assert not host._shell.expanded
            host.grab().save(str(output / 'home-collapsed.png'))
            QTest.mouseClick(host._shell.collapse_button, Qt.LeftButton)
            assert host._shell.expanded and host._shell.sidebar.width() == 224
            host.grab().save(str(output / 'home-expanded.png'))
            QTest.mouseClick(host._shell.enter_button, Qt.LeftButton)
            wait(lambda: host._player.isVisible())
            QTest.qWait(200)
            leave_controls(host)
            wait(lambda: not host._controls.isVisible())
            hover_controls(host)
            assert host._controls.height() <= 64, 'Controls must fit on one row'
            for button in (host._controls._play_btn, host._controls._stop_btn, host._controls._vol_btn):
                assert not button.icon().isNull() and button.text() == ''
            leave_controls(host)
            QTest.qWait(650)
            assert host._controls.isVisible(), 'Controls disappeared before the delay'
            wait(lambda: not host._controls.isVisible())
            hover_controls(host)
            QTest.mouseClick(host._controls._time_label, Qt.LeftButton)
            leave_controls(host)
            QTest.qWait(2100)
            assert host._controls.isVisible(), 'Time editing was interrupted'
            QTest.keyClick(host._controls._time_editor, Qt.Key_Escape)
            wait(lambda: not host._controls.isVisible())
            hover_controls(host)
            host._controls._seek_bar.setSliderDown(True)
            leave_controls(host)
            QTest.qWait(2100)
            assert host._controls.isVisible(), 'Seek dragging was interrupted'
            host._controls._seek_bar.setSliderDown(False)
            wait(lambda: not host._controls.isVisible())
            hover_controls(host)
            host._controls._show_vol_popup()
            QCursor.setPos(host._controls._vol_popup.mapToGlobal(host._controls._vol_popup.rect().center()))
            QTest.qWait(2100)
            assert host._controls.isVisible() and host._controls._vol_popup.isVisible()
            host._controls._vol_popup.hide()
            leave_controls(host)
            wait(lambda: not host._controls.isVisible())
            hover_controls(host)
            capture(host, 'theatre-empty.png')
            host.resize(1120, 720)
            QTest.qWait(200)
            host._controls.set_video_quality('4K', {'120': '4K', '80': '1080P'})
            host._controls.set_position(3601, 7200)
            QTest.qWait(100)
            hover_controls(host)
            for button in host._controls.findChildren(QPushButton):
                if button.isVisible():
                    assert host._controls.rect().contains(button.geometry()), button.text() + ' clipped'
            capture(host, 'theatre-minimum.png')
            assert host._controls.isVisible()
            assert host._controls.testAttribute(Qt.WA_TranslucentBackground)
            assert host._controls.width() == host._player.width()
            # The transparent controls must follow the owner and hide on minimize.
            host.move(host.x() + 8, host.y() + 8)
            QTest.qWait(100)
            assert host._controls.x() == host._player.mapToGlobal(QPoint(0, 0)).x()
            host.showMinimized()
            QTest.qWait(150)
            assert not host._controls.isVisible() and not host._danmaku.isVisible()
            host.showNormal()
            QTest.qWait(150)
            hover_controls(host)
            assert host._controls.isVisible()
            host.resize(1280, 800)
            host._on_load_file(media.as_posix())
            wait(lambda: not host._player.is_loading and host._player.duration > 0)
            assert host._controls._media_title.text() == 'preview.y4m'
            assert host._controls._media_source.text() == '本地视频'
            assert not host._controls.isAncestorOf(host._controls._open_btn)
            host._controls._vol_slider_v.setValue(37)
            host._on_seek(4)
            guest = MainWindow(legacy_autoconnect=True)
            windows.append(guest)
            guest._player._player = mpv.MPV(vo='null', ao='null', keep_open='yes')
            guest._player._setup_done = True
            guest._player._player.play(str(media))
            wait(lambda: host._network._ws is not None and guest._network._ws is not None)
            host._on_create_room('host')
            wait(lambda: host._room_ready)
            guest._on_join_room(host._room_code, 'guest')
            wait(lambda: guest._room_ready and guest._player.duration > 0)
            host._on_seek(4)
            hover_controls(host)
            QTest.mouseClick(host._controls._time_label, Qt.LeftButton)
            host._controls._time_editor.setText('00:04')
            QTest.keyClick(host._controls._time_editor, Qt.Key_Return)
            wait(lambda: abs(guest._player.position - 4) < .3)
            session_before_focus = host._network._session['token']
            host._room_panel._server_input.setFocus()
            host._player.setFocus()
            QTest.qWait(100)
            assert host._network._session['token'] == session_before_focus
            host._on_toggle_play()
            wait(lambda: host._player.is_playing and guest._player.is_playing)
            hover_controls(host)
            host._shell.refresh_status()
            host._poll_video_info()
            capture(host, 'theatre-playing.png')
            # A transparent gap in the toolbar must show the decoded video,
            # rather than Qt's opaque parent background.
            point = host._controls.mapToGlobal(QPoint(host._controls.width() // 2, host._controls.height() - 2))
            color = host.screen().grabWindow(0, point.x(), point.y(), 1, 1).toImage().pixelColor(0, 0)
            assert 195 <= color.red() <= 225 and abs(color.red() - color.blue()) < 5, color.name()
            leave_controls(host)
            wait(lambda: not host._controls.isVisible())
            capture(host, 'theatre-hidden.png')
            player_object = host._player._player
            native_id = host._player.winId()
            token = host._network._session['token']
            position = host._player.position
            QTest.mouseClick(host._shell.nav_buttons[0], Qt.LeftButton)
            wait(lambda: host._pip.isVisible())
            assert not host._controls.isVisible()
            assert host._player._player is player_object
            assert host._player.winId() == native_id, 'Native mpv render target changed'
            assert host._network._session['token'] == token
            assert host._player.volume == 37
            wait(lambda: host._player.position > position + .5)
            assert abs(host._player.position - guest._player.position) < .5
            host.grab().save(str(output / 'home-while-playing.png'))
            QTest.qWait(300)
            origin = host._pip.mapToGlobal(QPoint(0, 0))
            host._pip.screen().grabWindow(0, origin.x(), origin.y(), host._pip.width(), host._pip.height()).save(str(output / 'mini-player.png'))
            QTest.mouseClick(host._pip.mute, Qt.LeftButton)
            assert host._player.volume == 0
            QTest.mouseClick(host._pip.mute, Qt.LeftButton)
            assert host._player.volume == 37
            QTest.mouseClick(host._pip.play, Qt.LeftButton)
            wait(lambda: not host._player.is_playing and not guest._player.is_playing)
            old_position = host._player.position
            QTest.keyClick(host._player, Qt.Key_Right)
            wait(lambda: abs(guest._player.position - old_position - 5) < .3)
            assert abs(host._player.position - guest._player.position) < .3
            QTest.mouseClick(host._pip.restore, Qt.LeftButton)
            wait(lambda: not host._pip.isVisible())
            assert host._shell.pages.currentIndex() == 1
            assert host._player.parentWidget() is host._player_container
            assert host._player._player is player_object and host._player.winId() == native_id
            # Paused navigation doesn't pop out, Home keyboard doesn't seek.
            QTest.mouseClick(host._shell.nav_buttons[0], Qt.LeftButton)
            assert not host._pip.isVisible()
            pos = host._player.position
            QTest.keyClick(host._shell.nav_buttons[0], Qt.Key_Right)
            QTest.qWait(100)
            assert abs(host._player.position - pos) < .1
            host._switch_page(1)
            host.showMaximized()
            QTest.qWait(100)
            host._enter_fullscreen()
            QTest.qWait(150)
            assert host.isFullScreen() and not host._shell.sidebar.isVisible()
            hover_controls(host)
            leave_controls(host)
            QCursor.setPos(host._player.mapToGlobal(QPoint(50, 50)))
            wait(lambda: not host._controls.isVisible())
            host._exit_fullscreen()
            QTest.qWait(150)
            assert host.isMaximized() and host._shell.sidebar.isVisible()
            host.showNormal()
            for iteration in range(3):
                host._on_toggle_play()
                wait(lambda: host._player.is_playing and guest._player.is_playing and not host._network._pending_controls)
                host._switch_page(0)
                wait(lambda: host._pip.isVisible())
                host._pip.close()
                wait(lambda: host._shell.pages.currentIndex() == 1 and not host._pip.isVisible())
                host._on_toggle_play()
                wait(lambda: not host._player.is_playing and not guest._player.is_playing and not host._network._pending_controls)
            # Closing the owner while PiP is active also hides the child window.
            host._on_toggle_play()
            wait(lambda: host._player.is_playing and guest._player.is_playing)
            host._switch_page(0)
            assert host._pip.isVisible()
            host.close()
            assert not host._pip.isVisible()
            print('PASS: single-row vector controls, hover/delayed hide, edit/drag/volume protection, side media info, native PiP/sync/fullscreen/minimize')
        finally:
            for window in windows:
                window.close()
                window._network.stop()
                if window._player._player:
                    window._player._player.terminate()
            loop.call_soon_threadsafe(stop.set)
            thread.join(timeout=5)
    assert not exceptions
    assert not thread.is_alive()
    print('Screenshots: ' + str(output))


if __name__ == '__main__':
    main()
