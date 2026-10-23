"""XiangJian GuanYing - Client entry point."""
import sys
import os
from app.runtime import configure_runtime

_script_dir = os.path.dirname(os.path.abspath(__file__))

configure_runtime()

os.environ['QT_LOGGING_RULES'] = 'qt.qpa.mousegrab.warning=false'


from app.diagnostics import log_qt_environment, record_action, setup_logging

setup_logging()
from PySide6.QtCore import QTimer
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
    log_qt_environment(app)
    record_action("client.start")

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
    QTimer.singleShot(500, lambda: window._shell.settings.check_updates(True))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
