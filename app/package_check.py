"""Opt-in standalone-package diagnostics, using temporary config and hidden windows."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback


def run(report_path, server_url=None):
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
            assert config.save(server=server_url or 'ws://127.0.0.1:9877')
            media = Path(folder) / '本地 视频.y4m'
            media.write_bytes(b'YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n' +
                              (b'FRAME\n' + bytes([128]) * 384) * 500)
            try:
                for _ in range(2):
                    window = MainWindow(legacy_autoconnect=bool(server_url))
                    window._switch_page(1)
                    windows.append(window)
                    window._on_load_file(media.as_posix())
                wait_for(lambda: all(not w._player.is_loading and w._player.duration > 0 for w in windows))
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
                profile = host._shell.profile
                profile.nickname.setText('portable-profile')
                profile.save_name()
                assert config.load()['nickname'] == host._room_panel.get_name() == 'portable-profile'
                host._controls.set_media_title('Long title ' * 30)
                title = host._controls._media_title
                title.resize(240, title.height())
                assert len(title.display_lines()) == 2 and title.display_lines()[-1].endswith('…')
                subtitle = Path(folder) / 'manual.srt'
                subtitle.write_text('1\n00:00:00,000 --> 00:00:15,000\nPortable subtitle\n', encoding='utf-8')
                host._player.load_subtitle(str(subtitle))
                assert host._controls._subtitle_undo.isEnabled()
                assert host._player.undo_subtitle() and subtitle.is_file()
                assert not host._controls._subtitle_undo.isEnabled()
                result['checks'].append('profile persistence, whole-line title ellipsis, real external subtitle add/undo')
                if not server_url:
                    host._room_panel.mode.setCurrentIndex(1)
                host._on_create_room('package-host')
                wait_for(lambda: host._room_ready)
                if server_url:
                    guest._on_join_room(host._room_code, 'package-guest')
                else:
                    from app.hosting import make_invitation
                    service = host._rooms.host
                    invitation = make_invitation('ws://127.0.0.1:' + str(service.port) + service.guest_path, host._room_code)
                    guest._on_join_room(invitation, 'package-guest')
                wait_for(lambda: guest._room_ready)
                if host._chat_images_supported:
                    from PySide6.QtCore import QBuffer, QIODevice
                    from PySide6.QtGui import QImage
                    from app.ui.chat_images import prepare_image, EmojiPicker
                    image = QImage(320, 240, QImage.Format_RGB32)
                    image.fill(Qt.red)
                    buffer = QBuffer()
                    buffer.open(QIODevice.WriteOnly)
                    assert image.save(buffer, 'PNG')
                    payload = prepare_image(bytes(buffer.data()))
                    picker = EmojiPicker(host)
                    assert picker.list.count() >= 16
                    picker.deleteLater()
                    host._on_chat_image(payload)
                    wait_for(lambda: guest._room_panel._chat_list.count() == 1)
                    assert guest._room_panel._chat_list.item(0).data(Qt.UserRole) == 'image'
                    guest._controls._bar_danmaku_toggle.setChecked(False)
                    assert not guest._danmaku._labels
                    host._on_chat_image(payload)
                    wait_for(lambda: guest._room_panel._chat_list.count() == 2)
                    guest._controls._bar_danmaku_toggle.setChecked(True)
                    assert not guest._danmaku._labels
                    result['checks'].append('bundled image decoder and emoji picker; image chat; danmaku clear/no replay')
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
                if not server_url:
                    host._on_leave_room()
                    wait_for(lambda: not guest._room_code and not guest._network.isRunning())
                    result['checks'].append('embedded server in client, authenticated invitation, owner disband')
                if getattr(sys, 'frozen', False):
                    import hashlib
                    import subprocess
                    from app.tunnel import CLOUDFLARED_SHA256
                    helper = Path(sys._MEIPASS) / 'tools/cloudflared.exe'
                    assert hashlib.sha256(helper.read_bytes()).hexdigest() == CLOUDFLARED_SHA256
                    check = subprocess.run([str(helper), '--version'], capture_output=True,
                                           timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    assert check.returncode == 0 and b'2026.10.1' in check.stdout
                    result['checks'].append('bundled cloudflared hash and native executable startup')
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
