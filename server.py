#!/usr/bin/env python3
"""Room server with resumable sessions and an authoritative playback timeline."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
import json
import logging
import math
import random
import secrets
import time
from app.version import SERVER_VERSION

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("server")


class Peer:
    """A bounded, independent outbox keeps a slow socket off the room's path."""

    def __init__(self, ws, limit=128, send_timeout=5):
        self.ws = ws
        self.protocol = 1
        self.queue = deque()
        self.wakeup = asyncio.Event()
        self.limit = limit
        self.send_timeout = send_timeout
        self.failed = False

    def send(self, message):
        if self.failed:
            return
        # Only unsolicited snapshots are coalesced; replies and chat stay ordered.
        if message.get("type") == "sync_state" and not message.get("request_id"):
            self.queue = deque(item for item in self.queue
                               if item.get("type") != "sync_state" or item.get("request_id"))
        if len(self.queue) >= self.limit:
            self.failed = True
        else:
            self.queue.append(message)
        self.wakeup.set()

    async def run(self):
        while True:
            await self.wakeup.wait()
            if self.failed:
                raise ConnectionError("Client output queue is full")
            while self.queue:
                if self.failed:
                    raise ConnectionError("Client output queue is full")
                message = self.queue.popleft()
                await asyncio.wait_for(
                    self.ws.send(json.dumps(message, ensure_ascii=False)), self.send_timeout)
            self.wakeup.clear()


class Member:
    def __init__(self, name, peer):
        self.name = name
        self.requested_name = name
        self.token = secrets.token_urlsafe(32)
        self.peer = peer
        self.expires = None
        self.seen = OrderedDict()
        self.seen_chats = OrderedDict()


class Room:
    def __init__(self, code):
        self.code = code
        self.members = {}
        self.position = 0.0
        self.playing = False
        self.updated_at = time.monotonic()
        self.version = 0
        self.chat_seq = 0
        self.history = deque(maxlen=100)

    @property
    def member_names(self):
        return [member.name for member in self.members.values() if member.peer is not None]

    def available_name(self, requested_name, exclude=None):
        """Only online members reserve display names; tokens identify sessions."""
        names = {member.name for member in self.members.values()
                 if member.peer is not None and member is not exclude}
        name, suffix = requested_name, 1
        while name in names:
            name = f"{requested_name}_{suffix}"
            suffix += 1
        return name

    def snapshot(self):
        now = time.monotonic()
        position = self.position + (now - self.updated_at if self.playing else 0)
        return {"position": position, "playing": self.playing,
                "version": self.version, "server_time": now}

    def update(self, position, playing):
        self.position = max(0.0, position)
        self.playing = playing
        self.updated_at = time.monotonic()
        self.version += 1


class Server:
    def __init__(self, grace_period=60):
        self.rooms = {}
        self.grace_period = grace_period
        self._maintenance = None

    async def __aenter__(self):
        self._maintenance = asyncio.create_task(self._maintain())
        return self

    async def __aexit__(self, *args):
        self._maintenance.cancel()
        await asyncio.gather(self._maintenance, return_exceptions=True)

    def _expire(self):
        now = time.monotonic()
        for code, room in list(self.rooms.items()):
            for token, member in list(room.members.items()):
                if member.peer is None and member.expires is not None and member.expires <= now:
                    del room.members[token]
            if not room.members:
                del self.rooms[code]

    async def _maintain(self):
        while True:
            self._expire()
            await asyncio.sleep(1)

    def _generate_code(self):
        for _ in range(100):
            code = f"{random.randint(0, 9999):04d}"
            if code not in self.rooms:
                return code
        raise ValueError("No available room codes")

    def broadcast(self, room, message, exclude=None):
        for member in list(room.members.values()):
            if member.peer is not None and member is not exclude:
                member.peer.send(message)

    def _detach(self, room, member, peer, intentional=False):
        # An old connection's finally must not remove its resumed replacement.
        if room is None or member is None or member.peer is not peer:
            return
        member.peer = None
        if intentional:
            room.members.pop(member.token, None)
        else:
            member.expires = time.monotonic() + self.grace_period
        self.broadcast(room, {"type": "member_left", "name": member.name,
                              "members": room.member_names})
        if not room.members:
            self.rooms.pop(room.code, None)

    @staticmethod
    def _position(value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Position must be finite")
        return max(0.0, value)

    async def handle(self, ws):
        peer = Peer(ws)
        peer.send({"type": "hello", "protocol": 2})
        reader = asyncio.create_task(self._receive(peer))
        writer = asyncio.create_task(peer.run())
        try:
            done, _ = await asyncio.wait([reader, writer], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ConnectionClosed, ConnectionError, asyncio.TimeoutError) as exc:
            log.info("Connection ended: %s", type(exc).__name__)
        finally:
            reader.cancel()
            writer.cancel()
            await asyncio.gather(reader, writer, return_exceptions=True)
            await ws.close()

    async def _receive(self, peer):
        room = member = None
        try:
            async for raw in peer.ws:
                msg = None
                try:
                    msg = json.loads(raw)
                    if not isinstance(msg, dict):
                        raise ValueError("Message must be an object")
                    mtype = msg.get("type")
                    if mtype in ("create_room", "join_room", "resume_room"):
                        self._expire()
                        if member is not None:
                            raise ValueError("Leave the current room first")
                        peer.protocol = 2 if msg.get("protocol") == 2 else 1
                        if mtype == "resume_room":
                            candidate = self.rooms.get(msg.get("room"))
                            restored = candidate.members.get(msg.get("token")) if candidate else None
                            if restored is None:
                                peer.send({"type": "session_expired",
                                           "message": "Room session expired or server restarted"})
                                continue
                            cursor = max(0, min(candidate.chat_seq, int(msg.get("chat_seq", 0))))
                            room, member = candidate, restored
                            old_peer = member.peer
                            member.name = room.available_name(member.requested_name, exclude=member)
                            member.peer = peer
                            member.expires = None
                            if old_peer is not None and old_peer is not peer:
                                old_peer.failed = True
                                old_peer.wakeup.set()
                        else:
                            name = str(msg.get("name", "")).strip()[:64] or "Anonymous"
                            if mtype == "create_room":
                                room = Room(self._generate_code())
                                self.rooms[room.code] = room
                            else:
                                room = self.rooms.get(msg.get("room"))
                                if room is None:
                                    raise ValueError("Room not found")
                            member = Member(name, peer)
                            member.name = room.available_name(member.requested_name)
                            room.members[member.token] = member
                            cursor = room.chat_seq
                        peer.send({"type": "room_created" if mtype == "create_room" else "room_joined",
                                   "room": room.code, "name": member.name,
                                   "token": member.token, "protocol": 2,
                                   "chat_seq": cursor,
                                   "resumed": mtype == "resume_room", "members": room.member_names,
                                   "state": room.snapshot()})
                        if mtype == "resume_room":
                            if room.history and cursor < room.history[0][1]["seq"] - 1:
                                peer.send({"type": "delivery_failed",
                                           "message": "离线期间聊天过多，仅恢复最近100条记录"})
                            for sender_token, event in room.history:
                                if event["seq"] > cursor and sender_token != member.token:
                                    peer.send(event)
                        self.broadcast(room, {"type": "member_joined", "name": member.name,
                                              "members": room.member_names}, exclude=member)
                        continue

                    if mtype == "leave_room":
                        self._detach(room, member, peer, intentional=True)
                        room = member = None
                        peer.send({"type": "left_room"})
                        continue
                    if member is None or member.peer is not peer:
                        raise ValueError("Join a room first")
                    message_id = msg.get("id")
                    if message_id is not None and (not isinstance(message_id, str) or len(message_id) > 64):
                        raise ValueError("Invalid message ID")
                    seen = member.seen_chats if mtype == "chat" else member.seen
                    if message_id and message_id in seen:
                        peer.send({"type": "ack", "id": message_id})
                        continue

                    if mtype == "sync_request":
                        peer.send({"type": "sync_state", "room": room.code,
                                   "request_id": msg.get("request_id"), "state": room.snapshot()})
                        continue
                    elif mtype == "chat":
                        message = str(msg.get("message", ""))[:4000]
                        room.chat_seq += 1
                        event = {"type": "chat", "from": member.name,
                                 "message": message, "id": message_id, "seq": room.chat_seq}
                        room.history.append((member.token, event))
                        self.broadcast(room, event, exclude=member)
                    elif mtype == "load":
                        # Opening each viewer's own media must not reset the shared clock.
                        peer.send({"type": "sync_state", "room": room.code, "state": room.snapshot()})
                    elif mtype in ("play", "pause", "seek", "seek_rel", "sync_push"):
                        state = room.snapshot()
                        playing = state["playing"]
                        position = state["position"]
                        if mtype == "seek_rel":
                            delta = float(msg.get("delta", 0))
                            if not math.isfinite(delta):
                                raise ValueError("Seek delta must be finite")
                            position = max(0, position + delta)
                            if "duration" in msg:
                                duration = self._position(msg["duration"])
                                if duration > 0:
                                    position = min(position, duration)
                        else:
                            position = self._position(msg.get("position", position))
                        if mtype in ("play", "pause"):
                            playing = mtype == "play"
                        elif mtype == "sync_push":
                            playing = bool(msg.get("playing", False))
                        room.update(position, playing)
                        state = room.snapshot()
                        event = {"type": "sync_state", "room": room.code, "state": state,
                                 "applied_id": message_id}
                        legacy_type = "seek" if mtype == "seek_rel" else mtype
                        legacy = {"type": "sync_state" if mtype == "sync_push" else legacy_type,
                                  "position": state["position"], "state": state, "from": member.name}
                        for target in room.members.values():
                            if target.peer is not None:
                                if target.peer.protocol >= 2:
                                    target.peer.send(event)
                                elif target is not member:
                                    target.peer.send(legacy)
                    elif mtype == "key_press":
                        self.broadcast(room, {"type": "key_press", "key": msg.get("key", ""),
                                              "from": member.name}, exclude=member)
                    else:
                        raise ValueError("Unknown message type")
                    if message_id:
                        seen[message_id] = True
                        while len(seen) > 512:
                            seen.popitem(last=False)
                        peer.send({"type": "ack", "id": message_id})
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    peer.send({"type": "error", "message": str(exc),
                               "id": msg.get("id") if isinstance(msg, dict) else None})
        finally:
            self._detach(room, member, peer)


async def main(host="0.0.0.0", port=9877):
    async with Server() as server:
        log.info("server-%s starting on %s:%s", SERVER_VERSION, host, port)
        log.info("Clients on this computer: ws://127.0.0.1:%s", port)
        log.info("Other computers: ws://<this PC's LAN or VPN IP>:%s ; Ctrl+C to stop", port)
        async with serve(server.handle, host, port, ping_interval=10,
                         ping_timeout=30, close_timeout=2, max_size=65536) as listener:
            await listener.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WatchingTogether standalone room server")
    parser.add_argument("--version", action="version", version="server-" + SERVER_VERSION)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9877)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        pass
