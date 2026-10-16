import asyncio
import json
import time
import unittest
import subprocess
import sys
import threading
from PySide6.QtCore import QCoreApplication
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
from app.hosting import EmbeddedHost, make_invitation, parse_invitation
from app.network import NetworkClient

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
        ws = await connect(self.base + path)
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
