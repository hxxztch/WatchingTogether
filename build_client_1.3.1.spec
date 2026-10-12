# -*- mode: python ; coding: utf-8 -*-
import os, re

def filter_binaries(binaries):
    filtered = []
    qt5_pattern = re.compile(r"[Qq][Tt]5[A-Za-z]*\.dll$", re.IGNORECASE)
    for item in binaries:
        fname = os.path.basename(item[0]) if isinstance(item, tuple) else os.path.basename(item)
        if qt5_pattern.match(fname):
            print(f"EXCLUDING Qt5 binary: {fname}")
            continue
        if "api-ms-win" in fname.lower():
            continue
        filtered.append(item)
    return filtered

a = Analysis(
    ["client.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app", "app"),
        ("assets", "assets"),
        ("libmpv", "libmpv"),
    ],
    hiddenimports=[
        "PySide6",
        "mpv",
        "websockets",
        "segno",
        "qrcode",
        "qrcode.image.pil",
        "brotli",
        "yt_dlp",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pip", "setuptools", "wheel", "easy_install", "pkg_resources",
        "win32api", "win32com", "win32crypt",
        "pywin32", "pywin", "pywin32_system32",
        "pythoncom", "pywintypes",
        "numpy", "mkl", "psutil",
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
        "browser_cookie3", "lz4", "Crypto",
    ],
    noarchive=False,
    optimize=0,
)

a.binaries = filter_binaries(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WatchingTogether",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["*.pyd", "*.dll"],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets\\app_icon.ico"],
)
