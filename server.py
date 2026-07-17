#!/usr/bin/env python3
"""WebSocket server for xiangjian-guanying - handles rooms and playback sync."""
from __future__ import annotations

import asyncio
import json
import random
import logging
from typing import Dict, List, Optional
from websockets.asyncio.server import serve

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("server")


class Room:
    """A watching room containing connected clients and current playback state."""

    def __init__(self, code: str):
        self.code = code
        self.clients: Dict[str, object] = {}
        self.state = {
            "playing": False,
            "position": 0.0,
            "path": "",
            "paused_at": 0.0,
        }

    @property
    def member_count(self) -> int:
        return len(self.clients)

    @property
    def member_names(self) -> List[str]:
        return list(self.clients.keys())


class Server:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def _generate_code(self) -> str:
        for _ in range(100):
            code = f"{random.randint(0, 9999):04d}"
            if code not in self.rooms:
                return code
        raise RuntimeError("No available room codes")

    async def broadcast(self, room: Room, msg: dict, exclude: Optional[str] = None):
        data = json.dumps(msg, ensure_ascii=False)
        tasks = []
        for name, ws in room.clients.items():
            if name != exclude:
                tasks.append(asyncio.create_task(ws.send(data)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def handle(self, ws):
        client_name = ""
        current_room: Optional[Room] = None

        async for raw in ws:
            try:
                msg = json.loads(raw)
                mtype = msg.get("type", "")
            except json.JSONDecodeError:
                await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            try:
                if mtype == "create_room":
                    code = self._generate_code()
                    name = msg.get("name", "Host").strip()
                    current_room = Room(code)
                    self.rooms[code] = current_room
                    client_name = name
                    current_room.clients[name] = ws
                    log.info(f"Room {code} created by {name}")
                    await ws.send(json.dumps({"type": "room_created", "room": code, "members": current_room.member_names}))

                elif mtype == "join_room":
                    code = msg.get("room", "")
                    name = msg.get("name", "Anonymous").strip()
                    if not code or code not in self.rooms:
                        await ws.send(json.dumps({"type": "error", "message": "Room not found"}))
                        continue
                    room = self.rooms[code]
                    if name in room.clients:
                        name = f"{name}_{len(room.clients)}"
                    client_name = name
                    current_room = room
                    room.clients[name] = ws
                    log.info(f"{name} joined room {code}")
                    await ws.send(json.dumps({
                        "type": "room_joined",
                        "room": code,
                        "name": name,
                        "members": room.member_names,
                        "state": {"playing": room.state["playing"], "position": room.state["position"]},
                    }))
                    await self.broadcast(room, {
                        "type": "member_joined",
                        "name": name,
                        "members": room.member_names,
                    }, exclude=name)

                elif mtype == "leave_room":
                    if current_room and client_name in current_room.clients:
                        del current_room.clients[client_name]
                        log.info(f"{client_name} left room {current_room.code}")
                        members = current_room.member_names
                        await self.broadcast(current_room, {
                            "type": "member_left",
                            "name": client_name,
                            "members": members,
                        })
                        if current_room.member_count == 0:
                            del self.rooms[current_room.code]
                            log.info(f"Room {current_room.code} closed (empty)")
                    current_room = None
                    client_name = ""
                    await ws.send(json.dumps({"type": "left_room"}))

                elif mtype == "load":
                    if current_room:
                        current_room.state["path"] = msg.get("path", "")
                        current_room.state["position"] = 0.0
                        current_room.state["playing"] = False
                        # Each client opens their own file -- no broadcast

                elif mtype == "play":
                    if current_room:
                        current_room.state["playing"] = True
                        current_room.state["position"] = msg.get("position", 0.0)
                        await self.broadcast(current_room, {
                            "type": "play",
                            "position": current_room.state["position"],
                            "from": client_name,
                        }, exclude=client_name)

                elif mtype == "pause":
                    if current_room:
                        current_room.state["playing"] = False
                        current_room.state["position"] = msg.get("position", 0.0)
                        current_room.state["paused_at"] = current_room.state["position"]
                        await self.broadcast(current_room, {
                            "type": "pause",
                            "position": current_room.state["position"],
                            "from": client_name,
                        }, exclude=client_name)

                elif mtype == "key_press":
                    if current_room:
                        await self.broadcast(current_room, {
                            "type": "key_press",
                            "key": msg.get("key", ""),
                            "from": client_name,
                        }, exclude=client_name)

                elif mtype == "seek_rel":
                    if current_room:
                        await self.broadcast(current_room, {
                            "type": "seek_rel",
                            "delta": msg.get("delta", 0),
                            "from": client_name,
                        }, exclude=client_name)

                elif mtype == "seek":
                    if current_room:
                        current_room.state["position"] = msg.get("position", 0.0)
                        await self.broadcast(current_room, {
                            "type": "seek",
                            "position": current_room.state["position"],
                            "from": client_name,
                        }, exclude=client_name)

                elif mtype == "chat":
                    if current_room:
                        await self.broadcast(current_room, {
                            "type": "chat",
                            "from": client_name,
                            "message": msg.get("message", ""),
                        }, exclude=client_name)

                elif mtype == "sync_push":
                    if current_room:
                        pos = msg.get("position", 0.0)
                        playing = msg.get("playing", False)
                        current_room.state["position"] = pos
                        current_room.state["playing"] = playing
                        await self.broadcast(current_room, {
                            "type": "sync_to",
                            "position": pos,
                            "playing": playing,
                            "from": client_name,
                        }, exclude=client_name)

                else:
                    await ws.send(json.dumps({"type": "error", "message": f"Unknown type: {mtype}"}))

            except Exception as e:
                log.error(f"Error handling message: {e}")
                await ws.send(json.dumps({"type": "error", "message": str(e)}))

        if current_room and client_name in current_room.clients:
            del current_room.clients[client_name]
            log.info(f"{client_name} disconnected from room {current_room.code}")
            if current_room.member_count > 0:
                await self.broadcast(current_room, {
                    "type": "member_left",
                    "name": client_name,
                    "members": current_room.member_names,
                })
            else:
                del self.rooms[current_room.code]
                log.info(f"Room {current_room.code} closed (empty)")


async def main():
    server = Server()
    log.info("Server starting on 0.0.0.0:9877")
    async with serve(server.handle, "0.0.0.0", 9877) as s:
        await s.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())