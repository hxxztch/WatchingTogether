"""Simple JSON config persistence."""
import json
import os
import sys
import tempfile
import threading
import logging

_lock = threading.RLock()

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
        if not isinstance(data, dict):
            return dict(_defaults)
        data = {key: value for key, value in data.items()
                if key not in _defaults or isinstance(value, str)}
        return {**_defaults, **data}
    except (OSError, ValueError):
        return dict(_defaults)


def save(**kwargs):
    # Replace only after a complete write: interruption must not truncate login data.
    with _lock:
        data = load()
        data.update(kwargs)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                             dir=os.path.dirname(os.path.abspath(CONFIG_PATH)),
                                             prefix=".film-config-", suffix=".tmp") as f:
                temporary = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, CONFIG_PATH)
            return True
        except OSError as exc:
            logging.warning("Config could not be saved: %s", type(exc).__name__)
            return False
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    logging.warning("Temporary config could not be removed")
