"""Explicit post-publication acceptance against real public update endpoints."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication
import app.config as config
import app.ui.settings as settings
from app.updates import find_update


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['gitee', 'github', 'both'], default='both')
    parser.add_argument('--current', default='beta0.1.3')
    parser.add_argument('--download', choices=['check', 'delta', 'full'], default='delta')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/online-updates')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(str(value))

    def wait(check, page):
        end = time.monotonic() + 600
        report = time.monotonic() + 15
        while not check():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < end, 'Online update timed out'
            if time.monotonic() >= report:
                print(page.status.text(), flush=True)
                report = time.monotonic() + 15
            time.sleep(.02)
        app.processEvents()

    original_config = config.CONFIG_PATH
    results = []
    try:
        for source in (['gitee', 'github'] if args.source == 'both' else [args.source]):
            with tempfile.TemporaryDirectory() as temporary, \
                    patch.object(settings, 'CLIENT_VERSION', args.current), \
                    patch.object(settings, 'find_update', side_effect=lambda releases, source: find_update(releases, args.current, source)), \
                    patch.object(sys, 'frozen', args.download == 'delta', create=True), \
                    patch.object(QStandardPaths, 'writableLocation', return_value=str(args.output / source)):
                config.CONFIG_PATH = str(Path(temporary) / 'config.json')
                assert config.save(update_source=source)
                page = settings.SettingsPage()
                try:
                    page.resize(1000, 650)
                    page.show()
                    page.check_updates()
                    wait(lambda: page._check_reply is None, page)
                    assert page._release is not None, page.status.text()
                    result = {'source': source, 'tag': page._release.tag, 'check_path': page._check_source}
                    if args.download != 'check':
                        if args.download == 'delta':
                            assert page._release.delta_url, 'No applicable delta'
                        page.download_update()
                        wait(lambda: not page._downloading, page)
                        assert page.status.text().startswith('下载完成'), page.status.text()
                        with zipfile.ZipFile(page._target) as archive:
                            assert archive.testzip() is None
                        result.update(file=str(page._target), size=page._target.stat().st_size,
                                      sha256=hashlib.sha256(page._target.read_bytes()).hexdigest())
                    page.grab().save(str(args.output / (source + '-settings.png')))
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                    results.append(result)
                finally:
                    page.stop()
                    page.close()
                    app.processEvents()
        assert not errors, errors
        (args.output / ('verified-' + args.download + '.json')).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        config.CONFIG_PATH = original_config


if __name__ == '__main__':
    main()
