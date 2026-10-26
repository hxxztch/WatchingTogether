"""XiangJian GuanYing - Client entry point."""
import sys
import os
from app.runtime import configure_runtime, configure_taskbar_identity

configure_runtime()

os.environ['QT_LOGGING_RULES'] = 'qt.qpa.mousegrab.warning=false'


from app.diagnostics import log_qt_environment, record_action, setup_logging

setup_logging()
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
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
    configure_taskbar_identity()
    app = QApplication(sys.argv)
    app.setApplicationName('WatchingTogether')
    app.setApplicationDisplayName('超时空会夜机')
    log_qt_environment(app)
    record_action("client.start")

    window = MainWindow()
    # Use the same application logo for the taskbar, dialogs and mini player.
    app.setWindowIcon(window.windowIcon())
    window.show()
    QTimer.singleShot(500, lambda: window._shell.settings.check_updates(True))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
