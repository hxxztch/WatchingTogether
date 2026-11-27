# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
import PySide6
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from app.version import CLIENT_NAME, CLIENT_VERSION

qt = Path(PySide6.__file__).parent
schannel = qt / 'plugins' / 'tls' / 'qschannelbackend.dll'
if sys.platform == 'win32' and not schannel.is_file():
    raise RuntimeError('The Windows Schannel TLS plugin is required for safe update requests')
tls = [(str(schannel), 'PySide6/plugins/tls')] if sys.platform == 'win32' else []
runtime_names = ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
                 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll', 'concrt140.dll')
runtime = [(str(qt / name), '.') for name in runtime_names if (qt / name).is_file()]
conda_bin = Path(sys.prefix) / 'Library' / 'bin'
openssl = [(str(path), '.') for pattern in ('libssl-*.dll', 'libcrypto-*.dll')
           for path in conda_bin.glob(pattern)] if conda_bin.is_dir() else []
yd_data, yd_bin, yd_hidden = collect_all('yt_dlp')
opus = root / 'tools/opus'
opus_dll = opus / 'Library/bin/opus.dll'
opus_license = opus / 'info/licenses/COPYING'
if not opus_dll.is_file() or not opus_license.is_file():
    raise RuntimeError('Run packaging/fetch_opus.ps1 before building')
import hashlib
helper = root / 'tools/cloudflared.exe'
from app.tunnel import CLOUDFLARED_SHA256
if not helper.is_file() or hashlib.sha256(helper.read_bytes()).hexdigest() != CLOUDFLARED_SHA256:
    raise RuntimeError('Run packaging/fetch_cloudflared.ps1 before building the integrated client')
data = [(str(root / 'assets'), 'assets'), (str(helper), 'tools'),
        (str(root / 'packaging/apply_update.ps1'), 'updater'),
        (str(root / 'THIRD-PARTY-CLOUDFLARED.txt'), '.'),
        (str(opus_license), 'tools/opus')] + yd_data
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
                'python-mpv', 'websockets', 'segno', 'Pillow'):
    data += copy_metadata(package)

a = Analysis([str(root / 'client.py')], pathex=[str(root)],
    binaries=[(str(root / 'libmpv/libmpv-2.dll'), 'libmpv'), (str(opus_dll), 'tools/opus')] + runtime + openssl + tls + yd_bin,
    datas=data, hiddenimports=yd_hidden + ['websockets.asyncio.client', 'websockets.asyncio.server', 'segno', 'certifi', 'PIL.GifImagePlugin'],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'numpy', 'scipy', 'pandas', 'matplotlib', 'IPython'],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=CLIENT_NAME,
    console=False, debug=False, strip=False, upx=False,
    icon=str(root / 'assets/app_icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=CLIENT_NAME)
