"""Async WebRTC engine. Each viewer has a separate authenticated peer connection."""
import asyncio
import logging
import time
import uuid

import av
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

from app.p2p.source import FileSource, SourceAudio, SourceVideo

log = logging.getLogger(__name__)
logging.getLogger('aioice').setLevel(logging.WARNING)


class P2PEngine:
    def __init__(self, send, status, mailbox):
        self.send, self.status, self.mailbox = send, status, mailbox
        self.source = None
        self.descriptor = None
        self.peers = {}
        self.viewers = set()
        self.tasks = set()
        self.lock = asyncio.Lock()
        self.closed = False

    def task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.warning('P2P task failed: %s', type(task.exception()).__name__)
            self.status('媒体连接失败，请重试', False)

    async def _close_peers(self):
        peers, self.peers = list(self.peers.values()), {}
        for item in peers:
            await item['pc'].close()

    async def load(self, path, position=0, playing=True):
        old = self.source
        await self._close_peers()
        self.source = None
        if old:
            await asyncio.to_thread(old.close)
        self.mailbox.reset()
        self.status('正在读取本地片源…', False)
        source = await asyncio.to_thread(FileSource, path, position, playing)
        if self.closed:
            await asyncio.to_thread(source.close)
            return
        self.source = source
        stream_id = uuid.uuid4().hex
        from pathlib import Path
        self.descriptor = {'stream_id': stream_id, 'title': Path(path).name,
                           'duration': source.duration, 'position': source.position,
                           'playing': playing, 'active': True}
        self.mailbox.reset(stream_id)
        self.send({'type': 'p2p_state', **self.descriptor})
        self.task(self._consume(SourceVideo(source), stream_id))
        if source.has_audio:
            self.task(self._consume(SourceAudio(source), stream_id))
        self.task(self._source_status(source))
        for peer_id in sorted(self.viewers):
            await self.offer(peer_id)
        self.status('房主推流已就绪', True)

    async def _source_status(self, source):
        while self.source is source and not self.closed:
            await asyncio.sleep(.5)
            if self.source is not source:
                return
            if source.error:
                self.status(source.error, False)
                await self.stop_source()
                return
            if source.duration and source.position >= source.duration and source.playing:
                source.pause(True)
            self.descriptor.update(position=source.position, playing=source.playing)
            self.send({'type': 'p2p_state', **self.descriptor})

    async def pause(self, paused):
        if self.source:
            self.source.pause(paused)
            self.descriptor.update(position=self.source.position, playing=not paused)
            self.send({'type': 'p2p_state', **self.descriptor})

    async def stop_source(self):
        await self._close_peers()
        source, self.source = self.source, None
        if source:
            await asyncio.to_thread(source.close)
        self.descriptor = None
        self.mailbox.reset()
        if not self.closed:
            self.send({'type': 'p2p_state', 'active': False})
            self.status('已停止推流，房间和聊天保留', False)

    def _peer(self, peer_id, connection_id):
        # First stage deliberately has no public STUN/TURN or relay fallback.
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        item = {'pc': pc, 'connection_id': connection_id}
        self.peers[peer_id] = item

        @pc.on('connectionstatechange')
        async def connection_changed():
            if self.peers.get(peer_id) is not item:
                return
            if pc.connectionState == 'connected':
                self.status('P2P 媒体已直连', True)
            elif pc.connectionState in ('failed', 'closed'):
                self.status('媒体直连失败，请检查局域网连接后重试', False)
                if pc.connectionState == 'failed':
                    await pc.close()

        async def timeout():
            await asyncio.sleep(15)
            if self.peers.get(peer_id) is item and pc.connectionState != 'connected':
                self.status('媒体直连超时，请检查局域网和防火墙后重试', False)
                await pc.close()
        self.task(timeout())
        return pc

    async def offer(self, peer_id):
        self.viewers.add(peer_id)
        if not self.source:
            return
        old = self.peers.pop(peer_id, None)
        if old:
            await old['pc'].close()
        connection_id = uuid.uuid4().hex
        pc = self._peer(peer_id, connection_id)
        pc.addTrack(SourceVideo(self.source))
        if self.source.has_audio:
            pc.addTrack(SourceAudio(self.source))
        await pc.setLocalDescription(await pc.createOffer())
        if self.peers.get(peer_id, {}).get('pc') is pc:
            self.send({'type': 'p2p_signal', 'target': peer_id, 'kind': 'offer',
                       'stream_id': self.descriptor['stream_id'], 'connection_id': connection_id,
                       'sdp': pc.localDescription.sdp})

    async def set_state(self, state):
        if not state.get('active'):
            await self._close_peers()
            self.descriptor = None
            self.mailbox.reset()
        elif not self.descriptor or self.descriptor['stream_id'] != state['stream_id']:
            await self._close_peers()
            self.descriptor = dict(state)
            self.mailbox.reset(state['stream_id'])
        else:
            self.descriptor = dict(state)

    async def signal(self, message):
        peer_id = message['from_peer']
        if not self.descriptor or message['stream_id'] != self.descriptor['stream_id']:
            return
        if message['kind'] == 'offer':
            old = self.peers.pop(peer_id, None)
            if old:
                await old['pc'].close()
            connection_id = message['connection_id']
            pc = self._peer(peer_id, connection_id)
            generation = (message['stream_id'], connection_id)
            self.mailbox.reset(generation)

            @pc.on('track')
            def track_received(track):
                self.task(self._consume(track, generation))

            await pc.setRemoteDescription(RTCSessionDescription(sdp=message['sdp'], type='offer'))
            await pc.setLocalDescription(await pc.createAnswer())
            self.send({'type': 'p2p_signal', 'target': peer_id, 'kind': 'answer',
                       'stream_id': message['stream_id'], 'connection_id': connection_id,
                       'sdp': pc.localDescription.sdp})
        elif message['kind'] == 'answer':
            item = self.peers.get(peer_id)
            if item and item['connection_id'] == message['connection_id']:
                await item['pc'].setRemoteDescription(RTCSessionDescription(sdp=message['sdp'], type='answer'))

    async def _consume(self, track, generation):
        resampler = av.AudioResampler(format='s16', layout='stereo', rate=48000)
        try:
            while not self.closed:
                frame = await track.recv()
                if track.kind == 'video':
                    self.mailbox.put_video(generation, frame)
                else:
                    for out in resampler.resample(frame):
                        self.mailbox.put_audio(generation, bytes(out.planes[0])[:out.samples * 4])
        except (MediaStreamError, asyncio.CancelledError):
            pass
        finally:
            track.stop()

    async def remove(self, peer_id):
        self.viewers.discard(peer_id)
        item = self.peers.pop(peer_id, None)
        if item:
            await item['pc'].close()

    async def close(self):
        self.closed = True
        await self.stop_source()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
