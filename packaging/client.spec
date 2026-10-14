# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
import PySide6
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from app.version import CLIENT_NAME

qt = Path(PySide6.__file__).parent
runtime_names = ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
                 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll', 'concrt140.dll')
runtime = [(str(qt / name), '.') for name in runtime_names if (qt / name).is_file()]
yd_data, yd_bin, yd_hidden = collect_all('yt_dlp')
data = [(str(root / 'assets'), 'assets')] + yd_data
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
                'python-mpv', 'websockets', 'segno'):
    data += copy_metadata(package)

a = Analysis([str(root / 'client.py')], pathex=[str(root)],
    binaries=[(str(root / 'libmpv/libmpv-2.dll'), 'libmpv')] + runtime + yd_bin,
    datas=data, hiddenimports=yd_hidden + ['websockets.asyncio.client', 'segno', 'certifi'],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'numpy', 'scipy', 'pandas', 'matplotlib', 'IPython'],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=CLIENT_NAME,
    console=False, debug=False, strip=False, upx=False,
    icon=str(root / 'assets/app_icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=CLIENT_NAME)
