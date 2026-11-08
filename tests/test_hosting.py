import asyncio
import json
import time
import unittest
import subprocess
import sys
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
from app.hosting import EmbeddedHost, make_invitation, parse_invitation
from app.network import NetworkClient
from app.chat_media import MAX_MESSAGE_BYTES

APP = QCoreApplication.instance() or QCoreApplication([])


async def receive(ws, kind):
    async def read():
        async for raw in ws:
            message = json.loads(raw)
            if message['type'] == kind:
                return message
    return await asyncio.wait_for(read(), 3)


async def send(ws, kind, **kw):
    await ws.send(json.dumps(dict(type=kind, **kw)))


class HostingTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_gif_new_client_old_client_and_reconnect(self):
        import base64
        import random
        from io import BytesIO
        from PIL import Image
        from app.ui.chat_images import prepare_image
        from app.chat_media import image_bytes
        rng = random.Random(8)
        frames = [Image.frombytes('RGB', (256, 256), rng.getrandbits(256 * 256 * 24).to_bytes(256 * 256 * 3, 'big'))
                  for _ in range(10)]
        output = BytesIO()
        frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:], duration=80, loop=0)
        large = prepare_image(output.getvalue())
        self.assertGreater(len(large), 65536)
        image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhWQAAAAASUVORK5CYII='
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner', protocol=2, chat_media_bytes=MAX_MESSAGE_BYTES)
        room = await receive(owner, 'room_created')
        self.assertEqual(room['chat_media_bytes'], MAX_MESSAGE_BYTES)
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'join_room', name='new', room=room['room'], protocol=2, chat_media_bytes=MAX_MESSAGE_BYTES)
        joined = await receive(guest, 'room_joined')
        old = await connect(self.base + self.host.guest_path, max_size=65536)
        self.sockets.append(old)
        await receive(old, 'hello')
        await send(old, 'join_room', name='old', room=room['room'], protocol=2)
        await receive(old, 'room_joined')
        await send(owner, 'chat', message='[image]', image=image, image_large=large)
        event = await receive(guest, 'chat')
        self.assertEqual(event['image_large'], large)
        image_bytes(event['image_large'])
        legacy = await receive(old, 'chat')
        self.assertNotIn('image_large', legacy)
        image_bytes(legacy['image'], legacy=True)
        await guest.close()
        resumed = await self.socket(self.host.guest_path)
        await send(resumed, 'resume_room', room=room['room'], token=joined['token'], chat_seq=0,
                   chat_media_bytes=MAX_MESSAGE_BYTES)
        await receive(resumed, 'room_joined')
        self.assertEqual((await receive(resumed, 'chat'))['image_large'], large)
        await send(old, 'chat', message='still online')
        self.assertEqual((await receive(owner, 'chat'))['message'], 'still online')
    async def test_image_chat_validation_dedup_and_resume(self):
        import base64
        # A standard 1x1 PNG, no GUI required on the server.
        image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhWQAAAAASUVORK5CYII='
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner', protocol=2)
        room = await receive(owner, 'room_created')
        self.assertTrue(room['chat_images'])
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'join_room', name='guest', room=room['room'], protocol=2)
        joined = await receive(guest, 'room_joined')
        await send(owner, 'chat', message='[image]', image=image, id='picture')
        event = await receive(guest, 'chat')
        self.assertEqual(event['image'], image)
        await send(owner, 'chat', message='[image]', image=image, id='picture')
        await receive(owner, 'ack')
        await send(owner, 'chat', message='bad', image='X' * 40000, id='too-big')
        await receive(owner, 'error')
        await guest.close()
        resumed = await self.socket(self.host.guest_path)
        await send(resumed, 'resume_room', room=room['room'], token=joined['token'], chat_seq=0)
        await receive(resumed, 'room_joined')
        replay = await receive(resumed, 'chat')
        self.assertEqual(replay['seq'], event['seq'])
        self.assertEqual(replay['image'], image)

    async def test_gif_delivery_and_resume_with_legacy_png_fallback(self):
        import base64
        from io import BytesIO
        from PIL import Image
        from app.ui.gif_images import prepare_gif
        buffer = BytesIO()
        Image.new('RGB', (4, 4), 'red').save(buffer, format='GIF', save_all=True,
            append_images=[Image.new('RGB', (4, 4), 'blue')], duration=80, loop=0)
        animation = prepare_gif(buffer.getvalue())
        image = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhWQAAAAASUVORK5CYII='
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner', protocol=2)
        room = await receive(owner, 'room_created')
        self.assertTrue(room['chat_gifs'])
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'join_room', name='guest', room=room['room'], protocol=2)
        joined = await receive(guest, 'room_joined')
        await send(owner, 'chat', message='[图片]', image=image, animation=animation, id='gif')
        delivered = await receive(guest, 'chat')
        self.assertEqual(delivered['animation'], animation)
        self.assertEqual(delivered['image'], image)
        await guest.close()
        resumed = await self.socket(self.host.guest_path)
        await send(resumed, 'resume_room', room=room['room'], token=joined['token'], chat_seq=0)
        await receive(resumed, 'room_joined')
        self.assertEqual((await receive(resumed, 'chat'))['animation'], animation)
        await send(owner, 'chat', message='bad', image=image, animation=image)
        await receive(owner, 'error')

    async def asyncSetUp(self):
        self.host = EmbeddedHost()
        self.host.start()
        deadline = time.monotonic() + 3
        while not self.host.port:
            self.assertLess(time.monotonic(), deadline)
            await asyncio.sleep(.01)
        self.base = 'ws://127.0.0.1:' + str(self.host.port)
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        self.assertTrue(await asyncio.get_running_loop().run_in_executor(None, self.host.stop))

    async def socket(self, path):
        ws = await connect(self.base + path, max_size=MAX_MESSAGE_BYTES)
        self.sockets.append(ws)
        await receive(ws, 'hello')
        return ws

    async def test_authenticated_join_sync_and_host_disband(self):
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner', protocol=2)
        room = await receive(owner, 'room_created')
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'join_room', name='guest', room=room['room'], protocol=2)
        await receive(guest, 'room_joined')
        await send(guest, 'seek_rel', delta=5, id='step')
        state = await receive(owner, 'sync_state')
        self.assertEqual(state['state']['position'], 5)
        await send(owner, 'leave_room')
        self.assertEqual((await receive(guest, 'room_closed'))['type'], 'room_closed')
        await send(guest, 'seek_rel', delta=5)
        self.assertEqual((await receive(guest, 'error'))['message'], 'Join a room first')

    async def test_guest_cannot_create_or_resume_owner(self):
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'create_room', name='intruder')
        await receive(guest, 'error')
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner', protocol=2)
        room = await receive(owner, 'room_created')
        await send(guest, 'resume_room', room=room['room'], token=room['token'])
        await receive(guest, 'error')
        await send(owner, 'create_room', name='second')
        await receive(owner, 'error')

    async def test_http_auth_and_proxy_host_block(self):
        for path, headers in (('/', {}), ('/room/wrong', {}),
                              (self.host.host_path, {'CF-Connecting-IP': '1.2.3.4'}),
                              (self.host.guest_path, {'Origin': 'https://example.com'})):
            with self.assertRaises(InvalidStatus) as caught:
                await connect(self.base + path, additional_headers=headers)
            self.assertEqual(caught.exception.response.status_code, 403)

    async def test_stop_notifies_guests_and_releases_listener(self):
        owner = await self.socket(self.host.host_path)
        await send(owner, 'create_room', name='owner')
        room = await receive(owner, 'room_created')
        guest = await self.socket(self.host.guest_path)
        await send(guest, 'join_room', name='guest', room=room['room'])
        await receive(guest, 'room_joined')
        stop = asyncio.get_running_loop().run_in_executor(None, self.host.stop)
        await receive(guest, 'room_closed')
        self.assertTrue(await stop)
        with self.assertRaises(OSError):
            await connect(self.base + self.host.guest_path)


class InvitationTests(unittest.TestCase):
    def test_round_trip(self):
        endpoint = 'wss://example.trycloudflare.com/room/abcDEF123'
        self.assertEqual(parse_invitation(make_invitation(endpoint, '1234')), (endpoint, '1234'))

    def test_invalid_invitation(self):
        for value in ('1234', 'file:///room/key?room=1234', 'ws://user:pass@host/room/key?room=1234',
                      'ws://host:99999/room/key?room=1234', 'ws://host/host/key?room=1234',
                      'ws://host/room/key?room=１２３４'):
            with self.assertRaises(ValueError):
                parse_invitation(value)


class TunnelShutdownTests(unittest.TestCase):
    def test_native_process_stop_cleans_up_without_enum_callback_exception(self):
        from app.tunnel import PublicTunnel
        from PySide6.QtCore import QProcess
        tunnel = PublicTunnel()
        tunnel._temp = tempfile.TemporaryDirectory(prefix='tunnel-stop-qa-')
        temporary = Path(tunnel._temp.name)
        exceptions, failures = [], []
        tunnel.failed.connect(failures.append)
        try:
            with patch.object(sys, 'excepthook', lambda *args: exceptions.append(args[1])):
                tunnel.process.setProgram(sys.executable)
                tunnel.process.setArguments(['-c', 'import time; time.sleep(30)'])
                tunnel.process.start()
                self.assertTrue(tunnel.process.waitForStarted(3000))
                tunnel.timer.start(10000)
                tunnel.stop()
                APP.processEvents()
            self.assertEqual(exceptions, [])
            self.assertEqual(failures, [])
            self.assertEqual(tunnel.process.state(), QProcess.NotRunning)
            self.assertFalse(tunnel.timer.isActive())
            self.assertIsNone(tunnel._job)
            self.assertIsNone(tunnel._temp)
            self.assertFalse(temporary.exists())
        finally:
            tunnel.stop()
            tunnel.deleteLater()

    def test_native_failed_start_emits_friendly_error_without_enum_exception(self):
        from app.tunnel import PublicTunnel
        tunnel = PublicTunnel()
        exceptions, failures = [], []
        tunnel.failed.connect(failures.append)
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(
                    sys, 'excepthook', lambda *args: exceptions.append(args[1])):
                tunnel.process.setProgram(str(Path(directory) / 'missing-helper.exe'))
                tunnel.process.start()
                self.assertFalse(tunnel.process.waitForStarted(3000))
                APP.processEvents()
            self.assertEqual(exceptions, [])
            self.assertEqual(len(failures), 1)
            self.assertIn('无法启动', failures[0])
        finally:
            tunnel.stop()
            tunnel.deleteLater()


class WorkerShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_drains_background_keepalive_before_loop_close(self):
        started, cleaned = threading.Event(), threading.Event()
        class Worker(NetworkClient):
            async def _connect_loop(self):
                async def keepalive():
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        cleaned.set()
                asyncio.create_task(keepalive())
                await asyncio.Event().wait()
        worker = Worker()
        worker.start()
        try:
            deadline = time.monotonic() + 3
            while not started.is_set():
                self.assertLess(time.monotonic(), deadline)
                await asyncio.sleep(.01)
            self.assertTrue(await asyncio.get_running_loop().run_in_executor(None, worker.stop))
            self.assertTrue(cleaned.is_set())
            self.assertTrue(worker.stop())
        finally:
            worker.stop()


@unittest.skipUnless(sys.platform == 'win32', 'Windows process ownership')
class ProcessOwnershipTests(unittest.TestCase):
    def test_closing_job_terminates_only_owned_helper(self):
        from app.windows_job import own_process, close_job
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job = own_process(child.pid)
            close_job(job)
            child.wait(timeout=3)
            self.assertIsNotNone(child.returncode)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
