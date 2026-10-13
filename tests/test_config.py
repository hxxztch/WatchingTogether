import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import config


class ConfigTests(unittest.TestCase):
    def test_invalid_shapes_and_types_restore_defaults(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
            for value in [[], None, 123, {'nickname': 17, 'server': None}]:
                Path(config.CONFIG_PATH).write_text(json.dumps(value), encoding='utf-8')
                self.assertEqual(config.load()['server'], 'ws://localhost:9877')
                self.assertEqual(config.load()['nickname'], '')

    def test_atomic_replace_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'CONFIG_PATH', str(Path(directory) / 'config.json')):
            self.assertTrue(config.save(nickname='before', bili_cookie='synthetic-test-value'))
            original = Path(config.CONFIG_PATH).read_bytes()
            with patch.object(config.os, 'replace', side_effect=PermissionError):
                self.assertFalse(config.save(nickname='after'))
            self.assertEqual(Path(config.CONFIG_PATH).read_bytes(), original)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
            self.assertTrue(config.save(nickname='after'))
            self.assertEqual(config.load()['bili_cookie'], 'synthetic-test-value')
            self.assertEqual(config.load()['nickname'], 'after')
