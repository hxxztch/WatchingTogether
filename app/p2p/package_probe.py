"""Opt-in native P2P verification in the frozen test-channel package."""
from fractions import Fraction
import av
from PIL import Image


def check(host, guest, folder, wait):
    path = folder / 'p2p-native.mkv'
    with av.open(str(path), 'w', format='matroska') as output:
        video = output.add_stream('ffv1', rate=20)
        video.width, video.height, video.pix_fmt = 160, 90, 'bgr0'
        for index in range(120):
            frame = av.VideoFrame.from_image(Image.new('RGB', (160, 90), (index, 80, 120)))
            frame.pts, frame.time_base = index, Fraction(1, 20)
            for packet in video.encode(frame):
                output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
    host._room_panel.mode.setCurrentIndex(1)
    host._room_panel.watch_mode.setCurrentIndex(1)
    host._on_create_room('p2p-host')
    wait(lambda: host._p2p.active and bool(host._room_panel.invitation.text()))
    guest._room_panel.mode.setCurrentIndex(1)
    guest._on_join_room(host._room_panel.invitation.text(), 'p2p-guest')
    wait(lambda: guest._p2p.active)
    host._on_load_file(str(path))
    wait(lambda: not guest._player.stream.image.isNull() and guest._player.is_playing)
    host._on_toggle_play()
    wait(lambda: not guest._player.is_playing)
    host._on_leave_room()
    wait(lambda: not guest._room_ready and not guest._p2p.active)
