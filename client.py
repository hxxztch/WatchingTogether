"""XiangJian GuanYing - Client entry point."""
import sys, os

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