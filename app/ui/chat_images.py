"""Image preparation and reusable, local emoji library."""
import base64
import hashlib
import zipfile
from pathlib import Path
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize, QThread, Signal
from PySide6.QtGui import QImageReader, QPixmap, QIcon, QFont
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QLabel, QMessageBox, QAbstractItemView)
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


class ImportImages(QThread):
    completed = Signal(int, int, str)

    def __init__(self, paths, parent):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        count = failed = 0
        error = ''
        try:
            directory = library_dir()
            directory.mkdir(parents=True, exist_ok=True)
            remaining = max(0, 300 - len(list(directory.glob('*.png'))))
            if remaining == 0:
                raise ValueError('表情库最多保存 300 张，请先删除不用的表情。')
            def store(raw):
                nonlocal count, failed
                try:
                    data = image_bytes(prepare_image(raw))
                    target = directory / (hashlib.sha256(data).hexdigest() + '.png')
                    if not target.exists():
                        target.write_bytes(data)
                        count += 1
                except (ValueError, OSError):
                    failed += 1
            limit = min(100, remaining)
            used = 0
            total = 0
            for path in self.paths:
                if used >= limit:
                    break
                if path.suffix.lower() == '.zip':
                    with zipfile.ZipFile(path) as archive:
                        # Never extract archive paths onto the filesystem.
                        for entry in archive.infolist():
                            if used >= limit or total >= 64 * 1024 * 1024:
                                break
                            if entry.is_dir() or Path(entry.filename).suffix.lower() not in EXTENSIONS:
                                continue
                            used += 1
                            if entry.file_size > 8 * 1024 * 1024:
                                failed += 1
                                continue
                            total += entry.file_size
                            store(archive.read(entry))
                elif path.suffix.lower() in EXTENSIONS:
                    used += 1
                    if path.stat().st_size > 8 * 1024 * 1024:
                        failed += 1
                    else:
                        store(path.read_bytes())
        except Exception as exc:
            error = str(exc)
        self.completed.emit(count, failed, error)


class EmojiPicker(QDialog):
    text_chosen = Signal(str)
    image_chosen = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('表情与图片')
        self.resize(460, 430)
        self.worker = None
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setIconSize(QSize(56, 56))
        self.list.setGridSize(QSize(76, 80))
        self.list.setMovement(QListWidget.Static)
        self.list.itemDoubleClicked.connect(self.choose)
        layout.addWidget(self.list)
        self.note = QLabel('双击或选中后发送。图片自动压缩；GIF 使用首帧。\n每次最多导入 100 张，表情库最多 300 张。')
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.PlainText)
        layout.addWidget(self.note)
        row = QHBoxLayout()
        for title, callback in [('上传图片', self.upload), ('导入表情包', self.import_files),
                                ('导入文件夹', self.import_folder), ('删除', self.remove), ('发送', self.choose)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.reload()

    def reload(self):
        self.list.clear()
        for emoji in EMOJIS:
            item = QListWidgetItem(emoji)
            item.setFont(QFont('Segoe UI Emoji', 22))
            item.setData(Qt.UserRole, ('text', emoji))
            self.list.addItem(item)
        for path in sorted(library_dir().glob('*.png'))[:300]:
            try:
                value = base64.b64encode(path.read_bytes()).decode('ascii')
                item = QListWidgetItem(QIcon(image_pixmap(value, 56)), '自定义')
                item.setData(Qt.UserRole, ('image', value, str(path)))
                self.list.addItem(item)
            except (ValueError, OSError):
                continue

    def choose(self, *_):
        item = self.list.currentItem()
        if not item or self.worker is not None:
            return
        kind, value, *_ = item.data(Qt.UserRole)
        (self.text_chosen if kind == 'text' else self.image_chosen).emit(value)
        self.accept()

    def upload(self):
        if self.worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(self, '发送图片', '', IMAGE_FILTER)
        if path:
            try:
                if Path(path).stat().st_size > 8 * 1024 * 1024:
                    raise ValueError('原图超过 8 MB。')
                self.image_chosen.emit(prepare_image(Path(path).read_bytes()))
                self.accept()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, '图片无法发送', str(exc))

    def import_files(self):
        if self.worker is None:
            paths, _ = QFileDialog.getOpenFileNames(self, '添加自定义表情 / 导入图片 ZIP', '', IMAGE_FILTER + ';;ZIP 图片包 (*.zip)')
            self.start_import([Path(p) for p in paths])

    def import_folder(self):
        if self.worker is None:
            folder = QFileDialog.getExistingDirectory(self, '导入表情文件夹')
            if folder:
                self.start_import(list(Path(folder).iterdir()))

    def start_import(self, paths):
        if not paths or self.worker is not None:
            return
        self.note.setText('正在导入并压缩表情，请稍候…')
        self.worker = ImportImages(paths, self)
        self.worker.completed.connect(self.imported)
        self.worker.finished.connect(self.import_finished)
        self.worker.start()

    def imported(self, count, failed, error):
        self.note.setText(f'已导入 {count} 张，跳过或失败 {failed} 张。' + error)
        self.reload()

    def import_finished(self):
        self.worker.deleteLater()
        self.worker = None

    def remove(self):
        item = self.list.currentItem()
        if item and self.worker is None:
            data = item.data(Qt.UserRole)
            if data[0] == 'image':
                try:
                    Path(data[2]).unlink()
                    self.reload()
                except OSError as exc:
                    self.note.setText(str(exc))

    def reject(self):
        if self.worker is None:
            super().reject()
