"""Local, bounded diagnostics without account, invitation, or media contents."""
from collections import deque
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import threading
import traceback
import uuid

from app.version import CLIENT_VERSION


_session = uuid.uuid4().hex[:12]
_actions = deque(maxlen=20)
_lock = threading.Lock()
_fatal_file = None


def log_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def recent_actions():
    with _lock:
        return " | ".join(_actions) or "none"


def record_action(name, **details):
    """Record only fixed operation names and non-sensitive enumerated details."""
    fields = " ".join("{}={}".format(key, value) for key, value in sorted(details.items()))
    entry = name + (" " + fields if fields else "")
    with _lock:
        _actions.append(entry)
    logging.info("Action: %s", entry)


def _exception(kind, value, tb):
    logging.critical("Unhandled exception; recent_actions=%s\n%s",
                     recent_actions(), "".join(traceback.format_exception(kind, value, tb)))
    sys.__excepthook__(kind, value, tb)


def _thread_exception(args):
    logging.critical("Thread exception thread=%s recent_actions=%s\n%s",
                     args.thread.name if args.thread else "unknown", recent_actions(),
                     "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                        args.exc_traceback)))


def setup_logging():
    global _fatal_file
    directory = log_directory()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(str(directory / "crash.log"), maxBytes=2 * 1024 * 1024,
                                      backupCount=3, encoding="utf-8")
    except OSError:
        directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WatchingTogether" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(str(directory / "crash.log"), maxBytes=2 * 1024 * 1024,
                                      backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s session=" + _session +
        " thread=%(threadName)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    sys.excepthook = _exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_exception
    # Native Python faults cannot safely pass through the logging framework.
    fatal_path = directory / "fatal.log"
    try:
        if fatal_path.is_file() and fatal_path.stat().st_size > 2 * 1024 * 1024:
            os.replace(str(fatal_path), str(directory / "fatal.log.1"))
        _fatal_file = open(fatal_path, "a", encoding="utf-8")
        _fatal_file.write("\n=== session={} version={} ===\n".format(_session, CLIENT_VERSION))
        _fatal_file.flush()
        faulthandler.enable(file=_fatal_file, all_threads=True)
    except OSError as exc:
        logging.warning("Native fault log unavailable: %s", type(exc).__name__)
    logging.info("Client start version=%s frozen=%s os=%s architecture=%s python=%s cpu_count=%s",
                 CLIENT_VERSION, bool(getattr(sys, "frozen", False)), platform.platform(),
                 platform.machine(), platform.python_version(), os.cpu_count())
    return directory / "crash.log"


def log_qt_environment(app):
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    screens = app.screens()
    geometry = ["{}x{}".format(s.size().width(), s.size().height()) for s in screens]
    logging.info("Qt environment qt=%s pyside=%s screens=%s", qVersion(),
                 pyside_version, ",".join(geometry))
