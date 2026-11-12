"""Convert a verified portable ZIP into a transactional update of this installation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

INVENTORY = '_internal/package-files.json'
PROTECTED = {'config.json', 'crash.log', 'crash.log.1', 'crash.log.2', 'crash.log.3',
             'fatal.log', 'fatal.log.1'}


def safe_path(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or
            any(part in ('', '.', '..') for part in name.split('/')) or
            name.startswith('/') or any(ord(c) < 32 for c in name) or name.rstrip(' .') != name or
            any(part.rstrip(' .') != part for part in name.split('/'))):
        raise ValueError('Unsafe package path')
    if name.lower() in PROTECTED or name.split('/')[0].lower() == 'stickers':
        raise ValueError('Protected personal file in package')
    return name


def file_hash(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def prepare_full_update(package, install, current, target, expected, output, cancelled=lambda: False):
    """Read application inventory only; unknown files and personal data stay untouched."""
    package, install, output = Path(package), Path(install).resolve(), Path(output)
    if expected != 'sha256:' + file_hash(package):
        raise ValueError('Full package SHA256 mismatch')
    with zipfile.ZipFile(package) as archive:
        files, seen, roots = {}, set(), set()
        total = 0
        for item in archive.infolist():
            if item.is_dir():
                continue
            root, slash, relative = item.filename.partition('/')
            if not slash or root in ('', '.', '..') or '\\' in root or ':' in root:
                raise ValueError('Invalid portable package root')
            safe_path(relative)
            if relative.lower() in seen or item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError('Duplicate or linked package file')
            seen.add(relative.lower())
            roots.add(root)
            total += item.file_size
            if total > 4 * 1024 ** 3 or len(files) > 30000:
                raise ValueError('Portable package is too large')
            files[relative] = item
        if len(roots) != 1 or INVENTORY not in files:
            raise ValueError('Package has no application inventory')
        inventory_item = files[INVENTORY]
        if inventory_item.file_size > 4 * 1024 ** 2:
            raise ValueError('Application inventory is too large')
        inventory = json.loads(archive.read(inventory_item))
        if inventory.get('version') != target or sorted(inventory.get('files', [])) != sorted(files):
            raise ValueError('Package version or inventory mismatch')
        old_path = install / INVENTORY
        old = json.loads(old_path.read_text(encoding='utf-8'))
        if old.get('version') != current or not isinstance(old.get('files'), list):
            raise ValueError('Installed application inventory mismatch')
        old_files = [safe_path(name) for name in old['files']]
        if len({name.lower() for name in old_files}) != len(old_files):
            raise ValueError('Duplicate installed file')
        def destination(name):
            path = install.joinpath(*PurePosixPath(name).parts)
            if install not in path.resolve().parents:
                raise ValueError('Update path escaped installation')
            return path
        manifest = {'schema': 1, 'from_version': current, 'to_version': target,
                    'files': [], 'removed': []}
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED) as delta:
            for name, item in files.items():
                if cancelled():
                    raise ValueError('Update preparation cancelled')
                path = destination(name)
                previous = file_hash(path) if path.is_file() else None
                checksum = hashlib.sha256()
                with archive.open(item) as source, delta.open('files/' + name, 'w') as dest:
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        if cancelled():
                            raise ValueError('Update preparation cancelled')
                        checksum.update(chunk)
                        dest.write(chunk)
                manifest['files'].append({'path': name, 'sha256': checksum.hexdigest(),
                                          'old_sha256': previous})
            for name in sorted(set(old_files) - set(files)):
                path = destination(name)
                if path.is_file():
                    manifest['removed'].append({'path': name, 'old_sha256': file_hash(path)})
            delta.writestr('manifest.json', json.dumps(manifest))
    return output
