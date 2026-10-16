"""Run the portable executable in isolation without a separate server or dev PATH."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import CLIENT_NAME


def main():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ('PYTHON', 'CONDA', 'QT_', 'QML', 'VIRTUAL_ENV', '_PYI'))}
    system = Path(env.get('SystemRoot', r'C:\Windows'))
    env['PATH'] = str(system / 'System32') + os.pathsep + str(system)
    env['QT_QPA_PLATFORM'] = 'windows'
    report = ROOT / 'build/integrated-preview/client-check.json'
    with tempfile.TemporaryDirectory(prefix='film-integrated-package-') as temporary:
        target = Path(temporary) / CLIENT_NAME
        shutil.copytree(ROOT / 'dist/integrated-preview' / CLIENT_NAME, target)
        completed = subprocess.run([str(target / (CLIENT_NAME + '.exe')), '--package-check', str(report)],
                                   cwd=str(target), env=env, timeout=75,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode or not report.exists():
            raise RuntimeError('Packaged check failed: ' + str(completed.returncode))
        result = json.loads(report.read_text(encoding='utf-8'))
        assert result['ok'] and result['frozen'], result
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
