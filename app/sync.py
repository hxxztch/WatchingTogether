"""Playback correction policy, independent of Qt and mpv."""
import math
import time


class PlaybackSynchronizer:
    def __init__(self):
        self.version = -1

    def plan(self, state, position, duration, force=False, now=None):
        if not duration or duration <= 0:
            return None  # Wait for the viewer's media to finish loading.
        now = time.monotonic() if now is None else now
        version = int(state.get("version", self.version + 1))
        if version < self.version:
            return None
        target = float(state.get("position", 0))
        playing = bool(state.get("playing", False))
        if playing:
            target += max(0, now - float(state.get("local_time", now)))
        if not math.isfinite(target):
            return None
        target = min(float(duration), max(0.0, target))
        playing = playing and target < duration
        error = target - float(position or 0)
        changed = force or version != self.version
        self.version = version
        seek = None
        speed = 1.0
        if abs(error) > 1.5 or ((changed or not playing) and abs(error) > 0.15):
            seek = target
        elif playing and abs(error) > 0.15:
            speed = 1.02 if error > 0 else 0.98
        return {"seek": seek, "speed": speed, "playing": playing}
