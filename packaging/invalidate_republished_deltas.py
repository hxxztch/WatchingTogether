"""Remove outgoing deltas whose same-version baseline was explicitly replaced."""
import os
from publish_update_feed import api, publish as publish_feed

version = os.environ['REPUBLISH_VERSION']
repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
prefix = version + '-to-'
for release in api('GET', 'repos/' + repo + '/releases?per_page=100', token):
    for asset in release.get('assets', []):
        if asset['name'].startswith(prefix):
            api('DELETE', 'repos/' + repo + '/releases/assets/' + str(asset['id']), token)
publish_feed(repo, version, token)
print('Old outgoing GitHub deltas removed')
