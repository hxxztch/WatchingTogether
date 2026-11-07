import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from app.runtime import configure_runtime
configure_runtime()
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QMovie
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from app.chat_media import image_bytes, MAX_GIF_BYTES
from app.ui.chat_images import prepare_image, image_pixmap
from app.ui.gif_images import set_label_image

APP = QApplication.instance() or QApplication([])


def gif_bytes(count=3):
    frames = [Image.new('RGBA', (48, 32), color) for color in ('red', 'blue', 'green')]
    output = BytesIO()
    frames[0].save(output, format='GIF', save_all=True,
                   append_images=(frames * 28)[1:count], duration=80, loop=0)
    return output.getvalue()


class GifTests(unittest.TestCase):
    def test_chat_context_menu_favorites_gif_and_static_without_duplicates(self):
        import app.config as config
        from app.ui.room_panel import RoomPanel
        from app.ui.sticker_library import read_library, save_library
        from PySide6.QtWidgets import QMenu, QMessageBox
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
                panel = RoomPanel()
                saved = []
                panel.sticker_added.connect(lambda: saved.append(True))
                animation = prepare_image(gif_bytes())
                for value in (animation, prepare_image(image_bytes(animation), animate=False)):
                    panel.add_chat('other-user', '[图片]', value)
                    row = panel._chat_list.itemWidget(panel._chat_list.item(panel._chat_list.count() - 1))
                    picture = next(label for label in row.findChildren(QLabel)
                                   if label.contextMenuPolicy() == Qt.CustomContextMenu)
                    actions = []
                    def select_favorite():
                        menu = panel.findChildren(QMenu)[-1]
                        actions.extend(a.text() for a in menu.actions())
                        try:
                            menu.actions()[0].trigger()
                        finally:
                            menu.close()
                    QTimer.singleShot(0, select_favorite)
                    with patch.object(QMessageBox, 'warning') as warning:
                        point = QPoint(1, 1)
                        QApplication.sendEvent(picture, QContextMenuEvent(
                            QContextMenuEvent.Mouse, point, picture.mapToGlobal(point)))
                    self.assertEqual(actions, ['添加到表情'])
                    self.assertFalse(warning.called, warning.call_args)
                    entries = read_library()['items']
                    filename = next(key for key in entries
                                    if (Path(directory) / 'stickers' / key).read_bytes() == image_bytes(value))
                    self.assertEqual(entries[filename]['group'], 'custom')
                    data = read_library()
                    data['items'][filename]['name'] = 'renamed-favorite'
                    save_library(data)
                    panel._favorite_chat_image(value)
                    self.assertEqual(read_library()['items'][filename]['name'], 'renamed-favorite')
                self.assertEqual(len(saved), 4)
                self.assertEqual(len(read_library()['items']), 2)
                panel.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_favorite_failure_does_not_leave_orphan_file(self):
        import app.config as config
        from app.ui.sticker_library import favorite_image, read_library
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
                with patch('app.ui.sticker_library.save_library', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        favorite_image(prepare_image(gif_bytes()))
                self.assertEqual(read_library()['items'], {})
                self.assertEqual(list((Path(directory) / 'stickers').iterdir()), [])

    def test_favorite_during_import_is_rejected_without_blocking(self):
        import threading
        from app.ui.sticker_library import favorite_image, _LIBRARY_LOCK
        ready, release = threading.Event(), threading.Event()
        def importing():
            with _LIBRARY_LOCK:
                ready.set()
                release.wait(5)
        thread = threading.Thread(target=importing)
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            with self.assertRaisesRegex(ValueError, '正在导入'):
                favorite_image(prepare_image(gif_bytes()))
        finally:
            release.set()
            thread.join(3)

    def test_animation_preserves_frames_and_static_fallback(self):
        value = prepare_image(gif_bytes())
        raw = image_bytes(value)
        self.assertLessEqual(len(raw), MAX_GIF_BYTES)
        with Image.open(BytesIO(raw)) as image:
            self.assertEqual(image.n_frames, 3)
            self.assertEqual(image.info['loop'], 0)
            self.assertEqual(image.info['duration'], 80)
        fallback = prepare_image(raw, animate=False)
        self.assertTrue(image_bytes(fallback).startswith(b'\x89PNG'))
        self.assertFalse(image_pixmap(value).isNull())

    def test_invalid_and_excessive_animation_rejected(self):
        value = prepare_image(gif_bytes())
        raw = bytearray(image_bytes(value))
        raw[6:8] = (161).to_bytes(2, 'little')
        for broken in (bytes(raw), b'GIF89a', image_bytes(value)[:-3] + b';'):
            with self.assertRaises(ValueError):
                image_bytes(base64.b64encode(broken).decode('ascii'))
        with self.assertRaises(ValueError):
            prepare_image(gif_bytes(81))

    def test_qt_movie_advances_and_is_destroyed_with_label(self):
        label = QLabel()
        set_label_image(label, prepare_image(gif_bytes()), 64)
        movie = label.movie()
        frames = []
        destroyed = []
        movie.frameChanged.connect(frames.append)
        movie.destroyed.connect(lambda: destroyed.append(True))
        QTest.qWait(300)
        self.assertIn(1, frames)
        self.assertIn(2, frames)
        self.assertLessEqual(label.width(), 64)
        label.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertTrue(destroyed)

    def test_library_import_keeps_gif_and_metadata(self):
        import app.config as config
        from app.ui.sticker_library import ImportImages, read_library
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dance.gif'
            path.write_bytes(gif_bytes())
            with patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
                worker = ImportImages([path], None)
                worker.run()
                entries = read_library()['items']
                self.assertEqual(len(entries), 1)
                filename, entry = next(iter(entries.items()))
                self.assertTrue(filename.endswith('.gif'))
                self.assertEqual(entry['name'], 'dance')
                value = base64.b64encode((Path(directory) / 'stickers' / filename).read_bytes()).decode('ascii')
                self.assertTrue(image_bytes(value).startswith(b'GIF'))

    def test_chat_animation_limit_and_removal(self):
        from app.ui.room_panel import RoomPanel
        panel = RoomPanel()
        value = prepare_image(gif_bytes())
        for _ in range(12):
            panel.add_chat('sender', '[图片]', value)
        movies = panel.findChildren(QLabel)
        running = [label for label in movies if label.movie() and label.movie().state() == QMovie.MovieState.Running]
        self.assertEqual(len(running), 10)
        widget = panel._chat_list.itemWidget(panel._chat_list.item(0))
        deleted = []
        widget.destroyed.connect(lambda: deleted.append(True))
        panel._remove_chat_item(0)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertTrue(deleted)
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_send_uses_static_fallback_for_legacy_server(self):
        from app.ui.main_window import MainWindow
        for supported in (True, False):
            window = SimpleNamespace(_room_ready=True, _chat_images_supported=True,
                _chat_gifs_supported=supported, _network=Mock(), _room_panel=Mock(), _danmaku=Mock())
            value = prepare_image(gif_bytes())
            MainWindow._on_chat_image(window, value)
            payload = window._network.send.call_args[0][0]
            self.assertTrue(image_bytes(payload['image']).startswith(b'\x89PNG'))
            self.assertEqual('animation' in payload, supported)
            self.assertEqual(window._room_panel.add_chat.call_args[0][2],
                             value if supported else payload['image'])

    def test_danmaku_disable_destroys_animation_without_replay(self):
        from PySide6.QtWidgets import QWidget
        from app.ui.danmaku import DanmakuOverlay
        target = QWidget()
        target.resize(640, 360)
        target.show()
        overlay = DanmakuOverlay()
        overlay.track(target)
        overlay.show_danmaku('sender', '[图片]', prepare_image(gif_bytes()))
        self.assertEqual(len(overlay._labels), 1)
        label = overlay._labels[0]['label']
        self.assertIsNotNone(label.movie())
        dead = []
        label.movie().destroyed.connect(lambda: dead.append(True))
        overlay.set_enabled(False)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertTrue(dead)
        overlay.set_enabled(True)
        self.assertEqual(overlay._labels, [])
        overlay.close()
        overlay.deleteLater()
        target.close()
        target.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
