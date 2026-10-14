# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
import PySide6
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from app.version import SERVER_NAME
runtime = Path(PySide6.__file__).parent / 'vcruntime140.dll'
a = Analysis([str(root / 'server.py')], pathex=[str(root)],
    binaries=[(str(runtime), '.')], datas=copy_metadata('websockets'),
    hiddenimports=['websockets.asyncio.server'], excludes=['PySide6', 'tkinter'],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=SERVER_NAME,
    console=True, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=SERVER_NAME)
