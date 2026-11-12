"""Optional first-stage LAN P2P support. Imports stay lazy for existing clients."""
import importlib.util
import sys


def available():
    return sys.version_info >= (3, 11) and all(
        importlib.util.find_spec(name) is not None for name in ('aiortc', 'av'))
