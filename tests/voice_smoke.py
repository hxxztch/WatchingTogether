"""Exercise normal room and voice entry points with two Qt clients."""
import argparse
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.runtime import configure_runtime
configure_runtime()

from PySide6.QtWidgets import QApplication
from app.hosting import make_invitation
from app.ui.main_window import MainWindow
import app.config as config


def run(public):
    app = QApplication([])
    errors = []
    def failed(kind, value, tb):
        errors.append(str(value))
        traceback.print_exception(kind, value, tb)
    sys.excepthook = failed
    host, guest = MainWindow(), MainWindow()

    def wait(check, timeout=8):
        deadline = time.monotonic() + timeout
        while not check():
            app.processEvents()
            assert not errors, errors
            assert time.monotonic() < deadline, 'Timed out'
            time.sleep(.01)

    try:
        mode = 0 if public else 1
        host._room_panel.mode.setCurrentIndex(mode)
        host._on_create_room('host')
        wait(lambda: host._room_ready)
        service = host._rooms.host
        if public:
            wait(lambda: host._rooms.endpoint.startswith('wss://') or
                 (host._rooms.tunnel and not host._rooms.loading), 65)
            assert host._rooms.endpoint.startswith('wss://'), host._room_panel.tunnel_status.text()
            endpoint = host._rooms.endpoint
        else:
            endpoint = 'ws://127.0.0.1:' + str(service.port) + service.guest_path
        invite = make_invitation(endpoint, host._room_code)
        guest._room_panel.mode.setCurrentIndex(mode)
        guest._on_join_room(invite, 'guest')
        wait(lambda: guest._room_ready, 90 if public else 8)
        sender, receiver = host._room_panel.voice, guest._room_panel.voice
        sender.toggle()
        receiver.toggle()
        wait(lambda: sender.ready and receiver.ready)
        assert sender.source is None and receiver.source is None
        received = []
        receiver.socket.binaryMessageReceived.connect(lambda frame: received.append(bytes(frame)))
        sender.codec.start_capture()
        frame = sender.codec.encode(bytes(1920))
        sender.codec.stop_capture()
        sender.socket.sendBinaryMessage(frame)
        wait(lambda: received)
        assert len(receiver.codec.decode(received[0][0], received[0][1:])) == 1920
        host._on_leave_room()
        wait(lambda: not guest._room_ready and receiver.socket is None)
        assert sender.socket is None and not errors, errors
        print('PASS: two Qt clients joined voice, delivered Opus, and cleaned up on disband')
    finally:
        guest.close()
        host.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--public', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        config.CONFIG_PATH = str(Path(folder) / 'config.json')
        run(args.public)
