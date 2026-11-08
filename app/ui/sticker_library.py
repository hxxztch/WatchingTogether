"""Local image sticker metadata; no user image is uploaded during import."""
import hashlib
import json
import re
import uuid
import zipfile
import threading
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from app.chat_media import image_bytes, MAX_ORIGINAL_BYTES

_LIBRARY_LOCK = threading.RLock()


def read_library():
    from app.ui.chat_images import library_dir
    directory = library_dir()
    try:
        saved = json.loads((directory / 'library.json').read_text(encoding='utf-8'))
        if not isinstance(saved, dict):
            saved = {}
    except (OSError, ValueError):
        saved = {}
    packs = saved.get('packs', {})
    packs = {k: str(v)[:60] for k, v in packs.items() if re.fullmatch(r'[a-f0-9]{32}', k)} if isinstance(packs, dict) else {}
    entries = saved.get('items', {})
    entries = entries if isinstance(entries, dict) else {}
    items = {}
    for path in sorted(list(directory.glob('*.png')) + list(directory.glob('*.gif')))[:300]:
        if not re.fullmatch(r'[a-f0-9]{64}\.(png|gif)', path.name):
            continue
        item = entries.get(path.name, {})
        item = item if isinstance(item, dict) else {}
        group = item.get('group', 'custom')
        items[path.name] = {'name': str(item.get('name') or '自定义表情')[:60],
                            'group': group if isinstance(group, str) and group in packs else 'custom'}
    return {'packs': packs, 'items': items}


def save_library(data):
    from app.ui.chat_images import library_dir
    directory = library_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / ('library-' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(directory / 'library.json')
    finally:
        if temporary.exists():
            temporary.unlink()


def favorite_image(value):
    """Save the received payload unchanged in Custom, retaining GIF animation."""
    from app.ui.chat_images import library_dir
    raw = image_bytes(value)
    if not _LIBRARY_LOCK.acquire(blocking=False):
        raise ValueError('正在导入表情，请等待导入完成后再收藏。')
    try:
        directory = library_dir()
        data = read_library()
        # Also recognize older flat-library filenames and preserve renamed entries.
        for filename, entry in data['items'].items():
            if entry['group'] == 'custom' and (directory / filename).read_bytes() == raw:
                return False
        if len(data['items']) >= 300:
            raise ValueError('表情库最多保存 300 张，请先删除不用的表情。')
        directory.mkdir(parents=True, exist_ok=True)
        animated = raw.startswith((b'GIF87a', b'GIF89a'))
        key = hashlib.sha256(b'custom' + raw).hexdigest() + ('.gif' if animated else '.png')
        temporary = directory / ('favorite-' + uuid.uuid4().hex + '.tmp')
        destination = directory / key
        try:
            temporary.write_bytes(raw)
            temporary.replace(destination)
            data['items'][key] = {'name': '收藏动画' if animated else '收藏表情', 'group': 'custom'}
            try:
                save_library(data)
            except OSError:
                destination.unlink()
                raise
        finally:
            if temporary.exists():
                temporary.unlink()
        return True
    finally:
        _LIBRARY_LOCK.release()


class ImportImages(QThread):
    completed = Signal(int, int, str)

    def __init__(self, paths, parent, pack_name=None):
        super().__init__(parent)
        self.paths = paths
        self.pack_name = pack_name
        self.group = 'custom'

    def run(self):
        with _LIBRARY_LOCK:
            self._import_images()

    def _import_images(self):
        from app.ui.chat_images import prepare_image, library_dir, EXTENSIONS
        count = failed = used = total = 0
        error = ''
        try:
            directory = library_dir()
            directory.mkdir(parents=True, exist_ok=True)
            metadata = read_library()
            remaining = max(0, 300 - len(metadata['items']))
            if not remaining:
                raise ValueError('表情库最多保存 300 张，请先删除不用的表情。')
            if self.pack_name:
                self.group = uuid.uuid4().hex
                metadata['packs'][self.group] = self.pack_name[:60]

            def store(raw, name, group):
                nonlocal count, failed
                try:
                    data = image_bytes(prepare_image(raw))
                    # Deduplicate within a collection; the same image may belong to multiple packs.
                    suffix = '.gif' if data.startswith((b'GIF87a', b'GIF89a')) else '.png'
                    key = hashlib.sha256(group.encode() + data).hexdigest() + suffix
                    if key not in metadata['items']:
                        (directory / key).write_bytes(data)
                        metadata['items'][key] = {'name': name[:60], 'group': group}
                        count += 1
                except (ValueError, OSError):
                    failed += 1

            for path in self.paths:
                if used >= min(100, remaining) or self.isInterruptionRequested():
                    break
                try:
                    if path.suffix.lower() == '.zip':
                        group = uuid.uuid4().hex
                        metadata['packs'][group] = path.stem[:60]
                        self.group = group
                        with zipfile.ZipFile(path) as archive:
                            for entry in archive.infolist():
                                if used >= min(100, remaining) or total >= 64 * 1024 * 1024 or self.isInterruptionRequested():
                                    break
                                if entry.is_dir() or Path(entry.filename).suffix.lower() not in EXTENSIONS:
                                    continue
                                used += 1
                                if entry.file_size > MAX_ORIGINAL_BYTES:
                                    failed += 1
                                    continue
                                total += entry.file_size
                                # Never extract a supplied archive path.
                                store(archive.read(entry), Path(entry.filename).stem, group)
                    elif path.is_file() and path.suffix.lower() in EXTENSIONS:
                        used += 1
                        if path.stat().st_size > MAX_ORIGINAL_BYTES:
                            failed += 1
                        else:
                            store(path.read_bytes(), path.stem, self.group)
                except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
                    failed += 1
            metadata['packs'] = {k: v for k, v in metadata['packs'].items()
                                 if any(i['group'] == k for i in metadata['items'].values())}
            save_library(metadata)
        except Exception as exc:
            error = str(exc)
        self.completed.emit(count, failed, error)
