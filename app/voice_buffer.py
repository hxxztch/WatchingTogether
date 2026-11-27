"""Bounded buffering for 20 ms Opus packets arriving over TCP."""
from collections import deque


class VoiceBuffer:
    def __init__(self):
        self.queue = deque()
        self.depth = 3
        self.playing = False
        self.starved_at = None
        self.dropped = 0
        self.underruns = 0

    def put(self, now, packet):
        if self.starved_at is not None:
            gap = now - self.starved_at
            if gap < .12:
                self.depth = min(6, self.depth + 1)
                self.underruns += 1
            elif gap >= .25:
                self.depth = 3
            self.starved_at = None
        if len(self.queue) >= self.depth + 2:
            self.queue.popleft()
            self.dropped += 1
        self.queue.append((now, packet))

    def take(self, now):
        while self.queue and now - self.queue[0][0] > .18:
            self.queue.popleft()
            self.dropped += 1
        if not self.queue:
            if self.playing:
                self.starved_at = now
                self.playing = False
            return None
        if not self.playing:
            # A short utterance still plays if it never fills the buffer.
            if len(self.queue) < self.depth and now - self.queue[0][0] < .02 * (self.depth - 1):
                return None
            self.playing = True
        return self.queue.popleft()[1]
