"""Plan a versioned release from the shared beta branch without replacing releases."""
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError

from publish_update_feed import api

ROOT = Path(__file__).resolve().parents[1]


def plan(version, commit, tag_commit, release, manual=False):
    if not re.fullmatch(r"(?:beta|test)\d+\.\d+\.\d+", version):
        raise ValueError("CLIENT_VERSION must have the form betaX.Y.Z")
    complete = release and not release.get("draft") and any(
        a.get("name") == version + ".zip" for a in release.get("assets", []))
    if complete:
        # A rerun/manual dispatch can finish a failed feed or mirror publication.
        return {"version": version, "publish": manual or tag_commit == commit, "build": False}
    if tag_commit and tag_commit != commit:
        raise ValueError("Existing version tag points elsewhere; increment CLIENT_VERSION")
    return {"version": version, "publish": True, "build": True}


def main():
    namespace = {}
    exec((ROOT / "app/version.py").read_text(encoding="utf-8"), namespace)
    version = namespace["CLIENT_VERSION"]
    if not re.fullmatch(r"(?:beta|test)\d+\.\d+\.\d+", version):
        raise ValueError("Invalid CLIENT_VERSION")
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    try:
        release = api("GET", "repos/{}/releases/tags/{}".format(repo, version), token)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        release = None
    tag = subprocess.run(["git", "rev-parse", "--verify", "refs/tags/{}^{{commit}}".format(version)],
                         capture_output=True, text=True)
    tag_commit = tag.stdout.strip() if tag.returncode == 0 else None
    result = plan(version, os.environ["GITHUB_SHA"], tag_commit, release,
                  os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
    if result["build"]:
        lines = (ROOT / "更新日志.txt").read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].startswith(version + "（"):
            raise ValueError("Changelog must start with CLIENT_VERSION")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in result.items():
            output.write("{}={}\n".format(key, str(value).lower() if isinstance(value, bool) else value))
    print("Release plan: " + str(result))


if __name__ == "__main__":
    main()
