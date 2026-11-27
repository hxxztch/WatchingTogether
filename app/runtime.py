"""Locate this application's Qt plugins and DLLs before importing Qt widgets."""
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile

_dll_directories = {}
_qt_tls_ready = False
UPDATE_READY_ENV = 'WATCHING_TOGETHER_UPDATE_READY'


def confirm_updated_startup(receipt):
    """Signal that the new version has reached the Qt event loop."""
    from app.version import CLIENT_VERSION

    try:
        path = Path(receipt).resolve()
        if (path.name != 'client-ready.txt'
                or path.parent.parent != Path(tempfile.gettempdir()).resolve()
                or not re.fullmatch(r'wt-update-[a-f0-9]{32}', path.parent.name)):
            return
        with path.open('x', encoding='ascii') as stream:
            stream.write('{} {}'.format(os.getpid(), CLIENT_VERSION))
    except OSError:
        # Confirmation is optional; the updater keeps the archive on failure.
        return


def start_update_helper(arguments, directory):
    """Launch system PowerShell without inheriting the portable DLL search path."""
    import ctypes
    import subprocess

    install = os.path.normcase(os.path.abspath(os.path.dirname(sys.executable)))
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('_PYI_')}
    system = Path(env.get('SystemRoot', r'C:\Windows'))
    powershell = system / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    paths = []
    for item in env.get('PATH', '').split(os.pathsep):
        if not item:
            continue
        normalized = os.path.normcase(os.path.abspath(os.path.expandvars(item.strip('"'))))
        if normalized != install and not normalized.startswith(install + os.sep):
            paths.append(item)
    env['PATH'] = os.pathsep.join(paths)

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    query = kernel.GetDllDirectoryW
    query.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    query.restype = ctypes.c_uint32
    length = query(0, None)
    previous = ctypes.create_unicode_buffer(length or 1)
    if length:
        query(length, previous)
    set_directory = kernel.SetDllDirectoryW
    set_directory.argtypes = [ctypes.c_wchar_p]
    set_directory.restype = ctypes.c_int
    if not set_directory(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return subprocess.Popen([str(powershell), *arguments], cwd=str(directory), env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        set_directory(previous.value or None)


def configure_qt_tls():
    """Select Windows TLS before Qt creates any encrypted connections.

    Qt otherwise prefers the bundled OpenSSL library. Python networking still
    needs that library, so keep it bundled and select Schannel only for Qt.
    Never fall back to the crashing backend if the native plugin is missing.
    """
    global _qt_tls_ready
    if sys.platform != 'win32' or _qt_tls_ready:
        return True
    import logging
    from PySide6.QtNetwork import QSslSocket
    if not QSslSocket.setActiveBackend('schannel'):
        logging.error('Qt TLS: Windows Schannel unavailable; update requests disabled')
        return False
    _qt_tls_ready = True
    logging.info('Qt TLS backend=schannel')
    return True


def configure_taskbar_identity():
    """Keep the client separate from other applications using pythonw.exe."""
    if sys.platform != 'win32':
        return
    import ctypes
    app_id = 'WatchingTogether.Client' + ('' if getattr(sys, 'frozen', False) else '.Preview')
    setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    result = setter(app_id)
    if result != 0:
        import logging
        logging.warning('Could not set taskbar identity: HRESULT 0x%08x', result & 0xffffffff)


def configure_runtime():
    project = Path(__file__).resolve().parent.parent
    frozen = getattr(sys, "frozen", False)
    executable_dir = Path(sys.executable).resolve().parent
    bundle = Path(getattr(sys, "_MEIPASS", project))
    roots = []
    if frozen:
        # PyInstaller onefile / onedir layout takes precedence over external files.
        roots.extend([bundle / "PySide6", bundle,
                      executable_dir / "_internal" / "PySide6", executable_dir / "_internal"])
    spec = importlib.util.find_spec("PySide6")
    if spec is not None and spec.origin:
        roots.append(Path(spec.origin).resolve().parent)
    if frozen:
        roots.extend([executable_dir / "PySide6", executable_dir])

    platform_dir = None
    for root in roots:
        for candidate in (root / "plugins" / "platforms", root / "Qt" / "plugins" / "platforms",
                          root / "platforms"):
            if candidate.is_dir() and (sys.platform != "win32" or (candidate / "qwindows.dll").is_file()):
                platform_dir = candidate
                break
        if platform_dir is not None:
            break

    if platform_dir is None:
        raise RuntimeError("Qt platform plugins are missing; restore the PySide6 plugins directory.")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_dir)
    os.environ["QT_PLUGIN_PATH"] = str(platform_dir.parent)
    dll_paths = [root for root in roots if root.is_dir()]
    dll_paths.extend(path for path in (bundle / "libmpv", project / "libmpv") if path.is_dir())
    existing_path = os.environ.get("PATH", "").split(os.pathsep)
    paths = list(dict.fromkeys([str(path) for path in dll_paths] + existing_path))
    os.environ["PATH"] = os.pathsep.join(paths)
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        for path in dll_paths:
            key = str(path)
            if key not in _dll_directories:
                _dll_directories[key] = os.add_dll_directory(key)
    return platform_dir
