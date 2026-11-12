"""Native Qt clients, real room signaling and actual WebRTC media on loopback."""
import sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
import app.config as config
from p2p_fixture import make_video
app=QApplication([])
errors=[]
sys.excepthook=lambda kind,value,tb: errors.append(str(value))
QMessageBox.warning=lambda *args: errors.append(str(args[-1]))
def wait(check,timeout=20):
    until=time.monotonic()+timeout
    while not check():
        app.processEvents()
        assert not errors,errors
        assert time.monotonic()<until,'GUI timeout'
        QTest.qWait(20)
with tempfile.TemporaryDirectory() as tmp:
    config.CONFIG_PATH=str(Path(tmp)/'config.json')
    movie=Path(tmp)/'source.mkv'
    make_video(movie)
    host,guest=MainWindow(),MainWindow()
    try:
        host.show(); guest.show()
        host._room_panel.mode.setCurrentIndex(1)
        host._room_panel.watch_mode.setCurrentIndex(1)
        host._on_create_room('host')
        wait(lambda:host._p2p.active and bool(host._room_panel.invitation.text()))
        invitation=host._room_panel.invitation.text()
        guest._room_panel.mode.setCurrentIndex(1)
        guest._on_join_room(invitation,'viewer')
        wait(lambda:guest._p2p.active)
        assert host._p2p.host and not guest._p2p.host
        host._on_load_file(str(movie))
        wait(lambda:not guest._player.stream.image.isNull())
        wait(lambda:guest._player.is_playing)
        assert not guest._controls._play_btn.isEnabled()
        assert not guest._controls._open_btn.isEnabled()
        print('PASS: native clients receive video through authenticated room signaling',flush=True)
        host._on_toggle_play()
        wait(lambda:not guest._player.is_playing)
        frozen=host._player.position
        QTest.qWait(200)
        assert abs(host._player.position-frozen)<.1
        guest._on_toggle_play()
        QTest.qWait(100)
        assert not host._player.is_playing
        host._on_toggle_play()
        wait(lambda:guest._player.is_playing)
        host._on_seek(3)
        wait(lambda:guest._player.position>=3)
        host._on_stop()
        wait(lambda:not guest._player.stream.state.get('active'))
        print('PASS: pause, resume, host-only controls, seek and stop',flush=True)
        host._on_leave_room()
        wait(lambda:not guest._room_ready)
        assert not guest._p2p.active
        print('PASS: room close releases media workers',flush=True)
    finally:
        host.close();guest.close();app.processEvents()
        assert not errors,errors
