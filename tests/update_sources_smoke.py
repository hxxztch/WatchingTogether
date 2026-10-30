"""Real Qt HTTP checks for provider switching and multipart/delta downloads."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWidgets import QApplication
from app.ui.settings import SettingsPage
from app.updates import MANIFEST_START, MANIFEST_END
from app.version import CLIENT_VERSION
import app.config as config


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def main():
    app = QApplication([])
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(str(value))
    data = b'complete portable zip fixture'
    chunks = (data[:12], data[12:])
    delta = b'only changed files fixture'
    base = 'https://gitee.com/attachments/download/'
    full = {'name': 'beta0.1.5.zip', 'browser_download_url': base + '1/full.001',
            'digest': sha(data), 'size': len(data),
            'parts': [{'url': base + str(i + 1) + '/full.00' + str(i + 1),
                       'digest': sha(chunk), 'size': len(chunk)} for i, chunk in enumerate(chunks)]}
    diff = {'name': CLIENT_VERSION + '-to-beta0.1.5.delta.zip',
            'browser_download_url': base + '3/change.delta.zip', 'digest': sha(delta), 'size': len(delta)}
    release = {'tag_name': 'beta0.1.5', 'html_url': 'https://gitee.com/hxxztch/watching-together/releases/beta0.1.5',
               'assets': [full, diff]}
    state = {'bad': False, 'fail_feed': False}
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            path = urlsplit(self.path).path
            status = 200
            if path.endswith('/contents/releases.json'):
                status = 404 if state['fail_feed'] else 200
                content = json.dumps({'encoding': 'base64', 'content': base64.b64encode(json.dumps([release]).encode()).decode()}).encode()
            elif path.endswith('/releases'):
                body = MANIFEST_START + base64.b64encode(json.dumps(release).encode()).decode() + MANIFEST_END
                content = json.dumps([{'tag_name': 'beta0.1.5', 'body': body}]).encode()
            elif path.endswith('full.001'):
                content = chunks[0]
            elif path.endswith('full.002'):
                content = b'x' * len(chunks[1]) if state['bad'] else chunks[1]
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
        return QNetworkRequest(QUrl('http://127.0.0.1:{}{}{}'.format(
            server.server_port, parsed.path, '?' + parsed.query if parsed.query else '')))

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
            page = SettingsPage()
            page.show()
            assert page.source_combo.currentData() == 'gitee'
            page.check_updates()
            wait(lambda: page._check_reply is None)
            assert page._release and page._release.source == 'gitee'
            page.download_update()
            assert not page.source_combo.isEnabled()
            wait(lambda: not page._downloading)
            assert page._target.read_bytes() == data and page.source_combo.isEnabled()
            assert not page.install_button.isVisible()  # Source runs never install over the workspace.
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
            page.source_combo.setCurrentIndex(page.source_combo.findData('github'))
            wait(lambda: page._check_reply is None)
            assert page._release is None and not page.install_button.isVisible()
            assert config.load()['update_source'] == 'github'
            state['fail_feed'] = True
            page.source_combo.setCurrentIndex(page.source_combo.findData('gitee'))
            wait(lambda: page._check_reply is None)
            assert page._release and page._check_source == 'api'
            assert any('/api/v5/repos/' in call and '/releases?' in call for call in calls)
            page.stop()
            page.close()
            restored = SettingsPage()
            assert restored.source_combo.currentData() == 'gitee'
            restored.stop()
            restored.close()
            assert not errors, errors
            print('PASS: default/persisted source; provider API fallback; multipart merge/hash; corrupt part preserves prior ZIP; delta download/install controls')
    finally:
        config.CONFIG_PATH = original_config
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
