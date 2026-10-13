"""Hidden Qt/mpv checks; optional --live-bilibili uses the saved login read-only."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.player import mpv
from app.ui.main_window import MainWindow
from app.bilibili import QualityUnavailable
import app.config as config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-bilibili', action='store_true')
    live = parser.parse_args().live_bilibili
    cookie = config.load().get('bili_cookie', '') if live else ''
    app = QApplication([])
    errors = []
    def record_error(kind, value, tb):
        errors.append(kind.__name__)
        traceback.print_tb(tb)
        print(kind.__name__, str(value) if kind is AssertionError else '', flush=True)
    sys.excepthook = record_error
    original_init = mpv.MPV.__init__

    def null_init(self, *args, **kwargs):
        kwargs.pop('wid', None)
        kwargs.update(vo='null', ao='null', hwdec='no')
        original_init(self, *args, **kwargs)

    def wait_for(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            assert not errors, errors
            if time.monotonic() > deadline:
                raise AssertionError('Media condition timed out')
            time.sleep(.02)
        app.processEvents()

    with tempfile.TemporaryDirectory(prefix='film-media-test-') as temporary:
        config.CONFIG_PATH = str(Path(temporary) / 'config.json')
        config.save(server='ws://127.0.0.1:1', bili_cookie=cookie)
        with patch.object(mpv.MPV, '__init__', null_init):
            window = MainWindow()
            window._network.stop()
            try:
                media = Path(temporary) / 'sample.y4m'
                media.write_bytes(b'YUV4MPEG2 W16 H16 F25:1 Ip A1:1 C420jpeg\n' +
                                  (b'FRAME\n' + bytes([128]) * 384) * 500)
                window._on_load_file(str(media))
                wait_for(lambda: not window._player.is_loading and window._player.duration > 0)
                assert window._player.is_playing, 'Local media did not auto-play'
                window._player.pause()
                controls = window._controls
                controls.show()
                controls.set_position(2, 20)
                seeks = []
                controls.seek_requested.connect(seeks.append)

                def edit(text):
                    QTest.mouseClick(controls._time_label, Qt.LeftButton)
                    controls._time_editor.setText(text)

                edit('00:04')
                with patch.object(window, 'isFullScreen', return_value=True), patch.object(controls, 'hide') as hide:
                    window._hide_fs_controls()
                    hide.assert_not_called()
                controls.set_position(3, 20)
                assert controls._time_editor.text() == '00:04'
                QTest.keyClick(controls._time_editor, Qt.Key_Return)
                wait_for(lambda: abs(window._player.position - 4) < .3)
                assert seeks == [4] and not window._player.is_playing
                for value in ['00:60', '99', 'bad']:
                    edit(value)
                    QTest.keyClick(controls._time_editor, Qt.Key_Return)
                    assert controls.is_editing_time and seeks == [4]
                QTest.keyClick(controls._time_editor, Qt.Key_Escape)
                assert not controls.is_editing_time
                edit('00:09')
                from PySide6.QtCore import QEvent
                from PySide6.QtGui import QFocusEvent
                app.sendEvent(controls._time_editor, QFocusEvent(QEvent.FocusOut))
                assert not controls.is_editing_time and seeks == [4]
                edit('0')
                QTest.keyClick(controls._time_editor, Qt.Key_Return)
                wait_for(lambda: window._player.position < .3)
                window._player.replace_flv(str(media), 5, False)
                wait_for(lambda: not window._player.is_loading and abs(window._player.position - 5) < .3)
                assert not window._player.is_playing
                failures = []
                window._player.media_load_failed.connect(lambda: failures.append(True))
                window._player.load(str(Path(temporary) / 'missing.mp4'))
                wait_for(lambda: bool(failures))
                assert not window._player.is_loading
                window._player.replace_flv(str(media), 5, False)
                wait_for(lambda: not window._player.is_loading and window._player.duration > 0)
                # A result arriving after stop/open/close must never start its stream.
                generation = window._quality_generation
                window._invalidate_quality_request()
                with patch.object(window._player, 'load_dash') as load:
                    window._finish_quality_change(generation, (None, ('ignored', 'ignored', 80, {})))
                    load.assert_not_called()
                bi = {'current_qn': 80, 'quality_map': {'80': '1080P', '16': '360P'}}
                window._bili_info = bi
                with patch.object(window._player, 'load_dash') as load:
                    window._finish_quality_change(window._quality_generation,
                                                  (bi, QualityUnavailable(120, bi['quality_map'])))
                    load.assert_not_called()
                    assert bi['current_qn'] == 80
                window._bili_info = None
                window._on_stop()
                assert controls._duration == 0
                edit('1')
                QTest.keyClick(controls._time_editor, Qt.Key_Return)
                assert controls.is_editing_time and seeks == [4, 0]
                QTest.keyClick(controls._time_editor, Qt.Key_Escape)
                window._on_seek(1)
                print('PASS: click/edit/Enter, invalid input, Escape, paused zero, per-file load options', flush=True)
                print('PASS: load failure recovery, stale quality result ignored, unavailable quality preserves old stream', flush=True)

                if live:
                    anonymous = window._bili_api.fetch_streams(117369577936130, 42383181508, 120)
                    assert anonymous[2] in (16, 32) and '120' not in anonymous[3]
                    assert '16' in anonymous[3]
                    print('PASS: anonymous actual quality list ' + ','.join(anonymous[3]), flush=True)
                    window._on_load_url('https://www.bilibili.com/video/BV1mfay6pEti/')
                    wait_for(lambda: not window._player.is_loading and bool(window._player.get_video_info().get('width')), 50)
                    assert window._bili_info, 'Bilibili resolver failed'
                    for qn, width in [(120, 3840), (80, 1920), (64, 1280), (16, 640)]:
                        assert str(qn) in window._bili_info['quality_map'], 'Account does not supply requested quality'
                        window._player.pause()
                        window._player.seek(10)
                        wait_for(lambda: abs(window._player.position - 10) < .5)
                        window._on_quality_change(str(qn))
                        wait_for(lambda: not window._quality_busy and not window._player.is_loading and
                                 window._player.get_video_info().get('width') == width, 50)
                        assert window._bili_info['current_qn'] == qn
                        assert abs(window._player.position - 10) < .5
                        assert not window._player.is_playing
                        assert window._player.get_audio_tracks(), 'External audio missing'
                        info = window._player.get_video_info()
                        print(f"PASS: qn={qn}, decoded={info['width']}x{info['height']}, paused at 10s, audio present", flush=True)
                    window._player.play()
                    window._on_quality_change('80')
                    wait_for(lambda: not window._quality_busy and not window._player.is_loading and
                             window._player.get_video_info().get('width') == 1920, 50)
                    assert window._player.is_playing and window._player.position >= 10
                    print('PASS: playing quality switch preserves playback', flush=True)
            finally:
                window.close()
                if window._player._player:
                    window._player._player.terminate()
    assert not errors, errors


if __name__ == '__main__':
    main()
