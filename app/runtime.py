"""Locate this application's Qt plugins and DLLs before importing Qt widgets."""
import importlib.util
import os
from pathlib import Path
import sys

_dll_directories = {}


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
