"""Publish verified portable ZIPs/deltas to Gitee, then expose the update feed.

Token is read from GITEE_TOKEN or a hidden prompt, never written into Git/config.
Run after pushing the source tag to Gitee; --from-github mirrors CI artifacts.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.updates import (MANIFEST_START, MANIFEST_END, SOURCES,
                        valid_download_url, version_key)

REPO = 'hxxztch/watching-together'
API = 'https://gitee.com/api/v5/repos/' + REPO
PART_SIZE = 90_000_000


def public_session():
    # Publishing is explicitly direct; stale Windows proxy settings must not
    # redirect the Gitee mirror's anonymous verification through another service.
    session = requests.Session()
    session.trust_env = False
    return session


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for data in iter(lambda: source.read(1024 * 1024), b''):
            result.update(data)
    return 'sha256:' + result.hexdigest()


def split_asset(path, output, limit=PART_SIZE):
    """Deterministic byte chunks; the updater reconstructs the original ZIP."""
    path = Path(path)
    if path.stat().st_size <= limit:
        return [path]
    output.mkdir(parents=True, exist_ok=True)
    parts = []
    with path.open('rb') as source:
        index = 1
        while True:
            data = source.read(limit)
            if not data:
                break
            target = output / (path.name + '.{:03d}'.format(index))
            target.write_bytes(data)
            parts.append(target)
            index += 1
    return parts


def public_download(url, expected, destination=None, provider='gitee'):
    """Verify using anonymous HTTPS, including every redirect and byte digest."""
    checksum = hashlib.sha256()
    size = 0
    for hop in range(6):
        if not valid_download_url(url, provider, redirect=hop > 0):
            raise ValueError('Unexpected public download host')
        response = public_session().get(url, stream=True, timeout=(20, 180), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, response.headers.get('Location', ''))
            response.close()
            continue
        if response.status_code != 200:
            response.close()
            raise RuntimeError('Anonymous download failed: HTTP ' + str(response.status_code))
        output = Path(destination).open('wb') if destination else None
        try:
            for data in response.iter_content(1024 * 1024):
                checksum.update(data)
                size += len(data)
                if output:
                    output.write(data)
        finally:
            response.close()
            if output:
                output.close()
        if 'sha256:' + checksum.hexdigest() != expected.lower():
            raise ValueError('Public download digest mismatch')
        return size
    raise ValueError('Too many download redirects')


class Gitee:
    def __init__(self, token):
        self.token = token
        self.session = public_session()

    def api(self, method, suffix, payload=None, file=None, missing=False):
        values = dict(payload or {}, access_token=self.token)
        kwargs = {'params': values} if method == 'GET' else {'data': values}
        if file is not None:
            kwargs['files'] = {'file': (Path(file.name).name, file, 'application/octet-stream')}
        response = self.session.request(method, API + suffix,
            timeout=(20, 240), allow_redirects=False,
            headers={'User-Agent': 'WatchingTogether-Gitee-Publisher'}, **kwargs)
        if missing and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            # Do not print response URLs/bodies: some API errors echo credentials.
            raise RuntimeError('Gitee API {} {}: HTTP {}'.format(method, suffix, response.status_code))
        return response.json() if response.content else None

    def upload(self, release_id, path, existing):
        expected = digest(path)
        old = next((a for a in existing if a['name'] == path.name), None)
        if old:
            url = urljoin('https://gitee.com', old.get('browser_download_url', ''))
            try:
                size = public_download(url, expected)
                return {'url': url, 'digest': expected, 'size': size}
            except (ValueError, RuntimeError):
                self.api('DELETE', '/releases/{}/attach_files/{}'.format(release_id, old['id']))
        print('Uploading ' + path.name, flush=True)
        with path.open('rb') as source:
            item = self.api('POST', '/releases/{}/attach_files'.format(release_id), file=source)
        url = urljoin('https://gitee.com', item.get('browser_download_url', ''))
        size = public_download(url, expected)
        if size != path.stat().st_size:
            raise ValueError('Published size mismatch')
        print('Anonymous download verified: ' + path.name, flush=True)
        return {'url': url, 'digest': expected, 'size': size}


def publish(tag, directory, token):
    if version_key(tag) is None or not tag.startswith('beta'):
        raise ValueError('Invalid beta tag')
    directory = Path(directory)
    files = sorted(p for p in directory.iterdir() if p.name == tag + '.zip' or
                   p.name.endswith(('-to-' + tag + '.delta.zip', '-to-' + tag + '.delta.json')))
    if not any(p.name == tag + '.zip' for p in files):
        raise FileNotFoundError('Full ZIP is required')
    lines = (ROOT / '更新日志.txt').read_text(encoding='utf-8').splitlines()
    if not lines[0].startswith(tag + '（'):
        raise ValueError('Changelog must start with the release tag')
    notes = []
    for line in lines[1:]:
        if re.match(r'^beta\d+\.\d+\.\d+（', line):
            break
        notes.append(line)
    notes = '\n'.join(notes).strip()
    api = Gitee(token)
    release = api.api('GET', '/releases/tags/' + tag, missing=True)
    if release is None:
        release = api.api('POST', '/releases', {'tag_name': tag, 'target_commitish': tag,
            'name': tag, 'body': notes + '\n\n附件准备中，校验完成后开放自动更新。', 'prerelease': 'true'})
    rid = release['id']
    existing = api.api('GET', '/releases/{}/attach_files'.format(rid), {'per_page': 100})
    assets = []
    split_dir = directory / 'gitee-parts'
    merge_commands = []
    for path in files:
        parts = split_asset(path, split_dir)
        uploaded = [api.upload(rid, part, existing) for part in parts]
        asset = {'name': path.name, 'digest': digest(path), 'size': path.stat().st_size,
                 'browser_download_url': uploaded[0]['url']}
        if len(parts) > 1:
            asset['parts'] = uploaded
            merge_commands.append('copy /b ' + '+'.join('"' + p.name + '"' for p in parts) +
                                  ' "' + path.name + '" >nul || exit /b 1')
            merge_commands.append('powershell.exe -NoProfile -Command "if((Get-FileHash -LiteralPath \'' +
                                  path.name + '\' -Algorithm SHA256).Hash.ToLower() -ne \'' +
                                  asset['digest'][7:] + '\'){exit 1}"')
            merge_commands.append('if errorlevel 1 (echo SHA256 check failed & pause & exit /b 1)')
        assets.append(asset)
    if merge_commands:
        merge = directory / ('merge-' + tag + '.cmd')
        merge.write_bytes(('@echo off\r\ncd /d "%~dp0"\r\n' + '\r\n'.join(merge_commands) +
                           '\r\necho ZIP verified. Extract the complete ZIP before running.\r\npause\r\n').encode('ascii'))
        api.upload(rid, merge, existing)
        notes += '\n\n完整包超过 Gitee 单附件限制：手动下载请将所有 .001/.002 分段与 merge-' + tag + '.cmd 放在同一目录，运行合并脚本得到完整 ZIP，再完整解压。客户端内更新会自动合并并校验。'
    entry = {'tag_name': tag, 'html_url': SOURCES['gitee'].page_url + '/' + tag, 'assets': assets}
    encoded = base64.b64encode(json.dumps(entry, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).decode('ascii')
    api.api('PATCH', '/releases/' + str(rid), {'tag_name': tag, 'name': tag,
        'prerelease': 'true', 'body': notes + '\n\n' + MANIFEST_START + encoded + MANIFEST_END})
    # Publish discovery only after every attachment passed anonymous download verification.
    endpoint = '/contents/releases.json'
    old = api.api('GET', endpoint, {'ref': 'update-feed'}, missing=True)
    # Gitee also uses HTTP 200 + [] for a missing path/ref in an empty tree.
    if old == []:
        old = None
    previous = []
    if old is None:
        branch = api.api('GET', '/branches/update-feed', missing=True)
        if not branch:
            api.api('POST', '/branches', {'branch_name': 'update-feed', 'refs': tag})
    else:
        previous = json.loads(base64.b64decode(old['content']).decode('utf-8'))
    feed = [entry] + [item for item in previous if item.get('tag_name') != tag]
    payload = {'branch': 'update-feed', 'message': 'Refresh verified Gitee beta updates',
               'content': base64.b64encode((json.dumps(feed, ensure_ascii=False) + '\n').encode('utf-8')).decode('ascii')}
    if old:
        payload['sha'] = old['sha']
    api.api('PUT' if old else 'POST', endpoint, payload)
    (directory / 'gitee-release.json').write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Gitee release and update feed published: ' + tag, flush=True)


def fetch_github(tag, directory):
    response = public_session().get('https://api.github.com/repos/hxxztch/WatchingTogether/releases/tags/' + tag,
                            headers={'User-Agent': 'WatchingTogether-Gitee-Publisher'}, timeout=30)
    response.raise_for_status()
    directory.mkdir(parents=True, exist_ok=True)
    for asset in response.json()['assets']:
        name = asset['name']
        if name != tag + '.zip' and not name.endswith(('-to-' + tag + '.delta.zip', '-to-' + tag + '.delta.json')):
            continue
        expected = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', expected):
            raise ValueError('GitHub asset has no SHA256')
        target = directory / name
        if not target.exists() or digest(target) != expected.lower():
            print('Downloading GitHub artifact: ' + name, flush=True)
            public_download(asset['browser_download_url'], expected, target, provider='github')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--assets-dir', type=Path, required=True)
    parser.add_argument('--from-github', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('GITEE_TOKEN') or getpass.getpass('Gitee token (hidden): ')
    try:
        if args.from_github:
            fetch_github(args.tag, args.assets_dir)
        publish(args.tag, args.assets_dir, token)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, requests.RequestException) as exc:
        print('Gitee publication failed: ' + (str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
