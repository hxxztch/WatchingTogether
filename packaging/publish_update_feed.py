"""Publish a compact static release index after all Release assets are uploaded."""
import base64
import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


TAG = re.compile(r"^beta\d+\.\d+\.\d+$")
BRANCH = "update-feed"
PATH = "releases.json"


def make_feed(releases):
    result = []
    for release in releases:
        tag = release.get("tag_name", "")
        if release.get("draft") or not TAG.fullmatch(tag):
            continue
        assets = []
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if (name == tag + ".zip" or name.endswith((".delta.zip", ".delta.json"))):
                if not url.startswith("https://github.com/"):
                    raise ValueError("Unexpected release asset URL")
                assets.append({key: asset.get(key) for key in
                               ("name", "browser_download_url", "digest", "size")})
        if not any(asset["name"] == tag + ".zip" for asset in assets):
            continue
        result.append({"tag_name": tag, "html_url": release["html_url"],
                       "assets": assets})
    return result


def api(method, endpoint, token, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request("https://api.github.com/" + endpoint, data=data, method=method,
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/vnd.github+json",
                               "User-Agent": "WatchingTogether-release-feed",
                               "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def publish(repo, tag, token):
    try:
        api("GET", "repos/{}/git/ref/heads/{}".format(repo, BRANCH), token)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        commit = api("GET", "repos/{}/commits/{}".format(repo, tag), token)
        api("POST", "repos/{}/git/refs".format(repo), token,
            {"ref": "refs/heads/" + BRANCH, "sha": commit["sha"]})
    releases = api("GET", "repos/{}/releases?per_page=100".format(repo), token)
    feed = make_feed(releases)
    if not any(item["tag_name"] == tag for item in feed):
        raise ValueError("Release or its full ZIP is not published yet: " + tag)
    content = json.dumps(feed, ensure_ascii=False, separators=(",", ":")) + "\n"
    endpoint = "repos/{}/contents/{}".format(repo, PATH)
    try:
        old = api("GET", endpoint + "?ref=" + BRANCH, token)
        sha = old["sha"]
    except HTTPError as exc:
        if exc.code != 404:
            raise
        sha = None
    payload = {"message": "chore: refresh beta update feed", "branch": BRANCH,
               "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
    if sha:
        payload["sha"] = sha
    api("PUT", endpoint, token, payload)
    print("Published {} releases to {}:{}".format(len(feed), BRANCH, PATH))


if __name__ == "__main__":
    publish(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_NAME"],
            os.environ["GH_TOKEN"])
