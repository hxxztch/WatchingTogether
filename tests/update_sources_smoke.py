"""Real Qt HTTP checks for provider switching and multipart/delta downloads."""
import hashlib
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import zipfile
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWidgets import QApplication, QMessageBox
from app.ui.settings import SettingsPage
from app.updates import GITEE_PAUSED_MESSAGE
from app.version import CLIENT_VERSION
import app.config as config

_parts = [int(value) for value in CLIENT_VERSION[4:].split('.')]
NEXT_VERSION = 'beta{}.{}.{}'.format(_parts[0], _parts[1], _parts[2] + 1)


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def main():
    app = QApplication([])
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(str(value))
    data = b'complete portable zip fixture'
    chunks = (data[:12], data[12:])
    delta_file = io.BytesIO()
    with zipfile.ZipFile(delta_file, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({
            'schema': 1, 'from_version': CLIENT_VERSION, 'to_version': NEXT_VERSION,
            'files': [{'path': 'baseline.dll', 'old_sha256': hashlib.sha256(b'official').hexdigest()}],
            'removed': [],
        }))
    delta = delta_file.getvalue()
    base = 'https://github.com/hxxztch/WatchingTogether/releases/download/'
    full = {'name': NEXT_VERSION + '.zip', 'browser_download_url': base + '1/full.001',
            'digest': sha(data), 'size': len(data),
            'parts': [{'url': base + str(i + 1) + '/full.00' + str(i + 1),
                       'digest': sha(chunk), 'size': len(chunk)} for i, chunk in enumerate(chunks)]}
    diff = {'name': CLIENT_VERSION + '-to-' + NEXT_VERSION + '.delta.zip',
            'browser_download_url': base + '3/change.delta.zip', 'digest': sha(delta), 'size': len(delta)}
    release = {'tag_name': NEXT_VERSION, 'html_url': 'https://github.com/hxxztch/WatchingTogether/releases/tag/' + NEXT_VERSION,
               'assets': [full, diff]}
    test_version = 'test' + NEXT_VERSION[4:]
    test_release = {'tag_name': test_version,
        'html_url': 'https://github.com/hxxztch/WatchingTogether/releases/tag/' + test_version,
        'assets': [dict(full, name=test_version + '.zip')]}
    state = {'bad': False, 'fail_feed': False, 'interrupt': None}
    calls = []
    ranges = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            path = urlsplit(self.path).path
            status = 200
            if path.endswith('/releases.json'):
                status = 404 if state['fail_feed'] else 200
                content = json.dumps([release, test_release]).encode()
            elif path.endswith('/releases'):
                content = json.dumps([release, test_release]).encode()
            elif path.endswith('full.001'):
                content = chunks[0]
            elif path.endswith('full.002'):
                content = b'x' * len(chunks[1]) if state['bad'] else chunks[1]
                requested = self.headers.get('Range')
                if requested:
                    ranges.append(requested)
                    if state['interrupt'] != 'restart':
                        offset = int(requested[6:-1])
                        self.send_response(206)
                        start = offset - 1 if state['interrupt'] == 'bad_range' else offset
                        self.send_header('Content-Range', 'bytes {}-{}/{}'.format(start, len(content) - 1, len(content)))
                        self.send_header('Content-Length', str(len(content) - offset))
                        self.end_headers()
                        self.wfile.write(content[offset:])
                        return
                elif state['interrupt'] and not ranges:
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(content)))
                    self.end_headers()
                    self.wfile.write(content[:5])
                    self.wfile.flush()
                    time.sleep(.8)
                    self.close_connection = True
                    return
            elif path.endswith('change.delta.zip'):
                content = delta
            else:
                content = b'[]'  # GitHub feed: no newer release.
            self.send_response(status)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def local_request(self, url, timeout):
        parsed = urlsplit(str(url))
        request = QNetworkRequest(QUrl('http://127.0.0.1:{}{}{}'.format(
            server.server_port, parsed.path, '?' + parsed.query if parsed.query else '')))
        if timeout >= 120000 and state['interrupt']:
            request.setTransferTimeout(300)
        return request

    def wait(check):
        end = time.monotonic() + 10
        while not check():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < end, 'Updater UI timed out'
            time.sleep(.01)
        app.processEvents()

    original_config = config.CONFIG_PATH
    try:
        with tempfile.TemporaryDirectory() as temporary, patch.object(SettingsPage, '_request', local_request), \
                patch.object(QStandardPaths, 'writableLocation', return_value=temporary):
            config.CONFIG_PATH = str(Path(temporary) / 'config.json')
            config.save(update_channel='stable')
            page = SettingsPage()
            page.show()
            assert page.source_combo.currentData() == 'github'
            page.check_updates()
            wait(lambda: page._check_reply is None)
            assert page._release and page._release.source == 'github'
            page.channel_combo.setCurrentIndex(page.channel_combo.findData('test'))
            wait(lambda: page._check_reply is None)
            assert page._release.tag == test_version and not page._release.delta_url
            assert config.load()['update_channel'] == 'test'
            page.channel_combo.setCurrentIndex(page.channel_combo.findData('stable'))
            wait(lambda: page._check_reply is None)
            assert page._release.tag == NEXT_VERSION
            page.download_update()
            assert not page.source_combo.isEnabled()
            wait(lambda: not page._downloading)
            assert page._target.read_bytes() == data and page.source_combo.isEnabled()
            assert not page.install_button.isVisible()  # Source runs never install over the workspace.
            for mode in ('resume', 'restart', 'bad_range'):
                start = len(calls)
                ranges.clear()
                state['interrupt'] = mode
                page.download_update()
                wait(lambda: not page._downloading)
                assert ranges == ['bytes=5-'], (mode, ranges)
                assert sum(call.endswith('full.001') for call in calls[start:]) == 1
                assert page._target.read_bytes() == data and not page._partial.exists()
                assert ('续传范围' in page.status.text() if mode == 'bad_range'
                        else page.status.text().startswith('下载完成')), (mode, page.status.text())
            state['interrupt'] = None
            state['bad'] = True
            page.download_update()
            wait(lambda: not page._downloading)
            assert '校验失败' in page.status.text()
            assert page._target.read_bytes() == data and not page._partial.exists()
            state['bad'] = False
            with patch.object(sys, 'frozen', True, create=True):
                page.download_update()
                wait(lambda: not page._downloading)
                assert page._target.read_bytes() == delta and page.install_button.isVisible()
                install = Path(temporary) / 'install'
                install.mkdir()
                baseline = install / 'baseline.dll'
                baseline.write_bytes(b'official')
                with patch.object(sys, 'executable', str(install / 'client.exe')), \
                        patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                        patch.object(page, '_launch_install') as launch:
                    page.install_update()
                    wait(lambda: page._prepare_worker is None)
                    launch.assert_called_once_with(page._target)
                    launch.reset_mock()
                    baseline.write_bytes(b'local rebuild')
                    page.install_update()
                    wait(lambda: page._prepare_worker is None and not page._downloading)
                    launch.assert_not_called()
                    assert page._force_full and not page._download_is_delta
                    assert page._target.read_bytes() == data and page.install_button.isVisible()
                    assert baseline.read_bytes() == b'local rebuild'
            request_count = len(calls)
            page.source_combo.setCurrentIndex(page.source_combo.findData('gitee'))
            page.check_updates()
            app.processEvents()
            assert page._release is None and not page.install_button.isVisible()
            assert page.status.text() == GITEE_PAUSED_MESSAGE
            assert len(calls) == request_count and page._check_reply is None
            assert config.load()['update_source'] == 'gitee'
            restored = SettingsPage()
            restored.check_updates(True)
            assert restored.source_combo.currentData() == 'gitee'
            assert restored.status.text() == GITEE_PAUSED_MESSAGE and restored._check_reply is None
            restored.stop()
            restored.close()
            state['fail_feed'] = True
            page.source_combo.setCurrentIndex(page.source_combo.findData('github'))
            wait(lambda: page._check_reply is None)
            assert page._release and page._check_source == 'api'
            assert any('/repos/hxxztch/WatchingTogether/releases?' in call for call in calls)
            page.stop()
            page.close()
            assert not errors, errors
            print('PASS: GitHub default and API fallback; paused Gitee sends no requests; resume, verification and delta installation')
    finally:
        config.CONFIG_PATH = original_config
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
