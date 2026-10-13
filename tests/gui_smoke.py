"""Run separately: hidden Qt windows, real network workers, and mpv null output."""
import asyncio
import faulthandler
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime import configure_runtime
configure_runtime()

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from websockets.asyncio.server import serve
import app.config as config
from app.ui.main_window import MainWindow
from app.player import mpv
from server import Server


def main():
    faulthandler.dump_traceback_later(20, exit=True)
    ready = queue.Queue()

    async def serve_test():
        async with Server() as server:
            async with serve(server.handle, "127.0.0.1", 0, close_timeout=0.2) as listener:
                stop = asyncio.Event()
                ready.put((asyncio.get_running_loop(), server, stop,
                           listener.sockets[0].getsockname()[1]))
                await stop.wait()

    thread = threading.Thread(target=lambda: asyncio.run(serve_test()), daemon=True)
    thread.start()
    loop, server, stop, port = ready.get(timeout=5)
    app = QApplication([])
    windows = []
    players = []
    exceptions = []
    original_excepthook = sys.excepthook
    def record_exception(*args):
        exceptions.append(args)
        original_excepthook(*args)
    sys.excepthook = record_exception

    def wait_for(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            if exceptions:
                raise AssertionError("Qt callback failed: " + str(exceptions[0][1]))
            if time.monotonic() > deadline:
                raise AssertionError("GUI condition timed out")
            time.sleep(0.01)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix="film-app-smoke-") as temporary:
        config.CONFIG_PATH = str(Path(temporary) / "config.json")
        Path(config.CONFIG_PATH).write_text(json.dumps({"server": f"ws://127.0.0.1:{port}"}),
                                           encoding="utf-8")
        media = Path(temporary) / "sample.y4m"
        media.write_bytes(b"YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n" +
                          (b"FRAME\n" + bytes([128]) * 384) * 500)
        try:
            for _ in range(3):
                window = MainWindow()
                windows.append(window)
                player = mpv.MPV(vo="null", ao="null", keep_open="yes", pause=True)
                players.append(player)
                window._player._player = player
                window._player._setup_done = True
                player.play(str(media))
            host, guest, third = windows
            wait_for(lambda: all(w._network._ws is not None and w._player.duration > 0 for w in windows))
            host._on_create_room("host")
            wait_for(lambda: host._room_ready)
            guest._on_join_room(host._room_code, "guest")
            wait_for(lambda: guest._room_ready)
            third._on_join_room(host._room_code, "third")
            wait_for(lambda: third._room_ready)
            host._controls.set_position(0, 20)
            QTest.mouseClick(host._controls._time_label, Qt.LeftButton)
            host._controls._time_editor.setText("00:04")
            QTest.keyClick(host._controls._time_editor, Qt.Key_Return)
            wait_for(lambda: abs(guest._player.position - 4) < 0.3)
            QTest.keyClick(host._player, Qt.Key_Right)
            wait_for(lambda: all(abs(w._player.position - 9) < .3 for w in windows))
            QTest.keyClick(guest._player, Qt.Key_Left)
            wait_for(lambda: all(abs(w._player.position - 4) < .3 for w in windows))
            # One physical press only; Qt auto-repeat must not reach mpv or sliders.
            version = server.rooms[host._room_code].version
            app.sendEvent(host._player, QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier, '', True))
            QTest.keyClick(host._controls._danmaku_input, Qt.Key_Right)
            QTest.qWait(100)
            assert server.rooms[host._room_code].version == version
            QTest.keyClick(host._player, Qt.Key_Right)
            QTest.keyClick(host._player, Qt.Key_Right)
            wait_for(lambda: all(abs(w._player.position - 14) < .3 for w in windows))
            assert server.rooms[host._room_code].version == version + 2
            host._on_seek(18)
            wait_for(lambda: all(abs(w._player.position - 18) < .3 for w in windows))
            QTest.keyClick(host._player, Qt.Key_Right)
            wait_for(lambda: server.rooms[host._room_code].position == 20)
            QTest.keyClick(host._player, Qt.Key_Left)
            wait_for(lambda: all(abs(w._player.position - 15) < .3 for w in windows))
            host._on_seek(2)
            wait_for(lambda: all(abs(w._player.position - 2) < .3 for w in windows))
            QTest.keyClick(host._player, Qt.Key_Left)
            wait_for(lambda: all(w._player.position < .3 for w in windows))
            print('PASS: three clients, each +/-5s key once, two rapid presses +10s, auto-repeat/text-input ignored')
            host._on_toggle_play()
            wait_for(lambda: guest._player.is_playing)
            old_position = server.rooms[host._room_code].snapshot()['position']
            QTest.keyClick(third._player, Qt.Key_Right)
            wait_for(lambda: all(w._player.position >= old_position + 5 for w in windows))
            assert all(w._player.is_playing for w in windows)
            assert max(w._player.position for w in windows) - min(w._player.position for w in windows) < .3
            guest._network._loop.call_soon_threadsafe(guest._network._ws.transport.abort)
            wait_for(lambda: not guest._room_ready)
            host._on_toggle_play()
            host._on_seek(0)
            wait_for(lambda: guest._room_ready)
            wait_for(lambda: not guest._player.is_playing and guest._player.position < 0.3)
            assert guest._room_code == host._room_code
            assert guest._my_name == "guest"
            guest._on_leave_room()
            wait_for(lambda: not guest._room_ready and guest._network._session is None)
            assert not exceptions, "Unexpected Qt callback exception"
            print("GUI smoke passed: create/join, typed-time room seek/play, disconnect/resume at paused zero, leave")
        finally:
            for window in windows:
                window.close()
                window._network.stop()
            for player in players:
                player.terminate()
            loop.call_soon_threadsafe(stop.set)
            thread.join(timeout=5)
    assert not exceptions, "Qt callback exception during shutdown"
    assert not thread.is_alive(), "Test server did not stop"
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
