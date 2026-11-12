"""Remove outgoing deltas whose same-version baseline was explicitly replaced."""
import base64
import json
import os
from publish_update_feed import api, publish as publish_feed
from publish_gitee import Gitee
from app.updates import MANIFEST_START, MANIFEST_END

version = os.environ['REPUBLISH_VERSION']
repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
prefix = version + '-to-'
for release in api('GET', 'repos/' + repo + '/releases?per_page=100', token):
    for asset in release.get('assets', []):
        if asset['name'].startswith(prefix):
            api('DELETE', 'repos/' + repo + '/releases/assets/' + str(asset['id']), token)
publish_feed(repo, version, token)
gitee = Gitee(os.environ['GITEE_TOKEN'])
releases = gitee.api('GET', '/releases', {'per_page': 100})
for release in releases:
    body = release.get('body') or ''
    if MANIFEST_START not in body:
        continue
    encoded = body.split(MANIFEST_START, 1)[1].split(MANIFEST_END, 1)[0]
    entry = json.loads(base64.b64decode(encoded))
    filtered = [a for a in entry['assets'] if not a['name'].startswith(prefix)]
    if len(filtered) == len(entry['assets']):
        continue
    entry['assets'] = filtered
    encoded = base64.b64encode(json.dumps(entry, ensure_ascii=False).encode()).decode()
    body = body.split(MANIFEST_START, 1)[0] + MANIFEST_START + encoded + MANIFEST_END
    gitee.api('PATCH', '/releases/' + str(release['id']), {'body': body})
    for asset in gitee.api('GET', '/releases/{}/attach_files'.format(release['id']), {'per_page': 100}):
        if asset['name'].startswith(prefix):
            gitee.api('DELETE', '/releases/{}/attach_files/{}'.format(release['id'], asset['id']))
old = gitee.api('GET', '/contents/releases.json', {'ref': 'update-feed'})
entries = json.loads(base64.b64decode(old['content']))
for entry in entries:
    entry['assets'] = [a for a in entry['assets'] if not a['name'].startswith(prefix)]
gitee.api('PUT', '/contents/releases.json', {'branch': 'update-feed', 'sha': old['sha'],
    'message': 'Remove deltas with replaced baseline',
    'content': base64.b64encode(json.dumps(entries, ensure_ascii=False).encode()).decode()})
print('Old outgoing deltas removed; channel switching uses verified full packages')
