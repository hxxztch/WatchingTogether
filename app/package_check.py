"""Opt-in standalone-package diagnostics, using temporary config and hidden windows."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback


def run(report_path, server_url):
    result = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'checks': []}
    windows = []
    original_init = None
    try:
        import certifi
        import segno
        import brotli
        import Cryptodome.Cipher.AES
        import yt_dlp
        from yt_dlp.extractor import gen_extractor_classes
        from PySide6.QtCore import Qt, QEvent
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        from app.player import mpv
        from app.ui.main_window import MainWindow
        from app.bili_login import LoginSession
        from app.version import CLIENT_VERSION
        import app.config as config
        result['version'] = CLIENT_VERSION
        assert Path(certifi.where()).is_file()
        assert len(gen_extractor_classes()) > 100
        assert LoginSession._qr_png('https://www.bilibili.com/').startswith(b'\x89PNG')
        result['checks'].append('bundled certificate, yt-dlp extractors, crypto, brotli, QR encoder')
        app = QApplication.instance() or QApplication([])
        errors = []
        sys.excepthook = lambda kind, value, tb: errors.append(kind.__name__)
        original_init = mpv.MPV.__init__

        def null_init(self, *args, **kwargs):
            kwargs.pop('wid', None)
            kwargs.update(vo='null', ao='null', hwdec='no')
            original_init(self, *args, **kwargs)
        mpv.MPV.__init__ = null_init

        def wait_for(predicate):
            deadline = time.monotonic() + 12
            while not predicate():
                app.processEvents()
                assert not errors, errors
                if time.monotonic() > deadline:
                    raise AssertionError('Package integration check timed out')
                time.sleep(.02)
            app.processEvents()

        with tempfile.TemporaryDirectory(prefix='film-package-check-') as folder:
            config.CONFIG_PATH = str(Path(folder) / 'config.json')
            assert config.save(server=server_url)
            media = Path(folder) / '本地 视频.y4m'
            media.write_bytes(b'YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n' +
                              (b'FRAME\n' + bytes([128]) * 384) * 500)
            try:
                for _ in range(2):
                    window = MainWindow()
                    windows.append(window)
                    window._on_load_file(media.as_posix())
                wait_for(lambda: all(not w._player.is_loading and w._player.duration > 0 and
                                     w._network._ws is not None for w in windows))
                host, guest = windows
                host._player.pause()
                guest._player.pause()
                controls = host._controls
                controls._vol_slider_v.setValue(37)
                controls._on_vol_toggle()
                assert host._player.volume == 0
                controls._on_vol_toggle()
                assert host._player.volume == 37
                result['checks'].append('native Qt platform, mpv decoding, local forward-slash path, volume')
                host._on_create_room('package-host')
                wait_for(lambda: host._room_ready)
                guest._on_join_room(host._room_code, 'package-guest')
                wait_for(lambda: guest._room_ready)
                controls.set_position(0, 20)
                controls._time_editor.setText('00:04')
                controls._submit_time()
                wait_for(lambda: all(abs(w._player.position - 4) < .25 for w in windows))
                app.sendEvent(host._player, QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
                wait_for(lambda: all(abs(w._player.position - 9) < .25 for w in windows))
                result['checks'].append('packaged server create/join, typed time sync, +5s key sync')
                host._on_toggle_play()
                wait_for(lambda: guest._player.is_playing)
                guest._network._loop.call_soon_threadsafe(guest._network._ws.transport.abort)
                wait_for(lambda: not guest._room_ready)
                host._on_toggle_play()
                host._on_seek(0)
                wait_for(lambda: guest._room_ready and not guest._player.is_playing and guest._player.position < .25)
                result['checks'].append('real socket disconnect/resume, paused zero')
            finally:
                for window in windows:
                    window.close()
                    if window._player._player:
                        window._player._player.terminate()
        assert not errors, errors
        result['ok'] = True
    except Exception as exc:
        result['error_type'] = type(exc).__name__
        result['traceback'] = traceback.format_exc()
    finally:
        if original_init is not None:
            mpv.MPV.__init__ = original_init
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
