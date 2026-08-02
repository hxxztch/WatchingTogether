"""XiangJian GuanYing - Client entry point."""
import sys
import os, os

_script_dir = os.path.dirname(os.path.abspath(__file__))

# Add libmpv DLL to PATH so mpv library can find it
_libmpv_dir = os.path.join(_script_dir, "libmpv")
os.environ["PATH"] = _libmpv_dir + os.pathsep + os.environ.get("PATH", "")

if getattr(sys, 'frozen', False):
    _ext_platforms = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.abspath(_ext_platforms)
else:
    import importlib.util
    _spec = importlib.util.find_spec("PySide6")
    if _spec and _spec.origin:
        _pyside6_dir = os.path.dirname(os.path.abspath(_spec.origin))
        os.environ["PATH"] = _pyside6_dir + os.pathsep + os.environ.get("PATH", "")
        _plugins_dir = os.path.join(_pyside6_dir, "plugins", "platforms")
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.abspath(_plugins_dir)

os.environ['QT_LOGGING_RULES'] = 'qt.qpa.mousegrab.warning=false'


import logging, datetime, traceback

# ---------- crash logger ----------
def _setup_crash_log():
    log_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _script_dir
    log_path = os.path.join(log_dir, "crash.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%%(asctime)s] %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    logging.getLogger().setLevel(logging.DEBUG)
    logging.info("Client starting (frozen=%s)", getattr(sys, "frozen", False))
    # Global exception hook
    def _excepthook(exc_type, exc_val, tb):
        logging.critical("".join(traceback.format_exception(exc_type, exc_val, tb)))
        sys.__excepthook__(exc_type, exc_val, tb)
    sys.excepthook = _excepthook

_setup_crash_log()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Set application icon (taskbar icon on Windows)
    if getattr(sys, 'frozen', False):
        _png = os.path.join(sys._MEIPASS, "assets", "img.png")
    else:
        _png = os.path.join(_script_dir, "assets", "img.png")
    if os.path.exists(_png):
        _p = QPixmap(_png)
        if not _p.isNull():
            app.setWindowIcon(QIcon(_p))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()