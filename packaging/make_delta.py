"""Build a file-level update ZIP between two portable client ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


VERSION = re.compile(r"^beta\d+\.\d+\.\d+$")
EXCLUDED = {"config.json", "crash.log", "crash.log.1", "crash.log.2",
            "crash.log.3", "fatal.log", "fatal.log.1"}


def package_files(archive):
    files = {}
    roots = set()
    for item in archive.infolist():
        if item.is_dir():
            continue
        root, slash, relative = item.filename.partition("/")
        if not slash or not relative or relative.startswith("/") or "\\" in relative:
            raise ValueError("Invalid package path: " + item.filename)
        if any(part in ("", ".", "..") for part in relative.split("/")):
            raise ValueError("Unsafe package path: " + item.filename)
        roots.add(root)
        if relative.split('/')[0].lower() == 'stickers':
            continue
        if relative in files:
            raise ValueError("Duplicate package path: " + relative)
        if relative not in EXCLUDED:
            files[relative] = item
    if len(roots) != 1 or not files:
        raise ValueError("Expected one nonempty package directory")
    return files


def digest(archive, item):
    checksum = hashlib.sha256()
    with archive.open(item) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def create_delta(previous_zip, current_zip, from_version, to_version, output):
    if not VERSION.fullmatch(from_version) or not VERSION.fullmatch(to_version):
        raise ValueError("Expected beta version tags")
    if from_version == to_version:
        raise ValueError("Delta versions must differ")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(previous_zip) as previous, zipfile.ZipFile(current_zip) as current:
        old_files = package_files(previous)
        new_files = package_files(current)
        old_hashes = {name: digest(previous, item) for name, item in old_files.items()}
        new_hashes = {name: digest(current, item) for name, item in new_files.items()}
        changed = [name for name in sorted(new_files) if old_hashes.get(name) != new_hashes[name]]
        removed = sorted(set(old_files) - set(new_files))
        manifest = {
            "schema": 1,
            "from_version": from_version,
            "to_version": to_version,
            "files": [{"path": name, "sha256": new_hashes[name],
                       "old_sha256": old_hashes.get(name)} for name in changed],
            "removed": [{"path": name, "old_sha256": old_hashes[name]} for name in removed],
        }
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as delta:
            delta.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                       separators=(",", ":")))
            for name in changed:
                with current.open(new_files[name]) as source, delta.open("files/" + name, "w") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
    with zipfile.ZipFile(output) as delta:
        if delta.testzip() is not None:
            raise ValueError("Delta archive is corrupt")
    print("Delta: {} changed, {} removed, {} bytes".format(
        len(changed), len(removed), output.stat().st_size))
    output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-zip", type=Path, required=True)
    parser.add_argument("--to-zip", type=Path, required=True)
    parser.add_argument("--from-version", required=True)
    parser.add_argument("--to-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    create_delta(args.from_zip, args.to_zip, args.from_version,
                 args.to_version, args.output)
