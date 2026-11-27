"""Ephemeral audio streams tied to live room memberships."""
import asyncio
import secrets
import time
from dataclasses import dataclass

from websockets.exceptions import ConnectionClosed

VOICE_LIMIT = 6
MAX_FRAME = 256


@dataclass
class Stream:
    slot: int
    queue: asyncio.Queue
    task: asyncio.Task


class VoiceRelay:
    def __init__(self):
        self.tickets = {}
        self.streams = {}

    def issue(self, member):
        self.revoke(member)
        ticket = secrets.token_urlsafe(32)
        self.tickets[ticket] = member
        member.voice_ticket = ticket
        return ticket

    def revoke(self, member):
        ticket = getattr(member, 'voice_ticket', None)
        self.tickets.pop(ticket, None)
        stream = self.streams.pop(ticket, None)
        if stream:
            stream.task.cancel()
        member.voice_ticket = None

    async def _write(self, ws, queue):
        while True:
            created, frame = await queue.get()
            if time.monotonic() - created < .12:
                await asyncio.wait_for(ws.send(frame), .3)

    async def handle(self, ws, room):
        stream = None
        ticket = None
        tasks = []
        try:
            ticket = await asyncio.wait_for(ws.recv(), 3)
            member = self.tickets.get(ticket) if isinstance(ticket, str) else None
            if not member or member.peer is None or room.members.get(member.token) is not member:
                await ws.close(1008)
                return
            slots = {item.slot for item in self.streams.values()}
            slot = next((i for i in range(VOICE_LIMIT) if i not in slots), None)
            if slot is None or ticket in self.streams:
                await ws.close(1013)
                return
            stream = Stream(slot, asyncio.Queue(maxsize=5), asyncio.current_task())
            self.streams[ticket] = stream
            await ws.send('ready')
            tasks = [asyncio.create_task(self._write(ws, stream.queue)),
                     asyncio.create_task(self._read(ws, ticket, slot))]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (ConnectionClosed, asyncio.TimeoutError):
            pass
        finally:
            if stream is not None and self.streams.get(ticket) is stream:
                del self.streams[ticket]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await ws.close()

    async def _read(self, ws, ticket, slot):
        allowance = 10
        last = time.monotonic()
        async for frame in ws:
            now = time.monotonic()
            allowance = min(10, allowance + (now - last) * 55)
            last = now
            if not isinstance(frame, bytes) or not 1 <= len(frame) <= MAX_FRAME or allowance < 1:
                await ws.close(1008)
                return
            allowance -= 1
            packet = (now, bytes([slot]) + frame)
            for key, target in self.streams.items():
                if key != ticket:
                    if target.queue.full():
                        target.queue.get_nowait()
                    target.queue.put_nowait(packet)
