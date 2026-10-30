"""The published helper must be self-contained and readable by Windows PowerShell."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_update_repair', ROOT / 'packaging/build_update_repair.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RepairPackageTests(unittest.TestCase):
    def test_helper_contents_encoding_and_checksums_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = builder.build(root / 'first')
            second = builder.build(root / 'second')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            digest = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertTrue(first.with_suffix('.zip.sha256.txt').read_text(encoding='utf-8').startswith(digest + '  '))
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), len(builder.FILES))
                prefix = builder.VERSION + '-更新修复助手/'
                for name in builder.FILES:
                    content = archive.read(prefix + name)
                    if name.endswith('.ps1'):
                        self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
                    if name.endswith('.cmd'):
                        self.assertIn(b'-STA', content)
                        self.assertIn(b'%~dp0repair_update.ps1', content)
                    self.assertNotIn(b'\n', content.replace(b'\r\n', b''))
                self.assertIsNone(archive.testzip())


if __name__ == '__main__':
    unittest.main()
