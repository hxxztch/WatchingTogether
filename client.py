"""XiangJian GuanYing - Client entry point."""
import sys
import os
from app.runtime import configure_runtime

_script_dir = os.path.dirname(os.path.abspath(__file__))

configure_runtime()

os.environ['QT_LOGGING_RULES'] = 'qt.qpa.mousegrab.warning=false'


import logging, datetime, traceback

# ---------- crash logger ----------
def _setup_crash_log():
    log_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _script_dir
    log_path = os.path.join(log_dir, "crash.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    logging.getLogger().setLevel(logging.DEBUG)
    # WebSocket DEBUG frames include private session tokens and chat text.
    logging.getLogger("websockets").setLevel(logging.WARNING)
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
    if "--package-check" in sys.argv:
        import argparse
        from app.package_check import run
        parser = argparse.ArgumentParser()
        parser.add_argument("--package-check", required=True, metavar="REPORT_JSON")
        parser.add_argument("--check-server", default=None)
        options = parser.parse_args()
        sys.exit(run(options.package_check, options.check_server))
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
