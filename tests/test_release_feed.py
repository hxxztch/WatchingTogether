"""A published static index must retain delta and digest data for old clients."""
import importlib.util
from pathlib import Path
import unittest

from app.updates import find_update


spec = importlib.util.spec_from_file_location(
    "publish_update_feed", Path(__file__).resolve().parents[1] /
    "packaging" / "publish_update_feed.py")
feed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feed_module)


class ReleaseFeedTests(unittest.TestCase):
    def test_published_index_selects_matching_delta(self):
        tag = "beta0.1.2"
        base = "https://github.com/hxxztch/WatchingTogether/releases/download/" + tag + "/"
        assets = [
            {"name": tag + ".zip", "browser_download_url": base + tag + ".zip",
             "digest": "sha256:" + "a" * 64, "size": 100},
            {"name": "beta0.1.1-to-beta0.1.2.delta.zip",
             "browser_download_url": base + "beta0.1.1-to-beta0.1.2.delta.zip",
             "digest": "sha256:" + "b" * 64, "size": 10},
        ]
        releases = [{"tag_name": tag, "draft": False,
                     "html_url": "https://github.com/hxxztch/WatchingTogether/releases/tag/" + tag,
                     "assets": assets},
                    {"tag_name": "beta0.1.3", "draft": True, "assets": assets}]
        index = feed_module.make_feed(releases)
        self.assertEqual(len(index), 1)
        selected = find_update(index, "beta0.1.1")
        self.assertEqual(selected.tag, tag)
        self.assertEqual(selected.delta_digest, "sha256:" + "b" * 64)
        self.assertIsNone(find_update(index, tag))


if __name__ == "__main__":
    unittest.main()
