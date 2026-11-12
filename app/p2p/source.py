"""Local-file WebRTC sources with a shared, bounded playback clock."""
import math
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

import av
from aiortc import AudioStreamTrack, VideoStreamTrack


class FileSource:
    def __init__(self, path, position=0, playing=True):
        if not Path(path).is_file():
            raise ValueError('请选择存在的本地视频文件')
        self.path = str(path)
        self.duration = 0.0
        if not math.isfinite(float(position)):
            raise ValueError('Invalid source position')
        self.position_base = max(0.0, float(position))
        self.started = time.monotonic()
        self.playing = playing
        self.error = None
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.lock = threading.RLock()
        self.video = deque(maxlen=20)
        self.audio = deque(maxlen=100)
        self.has_audio = False
        self.has_video = False
        self.ended = False
        self.thread = threading.Thread(target=self._decode, name='p2p-source', daemon=True)
        self.thread.start()
        if not self.ready.wait(12):
            self.close()
            raise RuntimeError('读取片源超时')
        if self.error:
            self.close()
            raise RuntimeError(self.error)
        self.started = time.monotonic()

    @property
    def position(self):
        with self.lock:
            value = self.position_base + (time.monotonic() - self.started if self.playing else 0)
            return min(value, self.duration) if self.duration else value

    def pause(self, paused):
        with self.lock:
            self.position_base = self.position
            self.started = time.monotonic()
            self.playing = not paused

    def _decode(self):
        try:
            with av.open(self.path, timeout=(5, 10)) as container:
                self.duration = float(container.duration or 0) / av.time_base
                if self.duration:
                    self.position_base = min(self.position_base, max(0, self.duration - .05))
                streams = [s for s in container.streams if s.type in ('video', 'audio')]
                video = next((s for s in streams if s.type == 'video'), None)
                audio = next((s for s in streams if s.type == 'audio'), None)
                self.has_video, self.has_audio = video is not None, audio is not None
                if not self.has_video:
                    raise ValueError('片源中没有视频轨道')
                origin = float(container.start_time or 0) / av.time_base
                if self.position_base:
                    container.seek(int((self.position_base + origin) * av.time_base))
                resampler = av.AudioResampler(format='s16', layout='stereo', rate=48000, frame_size=960)
                chosen = [s for s in (video, audio) if s is not None]
                for frame in container.decode(*chosen):
                    if self.closed.is_set():
                        break
                    stamp = float(frame.time or 0) - origin
                    if stamp + .04 < self.position_base:
                        continue
                    # Bound decode-ahead and avoid reading an entire movie while paused.
                    while stamp > self.position + .35 and not self.closed.wait(.01):
                        pass
                    if self.closed.is_set():
                        break
                    if isinstance(frame, av.VideoFrame):
                        width = min(1280, frame.width)
                        height = max(2, round(frame.height * width / frame.width / 2) * 2)
                        image = frame.reformat(width=width, height=height, format='rgb24').to_image()
                        with self.lock:
                            self.video.append((stamp, image))
                        self.ready.set()
                    else:
                        for out in resampler.resample(frame):
                            out_stamp = float(out.time) - origin if out.time is not None else stamp
                            raw = bytes(out.planes[0])[:out.samples * 4]
                            with self.lock:
                                self.audio.append((out_stamp, raw))
                self.ended = True
                self.ready.set()
        except Exception as exc:
            # Do not include paths or FFmpeg input details in UI/log messages.
            self.error = '片源解码失败：' + type(exc).__name__
            self.ready.set()

    def image(self):
        with self.lock:
            available = [item for item in self.video if item[0] <= self.position + .02]
            return available[-1][1] if available else None

    def pcm(self):
        with self.lock:
            if not self.playing:
                return bytes(3840)
            pos = self.position
            candidates = [item for item in self.audio if abs(item[0] - pos) <= .035]
            raw = min(candidates, key=lambda item: abs(item[0] - pos))[1] if candidates else b''
            return (raw + bytes(3840))[:3840]

    def close(self):
        self.closed.set()
        if self.thread is not threading.current_thread():
            self.thread.join(2)


class SourceVideo(VideoStreamTrack):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.started = time.monotonic()
        self.counter = 0

    async def recv(self):
        import asyncio
        from aiortc.mediastreams import MediaStreamError
        if self.readyState != 'live' or self.source.closed.is_set():
            raise MediaStreamError
        await asyncio.sleep(max(0, self.started + self.counter / 30 - time.monotonic()))
        image = self.source.image()
        while image is None:
            if self.source.closed.is_set() or self.source.error:
                raise MediaStreamError
            await asyncio.sleep(.01)
            image = self.source.image()
        frame = av.VideoFrame.from_image(image)
        frame.pts, frame.time_base = self.counter * 3000, Fraction(1, 90000)
        self.counter += 1
        return frame


class SourceAudio(AudioStreamTrack):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.started = time.monotonic()
        self.counter = 0

    async def recv(self):
        import asyncio
        from aiortc.mediastreams import MediaStreamError
        if self.readyState != 'live' or self.source.closed.is_set():
            raise MediaStreamError
        await asyncio.sleep(max(0, self.started + self.counter * .02 - time.monotonic()))
        frame = av.AudioFrame(format='s16', layout='stereo', samples=960)
        frame.planes[0].update(self.source.pcm())
        frame.sample_rate = 48000
        frame.pts, frame.time_base = self.counter * 960, Fraction(1, 48000)
        self.counter += 1
        return frame
