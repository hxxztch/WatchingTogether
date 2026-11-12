"""Bounded cross-thread media mailbox; never queues Qt signals for every frame."""
import threading
from collections import deque


class MediaMailbox:
    MAX_AUDIO_BYTES = 48000  # 250 ms of 48 kHz stereo signed 16-bit PCM.

    def __init__(self):
        self.lock = threading.Lock()
        self.video = None
        self.audio = bytearray()
        self.generation = None

    def reset(self, generation=None):
        with self.lock:
            self.generation = generation
            self.video = None
            self.audio.clear()

    def put_video(self, generation, frame):
        image = frame.to_image()
        data = (image.tobytes(), image.width, image.height)
        with self.lock:
            if generation == self.generation:
                self.video = data

    def put_audio(self, generation, data):
        with self.lock:
            if generation == self.generation:
                self.audio.extend(data)
                if len(self.audio) > self.MAX_AUDIO_BYTES:
                    del self.audio[:-self.MAX_AUDIO_BYTES]

    def take(self):
        with self.lock:
            result = self.video, bytes(self.audio)
            self.video = None
            self.audio.clear()
            return result
