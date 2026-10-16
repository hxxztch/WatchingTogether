"""Real-socket reconnect regressions plus deterministic playback policy checks."""
import asyncio
import json
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, Qt
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from app.network import NetworkClient
from app.sync import PlaybackSynchronizer
from server import Member, Peer, Room, Server


QT_APP = QCoreApplication.instance() or QCoreApplication([])


async def until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Condition was not reached before timeout")
        await asyncio.sleep(0.01)


async def receive(ws, kind):
    async def read():
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == kind:
                return msg
        raise AssertionError("Socket closed before " + kind)
    return await asyncio.wait_for(read(), 3)


async def send(ws, kind, **fields):
    await ws.send(json.dumps({"type": kind, **fields}))


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = await Server().__aenter__()
        self.listener = await serve(self.server.handle, "127.0.0.1", 0,
                                    ping_interval=10, ping_timeout=30, close_timeout=0.2)
        self.port = self.listener.sockets[0].getsockname()[1]
        self.url = "ws://127.0.0.1:" + str(self.port)
        self.sockets = []
        self.workers = []

    async def asyncTearDown(self):
        for worker in self.workers:
            stopped = await asyncio.get_running_loop().run_in_executor(None, worker.stop)
            self.assertTrue(stopped, "Network QThread did not stop")
        for ws in self.sockets:
            await ws.close()
        self.listener.close()
        await self.listener.wait_closed()
        await self.server.__aexit__()

    async def socket(self):
        ws = await connect(self.url, close_timeout=0.2)
        self.sockets.append(ws)
        await receive(ws, "hello")
        return ws

    async def host(self):
        ws = await self.socket()
        await send(ws, "create_room", name="host", protocol=2)
        return ws, await receive(ws, "room_created")

    async def worker(self, room):
        client = NetworkClient(self.url)
        events, errors, latencies = [], [], []
        client.signals.message_received.connect(events.append, Qt.DirectConnection)
        client.signals.error_occurred.connect(errors.append, Qt.DirectConnection)
        client.signals.latency_updated.connect(latencies.append, Qt.DirectConnection)
        self.workers.append(client)
        client.start()
        await until(lambda: client._ws is not None)
        client.send({"type": "join_room", "room": room, "name": "viewer"})
        await until(lambda: client._ready)
        return client, events, errors, latencies

    async def test_integrated_client_stops_after_host_unreachable_deadline(self):
        host, info = await self.host()
        client, events, errors, latencies = await self.worker(info['room'])
        client.recovery_timeout = .1
        self.listener.close()
        await self.listener.wait_closed()
        await until(lambda: any(event['type'] == 'room_closed' for event in events))
        await until(lambda: not client.isRunning())
        self.assertIsNone(client._session)
        self.assertFalse(client._ready)

    async def test_abrupt_disconnect_cleans_members_and_resumes_identity(self):
        host, info = await self.host()
        guest = await self.socket()
        await send(guest, "join_room", room=info["room"], name="viewer", protocol=2)
        joined = await receive(guest, "room_joined")
        guest.transport.abort()
        left = await receive(host, "member_left")
        self.assertEqual(left["members"], ["host"])
        replacement = await self.socket()
        await send(replacement, "resume_room", room=info["room"], token=joined["token"], protocol=2)
        resumed = await receive(replacement, "room_joined")
        self.assertEqual(resumed["name"], "viewer")
        self.assertEqual(resumed["members"], ["host", "viewer"])
        self.assertEqual(len(self.server.rooms[info["room"]].members), 2)

    async def test_replacement_connection_cannot_be_removed_by_old_finally(self):
        original, info = await self.host()
        replacement = await self.socket()
        await send(replacement, "resume_room", room=info["room"], token=info["token"], protocol=2)
        await receive(replacement, "room_joined")
        await original.wait_closed()
        room = self.server.rooms[info["room"]]
        self.assertEqual(room.member_names, ["host"])
        await send(replacement, "sync_request", request_id="still-here")
        self.assertEqual((await receive(replacement, "sync_state"))["request_id"], "still-here")

    async def test_repeated_disconnect_and_fresh_join_reuses_online_name(self):
        host, info = await self.host()
        for _ in range(4):
            guest = await self.socket()
            await send(guest, "join_room", room=info["room"], name="viewer", protocol=2)
            joined = await receive(guest, "room_joined")
            self.assertEqual(joined["name"], "viewer")
            guest.transport.abort()
            self.assertEqual((await receive(host, "member_left"))["members"], ["host"])
        # Recovery tokens still exist, but don't occupy online display names.
        self.assertEqual(len(self.server.rooms[info["room"]].members), 5)

    async def test_explicit_leave_and_rejoin_does_not_accumulate_suffix(self):
        host, info = await self.host()
        guest = await self.socket()
        for _ in range(4):
            await send(guest, "join_room", room=info["room"], name="viewer", protocol=2)
            joined = await receive(guest, "room_joined")
            self.assertEqual(joined["name"], "viewer")
            await send(guest, "leave_room")
            await receive(guest, "left_room")
            self.assertNotIn(joined["token"], self.server.rooms[info["room"]].members)

    async def test_resume_with_online_duplicate_renames_without_stealing_session(self):
        host, info = await self.host()
        first = await self.socket()
        await send(first, "join_room", room=info["room"], name="viewer", protocol=2)
        original = await receive(first, "room_joined")
        first.transport.abort()
        await receive(host, "member_left")
        second = await self.socket()
        await send(second, "join_room", room=info["room"], name="viewer", protocol=2)
        newcomer = await receive(second, "room_joined")
        self.assertEqual(newcomer["name"], "viewer")
        self.assertNotEqual(newcomer["token"], original["token"])
        restored = await self.socket()
        await send(restored, "resume_room", room=info["room"], token=original["token"], protocol=2)
        resumed = await receive(restored, "room_joined")
        self.assertEqual(resumed["name"], "viewer_1")
        self.assertEqual(resumed["token"], original["token"])
        self.assertEqual(resumed["members"], ["host", "viewer_1", "viewer"])
        # A second resume starts from the requested nickname, not viewer_1_1.
        restored.transport.abort()
        await receive(second, "member_left")
        await send(second, "leave_room")
        await receive(second, "left_room")
        again = await self.socket()
        await send(again, "resume_room", room=info["room"], token=original["token"], protocol=2)
        self.assertEqual((await receive(again, "room_joined"))["name"], "viewer")

    async def test_literal_numeric_suffix_and_online_duplicates_are_preserved(self):
        host, info = await self.host()
        for expected in ("viewer_1", "viewer_1_1", "viewer_1_2"):
            guest = await self.socket()
            await send(guest, "join_room", room=info["room"], name="viewer_1", protocol=2)
            self.assertEqual((await receive(guest, "room_joined"))["name"], expected)

    async def test_timeline_advances_and_pause_zero_survives_resume(self):
        host, info = await self.host()
        await send(host, "play", position=10, id="play")
        first = (await receive(host, "sync_state"))["state"]
        await asyncio.sleep(0.06)
        await send(host, "sync_request", request_id="clock")
        second = (await receive(host, "sync_state"))["state"]
        self.assertGreater(second["position"], first["position"] + 0.03)
        await send(host, "pause", position=0, id="pause")
        await receive(host, "sync_state")
        host.transport.abort()
        await until(lambda: not self.server.rooms[info["room"]].member_names)
        resumed = await self.socket()
        await send(resumed, "resume_room", room=info["room"], token=info["token"], protocol=2)
        state = (await receive(resumed, "room_joined"))["state"]
        self.assertEqual(state["position"], 0)
        self.assertFalse(state["playing"])

    async def test_relative_seek_updates_authoritative_position_once(self):
        ws, info = await self.host()
        await send(ws, "seek", position=10, id="seek")
        await receive(ws, "ack")
        await send(ws, "seek_rel", delta=2.5, id="relative")
        await receive(ws, "ack")
        await send(ws, "seek_rel", delta=2.5, id="relative")
        await receive(ws, "ack")
        self.assertEqual(self.server.rooms[info["room"]].snapshot()["position"], 12.5)

    async def test_local_media_load_does_not_reset_room(self):
        ws, info = await self.host()
        await send(ws, "seek", position=42, id="seek")
        await receive(ws, "ack")
        await send(ws, "load", path="local.mp4", id="load")
        state = (await receive(ws, "sync_state"))["state"]
        self.assertEqual(state["position"], 42)

    async def test_intentional_leave_invalidates_resume(self):
        ws, info = await self.host()
        await send(ws, "leave_room")
        await receive(ws, "left_room")
        await send(ws, "resume_room", room=info["room"], token=info["token"], protocol=2)
        await receive(ws, "session_expired")
        self.assertNotIn(info["room"], self.server.rooms)

    async def test_expired_session_is_not_resurrected(self):
        self.server.grace_period = 0.02
        ws, info = await self.host()
        await ws.close()
        await until(lambda: not self.server.rooms[info["room"]].member_names)
        await asyncio.sleep(0.04)
        replacement = await self.socket()
        await send(replacement, "resume_room", room=info["room"], token=info["token"], protocol=2)
        await receive(replacement, "session_expired")

    async def test_invalid_messages_do_not_break_connection(self):
        ws = await self.socket()
        for raw in ("{", "[]", '{"type": "join_room", "room": []}'):
            await ws.send(raw)
            await receive(ws, "error")
        await send(ws, "create_room", name="valid", protocol=2)
        info = await receive(ws, "room_created")
        await send(ws, "seek", position=float("nan"))
        await receive(ws, "error")
        self.assertEqual(self.server.rooms[info["room"]].position, 0)

    async def test_legacy_client_receives_absolute_seek(self):
        host, info = await self.host()
        old = await self.socket()
        await send(old, "join_room", room=info["room"], name="old")
        await receive(old, "room_joined")
        await send(host, "seek_rel", delta=2.5)
        self.assertEqual((await receive(old, "seek"))["position"], 2.5)

    async def test_worker_recovers_room_discards_offline_controls_and_shows_latency(self):
        host, info = await self.host()
        client, events, errors, latencies = await self.worker(info["room"])
        token = client._session["token"]
        await until(lambda: bool(latencies))
        client._loop.call_soon_threadsafe(client._ws.transport.abort)
        await until(lambda: not client._ready)
        client.send({"type": "pause", "position": 999})
        await send(host, "seek", position=42)
        await receive(host, "sync_state")
        await until(lambda: any(msg.get("resumed") for msg in events))
        self.assertTrue(client._ready)
        self.assertEqual(client._session["token"], token)
        self.assertEqual(self.server.rooms[info["room"]].position, 42)
        self.assertTrue(any("未发送" in error for error in errors))
        self.assertEqual(self.server.rooms[info["room"]].member_names, ["host", "viewer"])

    async def test_lost_chat_ack_is_retried_without_duplicate_and_offline_chat_replays(self):
        host, info = await self.host()
        client, events, _, _ = await self.worker(info["room"])
        member = self.server.rooms[info["room"]].members[client._session["token"]]
        original_send = member.peer.send
        member.peer.send = lambda msg: original_send(msg) if msg["type"] != "ack" else None
        client.send({"type": "chat", "message": "one copy"})
        self.assertEqual((await receive(host, "chat"))["message"], "one copy")
        await until(lambda: bool(client._pending_chats))
        client._loop.call_soon_threadsafe(client._ws.transport.abort)
        await until(lambda: not client._ready)
        await send(host, "chat", message="while offline", id="offline")
        await receive(host, "ack")
        await until(lambda: any(msg.get("message") == "while offline" for msg in events))
        await until(lambda: not client._pending_chats)
        room = self.server.rooms[info["room"]]
        self.assertEqual(room.chat_seq, 2)
        self.assertEqual(len(room.history), 2)

    async def test_worker_does_not_rejoin_after_leaving_offline(self):
        _, info = await self.host()
        client, events, _, _ = await self.worker(info["room"])
        client._loop.call_soon_threadsafe(client._ws.transport.abort)
        await until(lambda: not client._ready)
        client.send({"type": "leave_room"})
        await until(lambda: client._session is None)
        await until(lambda: client._ws is not None)
        self.assertFalse(client._ready)
        self.assertFalse(any(msg.get("resumed") for msg in events))

    async def test_server_restart_is_reported_as_expired_session(self):
        _, info = await self.host()
        client, events, _, _ = await self.worker(info["room"])
        self.listener.close()
        await self.listener.wait_closed()
        await self.server.__aexit__()
        self.server = await Server().__aenter__()
        self.listener = await serve(self.server.handle, "127.0.0.1", self.port, close_timeout=0.2)
        await until(lambda: any(msg["type"] == "session_expired" for msg in events))
        self.assertIsNone(client._session)
        self.assertFalse(client._ready)


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_peer_does_not_hold_up_healthy_peer(self):
        class Socket:
            def __init__(self, slow=False):
                self.messages = []
                self.slow = slow

            async def send(self, raw):
                if self.slow:
                    await asyncio.Event().wait()
                self.messages.append(json.loads(raw))

        server, room = Server(), Room("1234")
        slow_socket, good_socket = Socket(True), Socket()
        slow, good = Peer(slow_socket, send_timeout=0.05), Peer(good_socket)
        for name, peer in (("slow", slow), ("good", good)):
            member = Member(name, peer)
            room.members[member.token] = member
        tasks = [asyncio.create_task(slow.run()), asyncio.create_task(good.run())]
        try:
            server.broadcast(room, {"type": "chat", "message": "hello"})
            await until(lambda: bool(good_socket.messages), timeout=0.2)
            with self.assertRaises(asyncio.TimeoutError):
                await tasks[0]
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_snapshot_coalescing_and_queue_limit(self):
        peer = Peer(None, limit=3)
        for version in range(100):
            peer.send({"type": "sync_state", "state": {"version": version}})
        self.assertEqual(len(peer.queue), 1)
        self.assertEqual(peer.queue[0]["state"]["version"], 99)
        for _ in range(3):
            peer.send({"type": "chat"})
        self.assertTrue(peer.failed)
        self.assertEqual(len(peer.queue), 3)

    async def test_old_queued_control_is_not_sent(self):
        client = NetworkClient()
        client._send_queue = asyncio.Queue()
        client._send_queue.put_nowait((time.monotonic() - 60, {"type": "seek", "position": 999}))
        sent = []

        class Socket:
            async def send(self, value):
                sent.append(value)

        task = asyncio.create_task(client._send_loop(Socket()))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertFalse(sent)

    async def test_late_join_reply_after_leave_does_not_restore_session(self):
        client = NetworkClient()
        client._ws = object()
        client._send_queue = asyncio.Queue()
        client._membership_pending = True
        client._enqueue_command({"type": "leave_room"}, client._generation)
        client._handle_message({"type": "room_joined", "room": "1234", "token": "old"})
        self.assertIsNone(client._session)
        self.assertFalse(client._ready)


class PlaybackTests(unittest.TestCase):
    def test_resume_paused_at_zero_seeks_back_and_pauses(self):
        sync = PlaybackSynchronizer()
        plan = sync.plan({"position": 0, "playing": False, "version": 2}, 50, 100)
        self.assertEqual(plan, {"seek": 0, "speed": 1, "playing": False})

    def test_transit_and_ui_queue_delay_are_added_only_while_playing(self):
        sync = PlaybackSynchronizer()
        plan = sync.plan({"position": 10, "playing": True, "local_time": 100, "version": 1},
                         0, 200, now=102)
        self.assertEqual(plan["seek"], 12)

    def test_small_drift_uses_speed_and_returns_to_normal(self):
        sync = PlaybackSynchronizer()
        sync.version = 3
        state = {"position": 10, "playing": True, "version": 3}
        self.assertEqual(sync.plan(state, 9.5, 100)["speed"], 1.02)
        self.assertEqual(sync.plan(state, 10.5, 100)["speed"], 0.98)
        self.assertEqual(sync.plan(state, 10.05, 100)["speed"], 1)

    def test_old_revision_is_ignored_and_unloaded_media_waits(self):
        sync = PlaybackSynchronizer()
        sync.version = 5
        self.assertIsNone(sync.plan({"version": 4, "position": 99}, 10, 100))
        self.assertIsNone(sync.plan({"version": 6}, 0, 0))
        self.assertEqual(sync.version, 5)


if __name__ == "__main__":
    unittest.main()
