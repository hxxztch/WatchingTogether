"""Image preparation and reusable, local emoji library."""
import base64
from pathlib import Path
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize, Signal
from PySide6.QtGui import QImageReader, QPixmap, QIcon, QFont, QPainter, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QLabel, QMessageBox, QTabBar, QWidget, QInputDialog)
import app.config as config
from app.chat_media import MAX_IMAGE_BYTES, image_bytes

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
IMAGE_FILTER = '图片 (*.png *.jpg *.jpeg *.webp *.gif *.bmp)'
EMOJIS = ['😀', '😂', '🥰', '😎', '😭', '😮', '😡', '🤔', '👍', '👎', '👏', '🙏', '❤️', '🎉', '🍿', '🎬']


def prepare_image(raw):
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('原图超过 8 MB，请选择较小的图片。')
    buf = QBuffer()
    buf.setData(QByteArray(raw))
    buf.open(QIODevice.ReadOnly)
    reader = QImageReader(buf)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 16000000:
        raise ValueError('图片无法读取或尺寸超过 1600 万像素。')
    reader.setScaledSize(size.scaled(320, 320, Qt.KeepAspectRatio))
    picture = reader.read()  # GIF: first frame only, by design.
    if picture.isNull():
        raise ValueError('无法解码此图片。')
    for edge in (320, 240, 180, 128, 96, 64):
        small = picture.scaled(edge, edge, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        output = QBuffer()
        output.open(QIODevice.WriteOnly)
        if small.save(output, 'PNG'):
            data = bytes(output.data())
            if len(data) <= MAX_IMAGE_BYTES:
                return base64.b64encode(data).decode('ascii')
    raise ValueError('图片无法压缩到发送大小。')


def image_pixmap(value, edge=160):
    pixmap = QPixmap()
    pixmap.loadFromData(image_bytes(value), 'PNG')
    if pixmap.isNull():
        raise ValueError('图片无法解码')
    return pixmap.scaled(edge, edge, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def library_dir():
    return Path(config.CONFIG_PATH).parent / 'stickers'


from app.ui.sticker_library import ImportImages, read_library, save_library


def symbol_icon(symbol, color=None):
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setFont(QFont('Segoe UI Emoji' if color is None else 'Segoe UI Symbol', 22))
    if color:
        painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, symbol)
    painter.end()
    return QIcon(pixmap)


class StickerCategoryBar(QTabBar):
    """Icon-only category tabs with the same selection API used by the browser."""
    def __init__(self):
        super().__init__()
        self.setAccessibleName('表情分类')
        self.setExpanding(False)
        self.setUsesScrollButtons(True)
        self.setIconSize(QSize(32, 32))
        self.setStyleSheet('''
            QTabBar::tab { width: 44px; height: 44px; margin-right: 4px;
                border: 1px solid transparent; border-radius: 9px; background: transparent; }
            QTabBar::tab:hover { background: #f8f0e8; }
            QTabBar::tab:selected { background: #f2e5d9; border-color: #d9c5b4; }
        ''')

    def addItem(self, title, data, icon):
        index = self.addTab(icon, '')
        self.setTabData(index, data)
        self.setTabToolTip(index, title)
        return index

    def currentData(self):
        return self.tabData(self.currentIndex()) if self.currentIndex() >= 0 else None

    def findData(self, data):
        for index in range(self.count()):
            if self.tabData(index) == data:
                return index
        return -1

    def clear(self):
        while self.count():
            self.removeTab(0)


class StickerBrowser(QWidget):
    """Read-only selection shared by profile management and the chat picker."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.category = StickerCategoryBar()
        self.category.currentChanged.connect(self.load_items)
        layout.addWidget(self.category)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setIconSize(QSize(40, 40))
        self.list.setMovement(QListWidget.Static)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setMinimumHeight(100)
        layout.addWidget(self.list)
        self.reload()

    def reload(self, group=None):
        group = group or self.category.currentData() or 'system'
        self.metadata = read_library()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem('系统 emoji · 插入文字', 'system', symbol_icon(EMOJIS[0]))
        self.category.addItem('自定义图片 · 单独发送', 'custom', symbol_icon('♥', '#e95068'))
        for key, name in self.metadata['packs'].items():
            icon = QIcon()
            for filename, entry in self.metadata['items'].items():
                if entry['group'] == key:
                    try:
                        value = base64.b64encode((library_dir() / filename).read_bytes()).decode('ascii')
                        icon = QIcon(image_pixmap(value, 32))
                        break
                    except (ValueError, OSError):
                        continue
            self.category.addItem('外部表情包 · ' + name, key, icon)
        self.category.setCurrentIndex(max(0, self.category.findData(group)))
        self.category.blockSignals(False)
        self.load_items()

    def load_items(self):
        self.list.clear()
        group = self.category.currentData()
        self.list.setGridSize(QSize(48, 48) if group == 'system' else QSize(72, 72))
        if group == 'system':
            for emoji in EMOJIS:
                item = QListWidgetItem(emoji)
                item.setFont(QFont('Segoe UI Emoji', 14))
                item.setData(Qt.UserRole, ('text', emoji))
                self.list.addItem(item)
        else:
            for filename, entry in self.metadata['items'].items():
                if entry['group'] != group:
                    continue
                try:
                    value = base64.b64encode((library_dir() / filename).read_bytes()).decode('ascii')
                    item = QListWidgetItem(QIcon(image_pixmap(value, 40)), entry['name'])
                    item.setToolTip(entry['name'])
                    item.setData(Qt.UserRole, ('image', value, filename))
                    self.list.addItem(item)
                except (ValueError, OSError):
                    continue


class EmojiPicker(QDialog):
    text_chosen = Signal(str)
    image_chosen = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('发送表情与图片')
        self.resize(440, 320)
        self._chosen = False
        layout = QVBoxLayout(self)
        self.browser = StickerBrowser()
        self.list = self.browser.list
        self.list.itemClicked.connect(self._clicked)
        self.list.itemActivated.connect(self.choose)
        layout.addWidget(self.browser)
        note = QLabel('单击系统 emoji 插入聊天光标位置；图片单独发送。\n导入、重命名和删除请前往个人中心。')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        upload = QPushButton('上传图片发送')
        upload.clicked.connect(self.upload)
        row.addWidget(upload)
        row.addStretch()
        self.select = QPushButton('单独发送')
        self.select.clicked.connect(self.choose)
        row.addWidget(self.select)
        layout.addLayout(row)
        self.browser.category.currentChanged.connect(self.update_action)
        self.update_action()

    def update_action(self):
        self.select.setVisible(self.browser.category.currentData() != 'system')

    def _clicked(self, item):
        if item.data(Qt.UserRole)[0] == 'text':
            self.choose()

    def choose(self, *_):
        item = self.list.currentItem()
        if item and not self._chosen:
            self._chosen = True
            kind, value, *_ = item.data(Qt.UserRole)
            (self.text_chosen if kind == 'text' else self.image_chosen).emit(value)
            self.accept()

    def upload(self):
        path, _ = QFileDialog.getOpenFileName(self, '发送图片', '', IMAGE_FILTER)
        if path:
            try:
                if Path(path).stat().st_size > 8 * 1024 * 1024:
                    raise ValueError('原图超过 8 MB。')
                self.image_chosen.emit(prepare_image(Path(path).read_bytes()))
                self.accept()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, '图片无法发送', str(exc))


class StickerManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('roomCard')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumWidth(720)
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title = QLabel('表情包管理')
        title.setObjectName('heading')
        layout.addWidget(title)
        self.browser = StickerBrowser()
        self.list = self.browser.list
        layout.addWidget(self.browser)
        self.note = QLabel('系统 emoji 可与文字一起发送；图片表情单独发送。GIF 使用首帧。\n每次最多导入 100 张，表情库最多 300 张；仅保存在本机。')
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.PlainText)
        layout.addWidget(self.note)
        self.actions = QWidget()
        rows = QVBoxLayout(self.actions)
        rows.setContentsMargins(0, 0, 0, 0)
        for buttons in (
            [('添加自定义图片', self.import_files), ('导入文件夹', self.import_folder), ('导入 ZIP 包', self.import_zip)],
            [('重命名图片', self.rename), ('重命名表情包', self.rename_pack), ('删除图片', self.remove)],
        ):
            row = QHBoxLayout()
            for title, callback in buttons:
                button = QPushButton(title)
                button.clicked.connect(callback)
                row.addWidget(button)
                if title == '重命名图片': self.rename_button = button
                if title == '重命名表情包': self.rename_pack_button = button
                if title == '删除图片': self.remove_button = button
            row.addStretch()
            rows.addLayout(row)
        layout.addWidget(self.actions)
        self.browser.category.currentChanged.connect(self.update_actions)
        self.list.currentItemChanged.connect(self.update_actions)
        self.update_actions()

    def update_actions(self, *_):
        self.list.setFixedHeight(116 if self.browser.category.currentData() == 'system' else 164)
        item = self.list.currentItem()
        editable = bool(item and item.data(Qt.UserRole)[0] == 'image')
        self.rename_button.setEnabled(editable)
        self.remove_button.setEnabled(editable)
        self.rename_pack_button.setEnabled(self.browser.category.currentData() not in ('system', 'custom'))

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '添加自定义图片', '', IMAGE_FILTER)
        self.start_import([Path(p) for p in paths])

    def import_zip(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '导入外部表情包', '', 'ZIP 图片包 (*.zip)')
        self.start_import([Path(p) for p in paths])

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '导入外部表情文件夹')
        if folder:
            try:
                self.start_import(list(Path(folder).iterdir()), Path(folder).name)
            except OSError as exc:
                self.note.setText('无法读取文件夹：' + str(exc))

    def start_import(self, paths, pack_name=None):
        if not paths or self.worker is not None:
            return
        self.note.setText('正在导入并压缩表情，请稍候…')
        self.actions.setEnabled(False)
        self.worker = ImportImages(paths, self, pack_name)
        self.worker.completed.connect(self.imported)
        self.worker.finished.connect(self.import_finished)
        self.worker.start()

    def imported(self, count, failed, error):
        self.note.setText(f'已新增 {count} 张，失败 {failed} 张。重复图片自动跳过；每批最多处理 100 张。' + error)
        self.browser.reload(self.worker.group if self.worker else None)
        self.update_actions()

    def import_finished(self):
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        self.actions.setEnabled(True)

    def rename(self):
        item = self.list.currentItem()
        if self.worker or not item or item.data(Qt.UserRole)[0] != 'image':
            return
        name, ok = QInputDialog.getText(self, '重命名图片', '图片名称（最多 60 字）：', text=item.text())
        if ok:
            self.save_name(item.data(Qt.UserRole)[2], name)

    def rename_pack(self):
        group = self.browser.category.currentData()
        if self.worker or group not in self.browser.metadata['packs']:
            return
        name, ok = QInputDialog.getText(self, '重命名表情包', '表情包名称（最多 60 字）：', text=self.browser.metadata['packs'][group])
        if ok:
            self.save_name(group, name, pack=True)

    def save_name(self, key, name, pack=False):
        if self.worker:
            return False
        name = name.strip()
        if not name or len(name) > 60:
            self.note.setText('名称不能为空，且最多 60 字。')
            return False
        data = read_library()
        try:
            if pack:
                if key not in data['packs']: return False
                data['packs'][key] = name
            else:
                if key not in data['items']: return False
                data['items'][key]['name'] = name
            save_library(data)
            self.browser.reload()
            self.note.setText('名称已保存。')
            return True
        except OSError as exc:
            self.note.setText('保存失败：' + str(exc))
            return False

    def remove(self):
        item = self.list.currentItem()
        if self.worker or not item or item.data(Qt.UserRole)[0] != 'image':
            return
        key = item.data(Qt.UserRole)[2]
        try:
            (library_dir() / key).unlink()
            data = read_library()
            data['packs'] = {k: v for k, v in data['packs'].items()
                             if any(i['group'] == k for i in data['items'].values())}
            save_library(data)
            self.browser.reload()
            self.update_actions()
            self.note.setText('已从表情库删除，不影响原始图片文件。')
        except OSError as exc:
            self.note.setText('删除失败：' + str(exc))

    def shutdown(self):
        if self.worker:
            self.worker.requestInterruption()
            self.worker.wait()
