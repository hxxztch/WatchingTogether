import sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.runtime import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QMimeData
from app.ui.main_window import MainWindow
from app.room_share import make_share,parse_share
import app.config as config
app=QApplication([])
previous_clipboard = QMimeData()
current_clipboard = app.clipboard().mimeData()
if current_clipboard:
    for mime_format in current_clipboard.formats():
        previous_clipboard.setData(mime_format, current_clipboard.data(mime_format))
errors=[]
sys.excepthook=lambda kind,value,tb:(errors.append(str(value)),sys.__excepthook__(kind,value,tb))
def wait(check,timeout=10):
    end=time.monotonic()+timeout
    while not check():
        app.processEvents()
        assert not errors,errors
        assert time.monotonic()<end,'Share UI timeout'
        QTest.qWait(20)
with tempfile.TemporaryDirectory() as tmp:
    config.CONFIG_PATH=str(Path(tmp)/'config.json')
    host,guest,target=MainWindow(),MainWindow(),MainWindow()
    try:
        host.show();host.activateWindow()
        host._room_panel.mode.setCurrentIndex(1)
        host._on_create_room('host')
        wait(lambda:host._room_ready and bool(host._room_panel.invitation.text()))
        host._sharing.copy_share()
        share=QApplication.clipboard().text()
        assert '房间邀请' in share
        guest.show();guest.activateWindow();guest.raise_()
        guest._sharing.dirty=True
        wait(lambda:guest._sharing.dialog is not None)
        dialog=guest._sharing.dialog
        dialog.nickname.clear();dialog.join_button.click()
        assert dialog.isVisible() and not guest._room_code
        dialog.nickname.setText('viewer');dialog.join_button.click()
        wait(lambda:guest._room_ready)
        assert guest._room_code==host._room_code
        assert guest._sharing.dialog is None
        print('PASS: copied invitation prompts; blank name rejected; explicit join succeeds',flush=True)
        guest._sharing.manual(share)
        assert guest._sharing.dialog is None
        other=make_share('ws://127.0.0.1:12345/room/other?room=5678')
        guest._sharing.manual(other)
        wait(lambda:guest._sharing.dialog is not None)
        assert '离开当前房间' in guest._sharing.dialog.join_button.text()
        guest._sharing.dialog.cancel_button.click()
        guest._sharing.dirty=True
        guest._sharing.check()
        assert guest._sharing.dialog is None and guest._room_ready
        guest._sharing.manual(other)
        wait(lambda:guest._sharing.dialog is not None)
        guest._sharing.dialog.cancel_button.click()
        print('PASS: same-room suppressed; cancel keeps current room; manual invitation can reopen',flush=True)
        guest._on_leave_room()
        host.activateWindow();host.raise_()
        host._sharing.manual(other)
        wait(lambda:host._sharing.dialog is not None)
        assert '解散当前房间' in host._sharing.dialog.join_button.text()
        host._sharing.dialog.cancel_button.click()
        assert host._rooms.host is not None
        print('PASS: current host gets explicit disband confirmation',flush=True)
        target._room_panel.mode.setCurrentIndex(1)
        target._on_create_room('new-host')
        wait(lambda:target._room_ready and bool(target._room_panel.invitation.text()))
        guest._on_join_room(host._room_panel.invitation.text(),'viewer')
        wait(lambda:guest._room_ready)
        host.activateWindow();host.raise_()
        host._sharing.manual(target._room_panel.invitation.text())
        wait(lambda:host._sharing.dialog is not None)
        host._sharing.dialog.nickname.setText('switch-host')
        host._sharing.dialog.join_button.click()
        wait(lambda:host._room_ready and host._room_code==target._room_code)
        wait(lambda:not guest._room_ready)
        assert host._rooms.host is None
        print('PASS: explicit host switch disbands old room and joins new room',flush=True)
    finally:
        host.close();guest.close();target.close();app.processEvents()
        app.clipboard().setMimeData(previous_clipboard)
        assert not errors,errors
