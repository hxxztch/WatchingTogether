"""Simple JSON config persistence."""
import json
import os
import sys

# Frozen: config.json sits next to the EXE; Source: config.json is at project root
if getattr(sys, "frozen", False):
    CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "config.json")
else:
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

_defaults = {"server": "ws://localhost:9877", "nickname": "", "bili_cookie": "", "bili_uid": "", "bili_uname": ""}


def load() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_defaults, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_defaults)


def save(**kwargs):
    data = load()
    data.update(kwargs)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)