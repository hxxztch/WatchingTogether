"""Select client updates from the public GitHub Releases feed."""
from dataclasses import dataclass
import re

from app.version import CLIENT_VERSION


RELEASES_API = "https://api.github.com/repos/hxxztch/WatchingTogether/releases?per_page=30"
RELEASES_FEED = "https://raw.githubusercontent.com/hxxztch/WatchingTogether/update-feed/releases.json"
RELEASES_PAGE = "https://github.com/hxxztch/WatchingTogether/releases"
ASSET_PREFIX = "https://github.com/hxxztch/WatchingTogether/releases/download/"
_VERSION = re.compile(r"^(beta|v)(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class ClientRelease:
    tag: str
    page_url: str
    asset_name: str
    asset_url: str
    digest: str
    size: int
    delta_name: str = ""
    delta_url: str = ""
    delta_digest: str = ""
    manifest_url: str = ""


def version_key(tag):
    match = _VERSION.fullmatch(tag or "")
    if not match:
        return None
    return match.group(1), tuple(int(part) for part in match.groups()[1:])


def find_update(releases, current=CLIENT_VERSION):
    """Return the newest newer client release on this installation's channel."""
    installed = version_key(current)
    if installed is None:
        raise ValueError("Unknown installed client version: " + current)
    newest = None
    newest_version = installed[1]
    for item in releases:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = item.get("tag_name", "")
        parsed = version_key(tag)
        if parsed is None or parsed[0] != installed[0] or parsed[1] <= newest_version:
            continue
        assets = item.get("assets") or []
        asset = next((a for a in assets if isinstance(a, dict) and
                      a.get("name") == tag + ".zip" and
                      str(a.get("browser_download_url", "")).startswith(ASSET_PREFIX)), None)
        if asset is None:
            continue
        page_url = item.get("html_url", "")
        if not isinstance(page_url, str) or not page_url.startswith(RELEASES_PAGE + "/tag/"):
            continue
        delta_name = current + "-to-" + tag + ".delta.zip"
        manifest_name = current + "-to-" + tag + ".delta.json"
        delta = next((a for a in assets if isinstance(a, dict) and
                      a.get("name") == delta_name and
                      str(a.get("browser_download_url", "")).startswith(ASSET_PREFIX)), None)
        manifest = next((a for a in assets if isinstance(a, dict) and
                         a.get("name") == manifest_name and
                         str(a.get("browser_download_url", "")).startswith(ASSET_PREFIX)), None)
        newest = ClientRelease(tag, page_url, asset["name"],
                               asset["browser_download_url"], asset.get("digest") or "",
                               int(asset.get("size") or 0),
                               delta_name if delta else "",
                               delta["browser_download_url"] if delta else "",
                               (delta.get("digest") or "") if delta else "",
                               manifest["browser_download_url"] if manifest else "")
        newest_version = parsed[1]
    return newest
