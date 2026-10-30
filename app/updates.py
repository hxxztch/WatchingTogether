"""Provider-specific release selection and verified multipart download plans."""
import base64
from dataclasses import dataclass
import json
import re
from urllib.parse import urlsplit

from app.version import CLIENT_VERSION


@dataclass(frozen=True)
class UpdateSource:
    name: str
    feed_url: str
    api_url: str
    page_url: str


SOURCES = {
    'gitee': UpdateSource('Gitee',
        'https://gitee.com/api/v5/repos/hxxztch/watching-together/contents/releases.json?ref=update-feed',
        'https://gitee.com/api/v5/repos/hxxztch/watching-together/releases?per_page=30',
        'https://gitee.com/hxxztch/watching-together/releases'),
    'github': UpdateSource('GitHub',
        'https://raw.githubusercontent.com/hxxztch/WatchingTogether/update-feed/releases.json',
        'https://api.github.com/repos/hxxztch/WatchingTogether/releases?per_page=30',
        'https://github.com/hxxztch/WatchingTogether/releases'),
}
DEFAULT_SOURCE = 'gitee'
RELEASES_API = SOURCES['github'].api_url
RELEASES_FEED = SOURCES['github'].feed_url
RELEASES_PAGE = SOURCES['github'].page_url
ASSET_PREFIX = RELEASES_PAGE + '/download/'
VERSION_PATTERN = r'(?:beta|v)\d+\.\d+\.\d+'
_VERSION = re.compile(r'^(beta|v)(\d+)\.(\d+)\.(\d+)$')
_DIGEST = re.compile(r'^sha256:[0-9a-fA-F]{64}$')
MANIFEST_START = '<!-- WatchingTogether-Update:'
MANIFEST_END = ' -->'


@dataclass(frozen=True)
class DownloadPart:
    url: str
    digest: str
    size: int


@dataclass(frozen=True)
class ClientRelease:
    tag: str
    page_url: str
    asset_name: str
    asset_url: str
    digest: str
    size: int
    delta_name: str = ''
    delta_url: str = ''
    delta_digest: str = ''
    manifest_url: str = ''
    parts: tuple = ()
    delta_parts: tuple = ()
    delta_size: int = 0
    source: str = 'github'

    def download_parts(self, delta=False):
        if delta:
            return self.delta_parts or (DownloadPart(self.delta_url, self.delta_digest, self.delta_size),)
        return self.parts or (DownloadPart(self.asset_url, self.digest, self.size),)


def version_key(tag):
    match = _VERSION.fullmatch(tag or '')
    if not match:
        return None
    return match.group(1), tuple(int(part or 0) for part in match.groups()[1:])


def valid_download_url(url, source, redirect=False):
    """Never silently download from another provider or arbitrary HTTPS hosts."""
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
    except ValueError:
        return False
    host = (parsed.hostname or '').lower()
    if source == 'github':
        if redirect:
            return host == 'github.com' or host.endswith('.githubusercontent.com')
        return host == 'github.com' and parsed.path.startswith('/hxxztch/WatchingTogether/releases/download/')
    if source != 'gitee':
        return False
    if redirect:
        return host in ('gitee.com', 'api.gitee.com') or host.endswith('.gitee.com')
    return host == 'gitee.com' and parsed.path.startswith((
        '/hxxztch/watching-together/releases/download/', '/attachments/download/',
        '/api/v5/repos/hxxztch/watching-together/releases/'))


def decode_release_feed(payload, source, api=False):
    if source == 'gitee' and not api:
        if not isinstance(payload, dict) or payload.get('encoding') != 'base64':
            raise ValueError('无效的 Gitee 更新清单')
        raw = base64.b64decode(payload.get('content', ''), validate=False)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('更新清单过大')
        payload = json.loads(raw.decode('utf-8'))
    if not isinstance(payload, list):
        raise ValueError('无效的发布信息')
    if source == 'gitee' and api:
        result = []
        for item in payload:
            if not isinstance(item, dict) or item.get('draft'):
                continue
            body = item.get('body') or ''
            if not isinstance(body, str):
                raise ValueError('无效的发行说明')
            if MANIFEST_START not in body:
                continue
            encoded = body.split(MANIFEST_START, 1)[1].split(MANIFEST_END, 1)[0]
            data = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
            if not isinstance(data, dict) or data.get('tag_name') != item.get('tag_name'):
                raise ValueError('发行版与更新清单版本不一致')
            result.append(data)
        if payload and not result:
            raise ValueError('Gitee 发行版尚未提供可校验的更新清单')
        return result
    return payload


def _asset(assets, name, source):
    if not isinstance(assets, list):
        raise ValueError('无效的更新文件清单')
    item = next((a for a in assets if isinstance(a, dict) and a.get('name') == name), None)
    if item is None:
        return None
    if not valid_download_url(item.get('browser_download_url'), source):
        raise ValueError('更新文件地址不属于所选更新源')
    size = int(item.get('size') or 0)
    digest = item.get('digest') or ''
    if size < 0 or size > 2 * 1024 ** 3:
        raise ValueError('无效的更新文件大小')
    if not isinstance(digest, str):
        raise ValueError('无效的校验信息')
    if source == 'gitee' and (not _DIGEST.fullmatch(digest) or not size):
        raise ValueError('Gitee 更新文件缺少校验信息')
    parts = []
    if item.get('parts'):
        if not isinstance(item['parts'], list) or not _DIGEST.fullmatch(digest) or not 1 <= len(item['parts']) <= 32:
            raise ValueError('无效的分段更新信息')
        for part in item['parts']:
            if (not isinstance(part, dict) or not valid_download_url(part.get('url'), source) or
                    not _DIGEST.fullmatch(part.get('digest', '')) or
                    not 0 < int(part.get('size', 0)) <= 100_000_000):
                raise ValueError('无效的更新分段')
            parts.append(DownloadPart(part['url'], part['digest'], int(part['size'])))
        if sum(p.size for p in parts) != size:
            raise ValueError('更新分段大小不一致')
    return item, tuple(parts)


def find_update(releases, current=CLIENT_VERSION, source='github'):
    installed = version_key(current)
    if installed is None or source not in SOURCES:
        raise ValueError('Unknown client version or update source')
    newest = None
    newest_version = installed[1]
    for item in releases:
        if not isinstance(item, dict) or item.get('draft'):
            continue
        tag = item.get('tag_name', '')
        parsed = version_key(tag)
        if parsed is None or parsed[0] != installed[0] or parsed[1] <= newest_version:
            continue
        page_url = item.get('html_url', '')
        page_prefix = SOURCES[source].page_url + ('/tag/' if source == 'github' else '/')
        if not isinstance(page_url, str) or not page_url.startswith(page_prefix):
            continue
        assets = item.get('assets') or []
        full = _asset(assets, tag + '.zip', source)
        if full is None:
            continue
        asset, parts = full
        delta_name = current + '-to-' + tag + '.delta.zip'
        delta = _asset(assets, delta_name, source)
        manifest = _asset(assets, current + '-to-' + tag + '.delta.json', source)
        d, delta_parts = delta if delta else ({}, ())
        newest = ClientRelease(tag, page_url, asset['name'], asset['browser_download_url'],
            asset.get('digest') or '', int(asset.get('size') or 0),
            delta_name if delta else '', d.get('browser_download_url', ''),
            d.get('digest') or '', manifest[0]['browser_download_url'] if manifest else '',
            parts, delta_parts, int(d.get('size') or 0), source)
        newest_version = parsed[1]
    return newest
