import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from app.full_update import INVENTORY, prepare_full_update
from app.updates import find_update


def release(tag):
    base = 'https://github.com/hxxztch/WatchingTogether/releases/'
    return {'tag_name': tag, 'html_url': base + 'tag/' + tag, 'assets': [
        {'name': tag + '.zip', 'browser_download_url': base + 'download/' + tag + '/' + tag + '.zip',
         'digest': 'sha256:' + 'a' * 64, 'size': 10}]}


class ChannelsTests(unittest.TestCase):
    def test_channels_are_isolated_and_can_switch_back_to_lower_version(self):
        releases = [release('beta0.1.7'), release('test0.1.9')]
        self.assertIsNone(find_update(releases, 'beta0.1.7'))
        self.assertEqual(find_update(releases, 'beta0.1.7', channel='test').tag, 'test0.1.9')
        self.assertEqual(find_update(releases, 'test0.1.9', channel='stable').tag, 'beta0.1.7')
        self.assertIsNone(find_update(releases, 'test0.1.9'))

    def test_missing_channel_does_not_install_another_channel(self):
        self.assertIsNone(find_update([release('beta0.1.7')], 'beta0.1.6', channel='test'))

    def package(self, path, version, files):
        files = dict(files)
        files[INVENTORY] = json.dumps({'version': version, 'files': sorted(list(files) + [INVENTORY])}).encode()
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in files.items():
                archive.writestr('client/' + name, data)
        return files

    @unittest.skipUnless(os.name == 'nt', 'Windows transactional installer')
    def test_full_package_roundtrip_cleans_components_and_preserves_personal_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / 'install'
            install.mkdir()
            stable, test = root / 'stable.zip', root / 'test.zip'
            files = self.package(stable, 'beta0.1.7', {'stable.exe': b'stable', '_internal/core.dll': b'old'})
            self.package(test, 'test0.1.8', {'test.exe': b'test', '_internal/core.dll': b'new',
                                          '_internal/p2p.dll': b'rtc'})
            for name, data in files.items():
                path = install / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (install / 'config.json').write_bytes(b'{"nickname":"keep","update_channel":"test"}')
            (install / 'stickers').mkdir()
            (install / 'stickers/keep.gif').write_bytes(b'personal')
            (install / 'notes.txt').write_bytes(b'unknown personal file')
            for index, (package, old, target) in enumerate(((test, 'beta0.1.7', 'test0.1.8'),
                                                          (stable, 'test0.1.8', 'beta0.1.7'))):
                delta = root / ('delta%d.zip' % index)
                digest = 'sha256:' + hashlib.sha256(package.read_bytes()).hexdigest()
                prepare_full_update(package, install, old, target, digest, delta)
                result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(Path(__file__).resolve().parents[1] / 'packaging/apply_update.ps1'),
                    '-InstallDir', str(install), '-DeltaZip', str(delta), '-FromVersion', old,
                    '-ToVersion', target, '-NoRestart'], capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('keep', (install / 'config.json').read_text())
                self.assertEqual((install / 'stickers/keep.gif').read_bytes(), b'personal')
                self.assertEqual((install / 'notes.txt').read_bytes(), b'unknown personal file')
            self.assertFalse((install / 'test.exe').exists())
            self.assertFalse((install / '_internal/p2p.dll').exists())
            self.assertEqual((install / '_internal/core.dll').read_bytes(), b'old')

    def test_bad_digest_and_protected_files_are_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'bad.zip'
            self.package(package, 'test0.1.7', {'config.json': b'bad'})
            with self.assertRaises(ValueError):
                prepare_full_update(package, root, 'beta0.1.7', 'test0.1.7', 'sha256:bad', root / 'delta.zip')
            with self.assertRaisesRegex(ValueError, 'Protected'):
                prepare_full_update(package, root, 'beta0.1.7', 'test0.1.7',
                    'sha256:' + hashlib.sha256(package.read_bytes()).hexdigest(), root / 'delta.zip')
            self.assertFalse((root / 'config.json').exists())
            self.assertFalse((root / 'delta.zip').exists())
