"""Build the standalone, Windows-native beta0.1.4 repair assistant."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'beta0.1.4'
FILES = ('repair_update.cmd', 'repair_update.ps1', 'apply_update.ps1', '修复升级说明.txt')


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / (VERSION + '-更新修复助手.zip')
    prefix = VERSION + '-更新修复助手/'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in FILES:
            text = (ROOT / 'packaging' / name).read_text(encoding='utf-8-sig')
            content = text.replace('\r\n', '\n').replace('\n', '\r\n').encode(
                'ascii' if name.endswith('.cmd') else 'utf-8-sig')
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 10, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=6)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name in ('apply_update.ps1', 'repair_update.ps1'):
            assert archive.read(prefix + name).startswith(b'\xef\xbb\xbf')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256.txt').write_text(digest + '  ' + target.name + '\n', encoding='utf-8')
    print('Built repair assistant: ' + str(target), flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/update-repair')
    build(parser.parse_args().output)
