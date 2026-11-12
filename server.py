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
from app.chat_media import MAX_MESSAGE_BYTES, MAX_HISTORY_BYTES, MAX_OUTBOX_BYTES, wire_size

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
        self.large_images = False
        self.queued_bytes = 0

    def send(self, message):
        if self.failed:
            return
        if message.get('image_large') is not None and not self.large_images:
            message = {key: value for key, value in message.items() if key != 'image_large'}
        if (not self.large_images and message.get('type') == 'chat' and message.get('image')
                and wire_size(message) > 64000):
            message = dict(message, message='[图片]')
        # Only unsolicited snapshots are coalesced; replies and chat stay ordered.
        if message.get("type") == "sync_state" and not message.get("request_id"):
            self.queue = deque(item for item in self.queue
                               if item.get("type") != "sync_state" or item.get("request_id"))
            self.queued_bytes = sum(wire_size(item) for item in self.queue)
        size = wire_size(message)
        if len(self.queue) >= self.limit or self.queued_bytes + size > MAX_OUTBOX_BYTES:
            self.failed = True
        else:
            self.queue.append(message)
            self.queued_bytes += size
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
                self.queued_bytes -= wire_size(message)
                timeout = max(20, self.send_timeout) if message.get('image_large') else self.send_timeout
                await asyncio.wait_for(
                    self.ws.send(json.dumps(message, ensure_ascii=False)), timeout)
            self.wakeup.clear()


class Member:
    def __init__(self, name, peer):
        self.name = name
        self.requested_name = name
        self.peer_id = secrets.token_hex(16)
        self.token = secrets.token_urlsafe(32)
        self.peer = peer
        self.expires = None
        self.seen = OrderedDict()
        self.seen_chats = OrderedDict()


class Room:
    def __init__(self, code):
        self.code = code
        self.members = {}
        self.watch_mode = 'sync'
        self.publisher_id = None
        self.stream = {'active': False}
        self.position = 0.0
        self.playing = False
        self.updated_at = time.monotonic()
        self.version = 0
        self.chat_seq = 0
        self.history = deque(maxlen=100)
        self.history_sizes = deque()
        self.history_bytes = 0

    def remember_chat(self, token, event, size):
        if len(self.history) == self.history.maxlen:
            self.history.popleft()
            self.history_bytes -= self.history_sizes.popleft()
        self.history.append((token, event))
        self.history_sizes.append(size)
        self.history_bytes += size
        while self.history_bytes > MAX_HISTORY_BYTES:
            self.history.popleft()
            self.history_bytes -= self.history_sizes.popleft()

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
    def __init__(self, grace_period=60, hosted=False):
        self.rooms = {}
        self.hosted = hosted
        self.owner_token = None
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
                    if self.hosted and token == self.owner_token:
                        self.disband(room)
                        break
                    del room.members[token]
            if not room.members:
                self.rooms.pop(code, None)

    def disband(self, room):
        self.broadcast(room, {"type": "room_closed", "message": "房主已离开，房间已解散"})
        self.rooms.pop(room.code, None)
        room.members.clear()

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
        if intentional and self.hosted and member.token == self.owner_token:
            self.disband(room)
            member.peer = None
            return
        member.peer = None
        if intentional:
            room.members.pop(member.token, None)
        else:
            member.expires = time.monotonic() + self.grace_period
        self.broadcast(room, {"type": "member_left", "name": member.name,
                              "members": room.member_names, "peer_id": member.peer_id})
        if not room.members:
            self.rooms.pop(room.code, None)

    def _p2p(self, room, member, msg):
        if room.watch_mode != 'p2p':
            raise ValueError('This is not a P2P room')
        publisher = next((m for m in room.members.values() if m.peer_id == room.publisher_id), None)
        if publisher is None or publisher.peer is None:
            raise ValueError('Publisher is offline')
        kind = msg['type']
        if kind == 'p2p_ready':
            if member is publisher:
                raise ValueError('Publisher cannot subscribe to itself')
            publisher.peer.send({'type': kind, 'from_peer': member.peer_id})
        elif kind == 'p2p_state':
            if member is not publisher:
                raise ValueError('Only the publisher can change stream state')
            if not isinstance(msg.get('active'), bool):
                raise ValueError('Invalid stream state')
            state = {'active': False}
            if msg['active']:
                stream_id = msg.get('stream_id')
                if not isinstance(stream_id, str) or len(stream_id) != 32 or any(c not in '0123456789abcdef' for c in stream_id):
                    raise ValueError('Invalid stream identity')
                if not isinstance(msg.get('title'), str) or len(msg['title']) > 240 or not isinstance(msg.get('playing'), bool):
                    raise ValueError('Invalid stream metadata')
                duration, position = self._position(msg.get('duration')), self._position(msg.get('position'))
                if duration > 1000000 or position > 1000000:
                    raise ValueError('Invalid media duration')
                state = {'active': True, 'stream_id': stream_id, 'title': msg['title'],
                         'duration': duration, 'position': position, 'playing': msg['playing']}
            room.stream = state
            self.broadcast(room, {'type': kind, 'stream': dict(state)})
        elif kind == 'p2p_signal':
            target = next((m for m in room.members.values() if m.peer_id == msg.get('target')), None)
            if target is None or target is member or target.peer is None:
                raise ValueError('Media peer is unavailable')
            if member is not publisher and target is not publisher:
                raise ValueError('Viewer-to-viewer signaling is not allowed')
            signal_kind = msg.get('kind')
            if signal_kind != ('offer' if member is publisher else 'answer'):
                raise ValueError('Invalid signaling direction')
            if not room.stream.get('active') or msg.get('stream_id') != room.stream.get('stream_id'):
                raise ValueError('Stream session expired')
            sdp, connection_id = msg.get('sdp'), msg.get('connection_id')
            if not isinstance(sdp, str) or not 0 < len(sdp) <= 65536:
                raise ValueError('Invalid session description')
            if not isinstance(connection_id, str) or len(connection_id) != 32 or any(c not in '0123456789abcdef' for c in connection_id):
                raise ValueError('Invalid connection identity')
            target.peer.send({'type': kind, 'kind': signal_kind, 'sdp': sdp,
                              'stream_id': room.stream['stream_id'], 'connection_id': connection_id,
                              'from_peer': member.peer_id})
        else:
            raise ValueError('Unknown P2P message')

    @staticmethod
    def _position(value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Position must be finite")
        return max(0.0, value)

    async def handle(self, ws, is_host=False):
        peer = Peer(ws)
        peer.is_host = is_host
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
                    if not isinstance(mtype, str):
                        raise ValueError('Invalid message type')
                    if mtype in ("create_room", "join_room", "resume_room"):
                        self._expire()
                        if member is not None:
                            raise ValueError("Leave the current room first")
                        peer.protocol = 2 if msg.get("protocol") == 2 else 1
                        peer.large_images = msg.get('chat_media_bytes') == MAX_MESSAGE_BYTES
                        if mtype == "resume_room":
                            candidate = self.rooms.get(msg.get("room"))
                            restored = candidate.members.get(msg.get("token")) if candidate else None
                            if restored is None:
                                peer.send({"type": "session_expired",
                                           "message": "Room session expired or server restarted"})
                                continue
                            if self.hosted and restored.token == self.owner_token and not peer.is_host:
                                raise ValueError("Host connection required")
                            if candidate.watch_mode == 'p2p' and msg.get('p2p') != 1:
                                raise ValueError('This room requires a P2P-capable client')
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
                                if self.hosted and (not peer.is_host or self.rooms):
                                    raise ValueError("Only the host can create this room")
                                mode = msg.get('watch_mode', 'sync')
                                if mode not in ('sync', 'p2p'):
                                    raise ValueError('Unknown watching mode')
                                if mode == 'p2p' and (not self.hosted or msg.get('p2p') != 1):
                                    raise ValueError('P2P requires an embedded host and compatible client')
                                room = Room(self._generate_code())
                                room.watch_mode = mode
                                self.rooms[room.code] = room
                            else:
                                room = self.rooms.get(msg.get("room"))
                                if room is None:
                                    raise ValueError("Room not found")
                            if room.watch_mode == 'p2p' and msg.get('p2p') != 1:
                                raise ValueError('This room requires Python 3.11+ and requirements-p2p.txt')
                            member = Member(name, peer)
                            member.name = room.available_name(member.requested_name)
                            room.members[member.token] = member
                            if mtype == 'create_room':
                                room.publisher_id = member.peer_id
                            if self.hosted and mtype == "create_room":
                                self.owner_token = member.token
                            cursor = room.chat_seq
                        peer.send({"type": "room_created" if mtype == "create_room" else "room_joined",
                                   "room": room.code, "name": member.name,
                                   "token": member.token, "protocol": 2,
                                   "peer_id": member.peer_id, "publisher_id": room.publisher_id,
                                   "watch_mode": room.watch_mode, "stream": room.stream,
                                   "chat_seq": cursor, "chat_images": True, "chat_gifs": True,
                                   "chat_media_bytes": MAX_MESSAGE_BYTES,
                                   "resumed": mtype == "resume_room", "members": room.member_names,
                                   "state": room.snapshot()})
                        if mtype == "resume_room":
                            if room.history and cursor < room.history[0][1]["seq"] - 1:
                                peer.send({"type": "delivery_failed",
                                           "message": "离线期间聊天过多，部分较早记录已过期"})
                            for sender_token, event in room.history:
                                if event["seq"] > cursor and sender_token != member.token:
                                    peer.send(event)
                        self.broadcast(room, {"type": "member_joined", "name": member.name,
                                              "members": room.member_names, "peer_id": member.peer_id}, exclude=member)
                        continue

                    if mtype == "leave_room":
                        self._detach(room, member, peer, intentional=True)
                        room = member = None
                        peer.send({"type": "left_room"})
                        continue
                    if member is None or member.peer is not peer or room.code not in self.rooms:
                        raise ValueError("Join a room first")
                    message_id = msg.get("id")
                    if message_id is not None and (not isinstance(message_id, str) or len(message_id) > 64):
                        raise ValueError("Invalid message ID")
                    seen = member.seen_chats if mtype == "chat" else member.seen
                    if message_id and message_id in seen:
                        peer.send({"type": "ack", "id": message_id})
                        continue

                    if mtype.startswith('p2p_'):
                        self._p2p(room, member, msg)
                        if message_id:
                            seen[message_id] = True
                            while len(seen) > 512:
                                seen.popitem(last=False)
                            peer.send({'type': 'ack', 'id': message_id})
                        continue
                    if room.watch_mode == 'p2p' and mtype in ('load', 'play', 'pause', 'seek', 'seek_rel', 'sync_push', 'key_press'):
                        raise ValueError('P2P playback is controlled by the publisher')
                    if mtype == "sync_request":
                        peer.send({"type": "sync_state", "room": room.code,
                                   "request_id": msg.get("request_id"), "state": room.snapshot()})
                        continue
                    elif mtype == "chat":
                        message = str(msg.get("message", ""))[:4000]
                        picture = msg.get('image')
                        if picture is not None:
                            from app.chat_media import image_bytes
                            image_bytes(picture, legacy=True)
                        animation = msg.get('animation')
                        if animation is not None:
                            from app.chat_media import image_bytes
                            if picture is None or not image_bytes(animation, legacy=True).startswith((b'GIF87a', b'GIF89a')):
                                raise ValueError('Invalid GIF attachment')
                        large = msg.get('image_large')
                        if large is not None:
                            from app.chat_media import image_bytes
                            if picture is None or not peer.large_images:
                                raise ValueError('Large image capability required')
                            image_bytes(large)
                        room.chat_seq += 1
                        event = {"type": "chat", "from": member.name,
                                 "message": message, "id": message_id, "seq": room.chat_seq}
                        if picture is not None:
                            event['image'] = picture
                        if animation is not None:
                            event['animation'] = animation
                        if large is not None:
                            event['image_large'] = large
                        size = wire_size(event)
                        if size > MAX_MESSAGE_BYTES:
                            room.chat_seq -= 1
                            raise ValueError('Image message is too large')
                        room.remember_chat(member.token, event, size)
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
                         ping_timeout=30, close_timeout=2, max_size=MAX_MESSAGE_BYTES, max_queue=4) as listener:
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
