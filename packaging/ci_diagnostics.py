"""Surface build/check failures in Actions annotations, without user data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import CLIENT_VERSION

for relative in ('client-check.json', 'client-build.log', 'build-console.log'):
    path = ROOT / 'build' / CLIENT_VERSION / relative
    if path.is_file():
        message = path.read_text(encoding='utf-8', errors='replace')[-6000:]
        message = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=' + relative + '::' + message)
