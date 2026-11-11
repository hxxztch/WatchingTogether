import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packaging'))
from prepare_release import plan


class ReleasePlanTests(unittest.TestCase):
    def setUp(self):
        self.release = {'draft': False, 'assets': [{'name': 'beta0.1.6.zip'}]}

    def test_new_version_builds_and_publishes(self):
        self.assertEqual(plan('beta0.1.7', 'new', None, None),
                         {'version': 'beta0.1.7', 'publish': True, 'build': True})

    def test_documentation_change_does_not_replace_published_version(self):
        self.assertFalse(plan('beta0.1.6', 'docs', 'old', self.release)['publish'])

    def test_retry_finishes_mirror_without_rebuilding(self):
        result = plan('beta0.1.6', 'old', 'old', self.release)
        self.assertTrue(result['publish'])
        self.assertFalse(result['build'])

    def test_manual_run_can_repair_mirror_after_later_commits(self):
        result = plan('beta0.1.6', 'docs', 'old', self.release, manual=True)
        self.assertTrue(result['publish'])
        self.assertFalse(result['build'])

    def test_existing_tag_cannot_be_moved(self):
        with self.assertRaises(ValueError):
            plan('beta0.1.7', 'new', 'old', None)

    def test_incomplete_release_rebuild_requires_same_tag_commit(self):
        self.assertTrue(plan('beta0.1.6', 'old', 'old', {'assets': []})['build'])
        with self.assertRaises(ValueError):
            plan('beta0.1.6', 'new', 'old', {'assets': []})

    def test_invalid_version_is_rejected(self):
        with self.assertRaises(ValueError):
            plan('0.1.7', 'new', None, None)
