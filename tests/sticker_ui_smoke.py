"""Native UI acceptance for profile-managed stickers and the compact theatre."""
import base64
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'windows'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import Qt, QTimer, QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QPushButton, QListView, QLineEdit, QTextEdit, QPlainTextEdit, QTabBar, QToolButton
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.chat_images import EmojiPicker, EMOJIS, library_dir, prepare_image
from app.ui.sticker_library import read_library
from app.ui.text_menus import edit_menu
import app.config as config


def main():
    app = QApplication([])
    errors = []
    sys.excepthook = lambda *args: (errors.append(str(args[1])), sys.__excepthook__(*args))
    review = ROOT / 'build/sticker-ui-review'
    review.mkdir(parents=True, exist_ok=True)
    def wait(check):
        deadline = time.monotonic() + 10
        while not check():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < deadline
            time.sleep(.02)
        app.processEvents()

    with tempfile.TemporaryDirectory() as tmp:
        config.CONFIG_PATH = str(Path(tmp) / 'config.json')
        window = MainWindow()
        try:
            window.show()
            window.resize(1120, 720)
            manager = window._shell.sticker_manager
            picture = QImage(160, 120, QImage.Format_ARGB32)
            picture.fill(Qt.red)
            data = QBuffer()
            data.open(QIODevice.WriteOnly)
            assert picture.save(data, 'PNG')
            source = Path(tmp) / '开心.png'
            source.write_bytes(bytes(data.data()))
            manager.start_import([source])
            wait(lambda: manager.worker is None)
            assert manager.browser.category.currentData() == 'custom'
            assert manager.list.count() == 1
            manager.list.setCurrentRow(0)
            key = manager.list.currentItem().data(Qt.UserRole)[2]
            with patch.object(QInputDialog, 'getText', return_value=('改名后的图片', True)):
                manager.rename_button.click()
            assert read_library()['items'][key]['name'] == '改名后的图片'
            assert not manager.save_name(key, '   ')
            manager.start_import([source], '我的外部表情包')
            wait(lambda: manager.worker is None)
            pack = manager.browser.category.currentData()
            assert pack not in ('custom', 'system')
            assert len(read_library()['items']) == 2
            with patch.object(QInputDialog, 'getText', return_value=('重新命名的合集', True)):
                manager.rename_pack_button.click()
            assert read_library()['packs'][pack] == '重新命名的合集'
            tabs = manager.browser.category
            assert isinstance(tabs, QTabBar) and tabs.count() == 3
            assert all(not tabs.tabIcon(index).isNull() for index in range(3))
            assert tabs.tabToolTip(2).endswith('重新命名的合集')
            assert tabs.tabIcon(2).pixmap(32, 32).toImage().pixelColor(16, 16).red() > 200
            QTest.mouseClick(tabs, Qt.LeftButton, pos=tabs.tabRect(0).center())
            assert manager.list.count() == len(EMOJIS)
            QTest.mouseClick(tabs, Qt.LeftButton, pos=tabs.tabRect(2).center())
            assert manager.list.count() == 1 and tabs.currentData() == pack
            # Legacy flat libraries appear under Custom without reimporting.
            value = prepare_image(bytes(data.data()))
            legacy_data = base64.b64decode(value)
            legacy_key = hashlib.sha256(legacy_data).hexdigest() + '.png'
            (library_dir() / legacy_key).write_bytes(legacy_data)
            assert read_library()['items'][legacy_key]['group'] == 'custom'
            picker = EmojiPicker(window)
            assert picker.list.count() == 16
            QTest.mouseClick(picker.browser.category, Qt.LeftButton,
                             pos=picker.browser.category.tabRect(1).center())
            assert picker.list.count() == 2
            assert '改名后的图片' in [picker.list.item(i).text() for i in range(2)]
            assert not any('导入' in b.text() or '删除' in b.text() or '重命名' in b.text() for b in picker.findChildren(QPushButton))
            picker.deleteLater()
            window._switch_page(1)
            window._room_code = '1234'
            window._room_ready = True
            window._chat_images_supported = True
            window._room_panel.set_in_room(True, '1234', ['房主', '观众'])
            window._room_panel.set_latency(23)
            window._shell.refresh_status()
            field = window._room_panel._chat_input
            field.setText('你好世界')
            field.setCursorPosition(2)
            def choose_emoji():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, EmojiPicker)
                assert not dialog.select.isVisible()
                QTest.mouseClick(dialog.list.viewport(), Qt.LeftButton,
                                 pos=dialog.list.visualItemRect(dialog.list.item(0)).center())
            with patch.object(window._network, 'send') as send:
                QTimer.singleShot(100, choose_emoji)
                window._choose_emoji()
                assert field.text() == '你好' + EMOJIS[0] + '世界'
                assert not send.called
                QTest.keyClick(field, Qt.Key_Return)
                assert send.call_args[0][0]['message'] == '你好' + EMOJIS[0] + '世界'
                field.setText('尚未发送的文字')
                window._on_chat_image(value)
                assert field.text() == '尚未发送的文字'
                assert send.call_args[0][0]['message'] == '[图片]'
                assert send.call_args[0][0]['image'] == value
            assert '2 人在线' in window._shell.theatre_status.text()
            assert '23 ms' in window._shell.theatre_status.text()
            def check_members():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, QDialog)
                view = dialog.findChild(QListView)
                assert view.model().rowCount() == 2
                window._room_panel.add_member('新成员')
                assert view.model().rowCount() == 3
                dialog.accept()
            QTimer.singleShot(100, check_members)
            window._shell.members_details.click()
            buttons = window._room_panel.findChildren(QPushButton)
            assert not any(b.text() == '离开房间' for b in buttons)
            assert not hasattr(window._controls, '_bar_emoji_btn')
            assert not hasattr(window._controls, '_danmaku_input')
            assert not hasattr(window._controls, '_danmaku_toggle')
            window._controls.set_media_title('Cosmic.Princess.Kaguya.2026.2160p.WebRip.x265.很长很长的视频名称用于检查完整文字', '本地视频')
            window._controls.set_position(3800, 8000)
            window._shell.expanded = True
            window._shell._apply_sidebar()
            window._position_controls()
            QTest.qWait(250)
            before = window._room_panel._chat_list.height()
            composer_bottom = field.mapTo(window._right_content, field.rect().bottomRight()).y()
            assert composer_bottom < window._right_content.height()
            assert window._controls.media_panel.geometry().bottom() < window._media_fold.geometry().top()
            for control in (window._controls._bili_btn, window._controls._audio_combo,
                            window._controls._page_combo, window._controls._subtitle_btn):
                assert control.height() >= control.sizeHint().height(), (control, control.height(), control.sizeHint().height())
            window.grab().save(str(review / 'theatre-expanded.png'))
            window._media_fold.click()
            QTest.qWait(250)
            after = window._room_panel._chat_list.height()
            assert after > before + 60, (before, after)
            assert not window._controls.media_details.isVisible()
            assert window._controls._media_title.isVisible()
            assert window._controls._open_btn.isVisible()
            window.grab().save(str(review / 'theatre-collapsed.png'))
            window._controls.grab().save(str(review / 'controls-on.png'))
            window._controls._bar_danmaku_toggle.click()
            window._controls.grab().save(str(review / 'controls-off.png'))
            window._media_fold.click()
            QTest.qWait(100)
            assert window._controls.media_details.isVisible()
            window._switch_page(2)
            window.resize(1500, 900)
            QTest.qWait(200)
            card = window._room_panel.management
            container = card.parentWidget().parentWidget()
            center = card.mapTo(container, card.rect().center()).x()
            assert abs(center - container.width() / 2) < 3
            window.grab().save(str(review / 'rooms.png'))
            window._switch_page(3)
            manager.browser.category.setCurrentIndex(0)
            QTest.qWait(200)
            for card in (window._shell.profile, manager):
                container = card.parentWidget().parentWidget()
                center = card.mapTo(container, card.rect().center()).x()
                assert abs(center - container.width() / 2) < 3
            window.grab().save(str(review / 'profile.png'))
            for editor in (QLineEdit(), QTextEdit(), QPlainTextEdit()):
                menu = edit_menu(editor)
                titles = [a.text().split('\t')[0] for a in menu.actions() if not a.isSeparator()]
                assert '复制' in titles and '粘贴' in titles and '全选' in titles, titles
                assert not any(any(word in t for word in ('Undo', 'Redo', 'Cut', 'Copy', 'Paste', 'Delete', 'Select All')) for t in titles)
                menu.deleteLater()
                editor.deleteLater()
            manager.browser.category.setCurrentIndex(1)
            manager.list.setCurrentRow(0)
            manager.remove_button.click()
            assert source.exists() and len(read_library()['items']) == 2
            for index in range(12):
                manager.start_import([source], f'合集 {index + 1}')
                wait(lambda: manager.worker is None)
            tabs = manager.browser.category
            assert tabs.count() == 15 and tabs.currentIndex() == 14
            assert any(button.isVisible() for button in tabs.findChildren(QToolButton))
            assert tabs.tabRect(14).center().x() < tabs.width()
            QTest.keyClick(tabs, Qt.Key_Left)
            assert tabs.currentIndex() == 13
            QTest.mouseClick(tabs, Qt.LeftButton, pos=tabs.tabRect(14).center())
            assert tabs.currentIndex() == 14 and manager.list.count() == 1
            print('PASS: categorized persistent imports/rename/delete; emoji inserts in draft; image sends alone; legacy library migrated')
            print('PASS: chat grows on collapse; member details share live model; single bottom toggle; Chinese edit menus; centered room cards')
            manager.start_import([source] * 100, '退出时中断导入')
        finally:
            backend = window._player._player
            window.close()
            assert manager.worker is None or not manager.worker.isRunning()
            assert backend is None or not backend._event_thread.is_alive()
            if window._player._player:
                window._player._player.terminate()
            app.processEvents()
        assert not errors, errors


if __name__ == '__main__':
    main()
