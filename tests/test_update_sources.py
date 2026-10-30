"""Source isolation, authenticated metadata and multipart artifact integrity."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.updates import (DEFAULT_SOURCE, MANIFEST_START, MANIFEST_END,
                         decode_release_feed, find_update, valid_download_url)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish_gitee', ROOT / 'packaging/publish_gitee.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def gitee_release(tag='beta0.1.4'):
    return {'tag_name': tag, 'html_url': 'https://gitee.com/hxxztch/watching-together/releases/' + tag,
            'assets': [{'name': tag + '.zip', 'browser_download_url': 'https://gitee.com/attachments/download/1/full.zip.001',
                        'digest': 'sha256:' + 'a' * 64, 'size': 5,
                        'parts': [{'url': 'https://gitee.com/attachments/download/1/full.zip.001',
                                   'digest': 'sha256:' + 'b' * 64, 'size': 3},
                                  {'url': 'https://gitee.com/attachments/download/2/full.zip.002',
                                   'digest': 'sha256:' + 'c' * 64, 'size': 2}]}]}


class UpdateSourceTests(unittest.TestCase):
    def test_gitee_default_and_same_channel_version_selection(self):
        self.assertEqual(DEFAULT_SOURCE, 'gitee')
        item = gitee_release()
        selected = find_update([item], 'beta0.1.3', source='gitee')
        self.assertEqual(selected.tag, 'beta0.1.4')
        self.assertEqual([part.size for part in selected.download_parts()], [3, 2])
        self.assertIsNone(find_update([item], 'beta0.1.4', source='gitee'))
        self.assertIsNone(find_update([item], 'v0.1.3', source='gitee'))

    def test_feed_and_release_api_fallback_have_identical_integrity_metadata(self):
        item = gitee_release()
        encoded = base64.b64encode(json.dumps([item]).encode()).decode()
        self.assertEqual(decode_release_feed({'encoding': 'base64', 'content': encoded}, 'gitee'), [item])
        marker = MANIFEST_START + base64.b64encode(json.dumps(item).encode()).decode() + MANIFEST_END
        self.assertEqual(decode_release_feed([{'tag_name': item['tag_name'], 'body': marker}], 'gitee', api=True), [item])
        with self.assertRaises(ValueError):
            decode_release_feed([{'tag_name': 'beta0.1.5', 'body': marker}], 'gitee', api=True)

    def test_provider_urls_and_redirects_cannot_cross_or_escape_hosts(self):
        self.assertFalse(valid_download_url('https://github.com/hxxztch/WatchingTogether/releases/download/x/a', 'gitee', True))
        for url in ('http://gitee.com/a', 'https://gitee.com.evil.test/a',
                    'https://secret@gitee.com/attachments/download/1/a', 'https://gitee.com:8443/a'):
            self.assertFalse(valid_download_url(url, 'gitee', True))
        self.assertTrue(valid_download_url('https://release-assets.githubusercontent.com/a', 'github', True))
        self.assertFalse(valid_download_url('https://gitee.com/attachments/download/1/a', 'github', True))

    def test_bad_parts_missing_hash_and_wrong_provider_are_rejected(self):
        for change in ('size', 'digest', 'url'):
            item = deepcopy(gitee_release())
            part = item['assets'][0]['parts'][0]
            part[change] = {'size': 4, 'digest': '', 'url': 'https://other.test/a'}[change]
            with self.assertRaises(ValueError):
                find_update([item], 'beta0.1.3', source='gitee')
        item = gitee_release()
        item['assets'][0]['digest'] = ''
        with self.assertRaises(ValueError):
            find_update([item], 'beta0.1.3', source='gitee')

    def test_publish_split_is_lossless_and_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'beta0.1.4.zip'
            data = b'portable client bytes' * 20
            original.write_bytes(data)
            parts = publisher.split_asset(original, root / 'parts', limit=17)
            self.assertTrue(all(p.stat().st_size <= 17 for p in parts))
            self.assertEqual(b''.join(p.read_bytes() for p in parts), data)
            self.assertEqual(publisher.digest(original), 'sha256:' + hashlib.sha256(data).hexdigest())

    def test_gitee_required_release_fields_and_missing_feed_array(self):
        calls = []

        class FakeGitee:
            def __init__(self, token):
                pass

            def api(self, method, suffix, payload=None, **kwargs):
                calls.append((method, suffix, payload))
                if suffix.startswith('/releases/tags/'):
                    return {'id': 1}
                if suffix.endswith('/attach_files'):
                    return []
                if method == 'PATCH':
                    assert payload['tag_name'] == payload['name'] == 'beta0.1.4'
                if method == 'GET' and suffix == '/contents/releases.json':
                    return []  # Actual Gitee missing-path response.
                return None

            def upload(self, release_id, path, existing):
                return {'url': 'https://gitee.com/attachments/download/1/' + path.name,
                        'digest': publisher.digest(path), 'size': path.stat().st_size}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '更新日志.txt').write_text('beta0.1.4（2026-10-30）\nTest release\n', encoding='utf-8')
            files = root / 'assets'
            files.mkdir()
            (files / 'beta0.1.4.zip').write_bytes(b'portable')
            with patch.object(publisher, 'ROOT', root), patch.object(publisher, 'Gitee', FakeGitee):
                publisher.publish('beta0.1.4', files, 'test-only')
            self.assertTrue(any(method == 'POST' and path == '/branches' for method, path, _ in calls))
            posted = next(payload for method, path, payload in calls if method == 'POST' and path == '/contents/releases.json')
            feed = json.loads(base64.b64decode(posted['content']))
            self.assertEqual(find_update(feed, 'beta0.1.3', 'gitee').tag, 'beta0.1.4')


if __name__ == '__main__':
    unittest.main()
