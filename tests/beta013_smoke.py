"""Real Qt/host image delivery, local library and minimize/PiP regressions."""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'windows'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.chat_images import prepare_image, image_pixmap, EmojiPicker, library_dir
from app.chat_media import image_bytes, MAX_IMAGE_BYTES
import app.config as config


def main():
    app = QApplication([])
    failures = []
    sys.excepthook = lambda *args: failures.append(str(args[1]))
    def wait(check, timeout=10):
        end = time.monotonic() + timeout
        while not check():
            app.processEvents()
            assert not failures, failures
            assert time.monotonic() < end, 'Condition timed out'
            time.sleep(.02)
        app.processEvents()
    with tempfile.TemporaryDirectory() as directory:
        config.CONFIG_PATH = str(Path(directory) / 'config.json')
        picture = QImage(1024, 768, QImage.Format_ARGB32)
        picture.fill(Qt.red)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        assert picture.save(buffer, 'PNG')
        value = prepare_image(bytes(buffer.data()))
        assert len(image_bytes(value)) <= MAX_IMAGE_BYTES
        assert image_pixmap(value).width() <= 160
        media = Path(directory) / 'clip.y4m'
        media.write_bytes(b'YUV4MPEG2 W160 H160 F25:1 Ip A1:1 C420jpeg\n' +
                          (b'FRAME\n' + bytes([120]) * 25600 + bytes([128]) * 12800) * 1000)
        host, guest = MainWindow(), MainWindow()
        try:
            host.show()
            guest.show()
            host._room_panel.mode.setCurrentIndex(1)
            host._on_create_room('owner')
            wait(lambda: bool(host._room_panel.invitation.text()))
            guest._on_join_room(host._room_panel.invitation.text(), 'viewer')
            wait(lambda: guest._room_ready)
            assert guest._chat_images_supported
            host._on_chat_image(value)
            wait(lambda: guest._room_panel._chat_list.count() == 1)
            assert guest._room_panel._chat_list.item(0).data(Qt.UserRole) == 'image'
            assert len(guest._danmaku._labels) == 1
            guest._controls._bar_danmaku_toggle.setChecked(False)
            assert not guest._danmaku._labels
            assert not guest._controls._bar_danmaku_toggle.isChecked()
            host._on_chat_image(value)
            wait(lambda: guest._room_panel._chat_list.count() == 2)
            assert not guest._danmaku._labels
            guest._controls._bar_danmaku_toggle.setChecked(True)
            assert not guest._danmaku._labels
            host._on_chat('new-after-enable')
            wait(lambda: len(guest._danmaku._labels) == 1)
            assert 'new-after-enable' in guest._danmaku._labels[0]['label'].text()
            # Old external servers must not silently drop attached pictures.
            guest._chat_images_supported = False
            with patch.object(QMessageBox, 'information') as warning:
                guest._on_chat_image(value)
                assert warning.call_count == 1
            guest._chat_images_supported = True
            manager = host._shell.sticker_manager
            pack = Path(directory) / 'pack.zip'
            with zipfile.ZipFile(pack, 'w') as z:
                z.writestr('../../outside.png', bytes(buffer.data()))
                z.writestr('broken.png', b'not an image')
            manager.start_import([pack])
            wait(lambda: manager.worker is None)
            assert len(list(library_dir().glob('*.png'))) == 1
            assert not (Path(directory).parent / 'outside.png').exists()
            picker = EmojiPicker(host)
            assert picker.list.count() == 16
            picker.browser.category.setCurrentIndex(2)
            assert picker.list.count() == 1
            review = ROOT / 'build/beta013-review'
            review.mkdir(parents=True, exist_ok=True)
            picker.show()
            QTest.qWait(100)
            picker.grab().save(str(review / 'emoji-library.png'))
            chosen = []
            picker.image_chosen.connect(chosen.append)
            QTest.mouseClick(picker.list.viewport(), Qt.LeftButton,
                             pos=picker.list.visualItemRect(picker.list.item(0)).center())
            assert chosen == [value]
            manager.list.setCurrentRow(0)
            manager.remove()
            assert not list(library_dir().glob('*.png'))
            picker.deleteLater()
            print('PASS: images delivered; disable clears immediately, disabled traffic not replayed; import/select/delete', flush=True)
            host._switch_page(1)
            host._on_load_file(media.as_posix())
            wait(lambda: host._player.duration > 0 and not host._player.is_loading)
            host._player.play()
            wait(lambda: host._player.is_playing)
            backend = host._player._player
            host.showMinimized()
            wait(lambda: host._pip.isVisible() and host._player.parentWidget() is host._pip)
            assert host.isMinimized() and host._player._player is backend
            assert not host._pip.isMinimized()
            QTest.qWait(400)
            assert host._pip.isVisible()
            host._pip.grab().save(str(review / 'minimized-player.png'))
            host._pip.restore.click()
            wait(lambda: not host.isMinimized() and not host._pip.isVisible())
            host._switch_page(0)
            wait(lambda: host._pip.isVisible())
            host.showMinimized()
            QTest.qWait(300)
            assert host._pip.isVisible() and not host._pip.isMinimized()
            host._pip.restore.click()
            wait(lambda: not host.isMinimized() and not host._pip.isVisible())
            assert host._player._player is backend
            host._player.pause()
            host.showMinimized()
            wait(lambda: host._pip.isVisible())
            assert not host._player.is_playing
            host._pip.restore.click()
            wait(lambda: not host.isMinimized() and not host._pip.isVisible())
            host._player.play()
            print('PASS: minimize theatre opens PiP; existing PiP survives minimize; return restores same player', flush=True)
            from types import SimpleNamespace
            updater = Path(directory) / 'updater'
            updater.mkdir()
            (updater / 'apply_update.ps1').write_text('# mocked updater')
            delta = Path(directory) / 'test.delta.zip'
            delta.write_bytes(b'test')
            settings = host._shell.settings
            settings._download_is_delta = True
            settings._target = delta
            settings._release = SimpleNamespace(tag='beta0.1.4')
            host._switch_page(0)
            wait(lambda: host._pip.isVisible())
            with patch.object(sys, '_MEIPASS', directory, create=True), \
                    patch('app.ui.settings.subprocess.Popen') as launch, \
                    patch.object(QApplication, 'quit') as quit_app:
                settings.install_update()
                assert launch.call_count == quit_app.call_count == 1
                assert host._closing and not host._pip.isVisible() and host._rooms.host is None
                assert not backend._event_thread.is_alive(), 'mpv thread must stop before Qt exits'
            print('PASS: update shutdown closes active PiP and room before quitting', flush=True)
        finally:
            for window in (host, guest):
                window.close()
                if window._player._player:
                    window._player._player.terminate()
            app.processEvents()
        assert not failures, failures


if __name__ == '__main__':
    main()
