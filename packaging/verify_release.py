"""Run both EXEs outside the repo with Python/Conda/Qt environment paths removed."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import CLIENT_NAME, SERVER_NAME


def main():
    dist = ROOT / 'dist' / 'release-1.4.0'
    reports = ROOT / 'build' / 'release-1.4.0'
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ('PYTHON', 'CONDA', 'QT_', 'QML', 'VIRTUAL_ENV', '_PYI'))}
    system = Path(env.get('SystemRoot', r'C:\Windows'))
    env['PATH'] = str(system / 'System32') + os.pathsep + str(system)
    env['QT_QPA_PLATFORM'] = 'windows'
    with tempfile.TemporaryDirectory(prefix='film-independent-package-') as temporary:
        root = Path(temporary)
        for name in (CLIENT_NAME, SERVER_NAME):
            shutil.copytree(dist / name, root / name)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        with (reports / 'server-check.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([str(root / SERVER_NAME / (SERVER_NAME + '.exe')),
                '--host', '127.0.0.1', '--port', str(port)], cwd=str(root), env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 20
                while True:
                    if server.poll() is not None:
                        raise RuntimeError('Packaged server exited at startup')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise TimeoutError('Packaged server did not listen')
                        time.sleep(.1)
                report = reports / 'client-check.json'
                completed = subprocess.run([str(root / CLIENT_NAME / (CLIENT_NAME + '.exe')),
                    '--package-check', str(report), '--check-server', f'ws://127.0.0.1:{port}'],
                    cwd=str(root), env=env, timeout=75, creationflags=subprocess.CREATE_NO_WINDOW)
                if completed.returncode or not report.exists():
                    raise RuntimeError('Packaged client check failed: ' + str(completed.returncode))
                result = json.loads(report.read_text(encoding='utf-8'))
                assert result['ok'] and result['frozen'], result
                print(json.dumps(result, ensure_ascii=False, indent=2))
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    main()
