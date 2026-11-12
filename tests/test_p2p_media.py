"""Actual loopback WebRTC video/audio, pause, late join and teardown."""
import asyncio
import tempfile
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.p2p import available


@unittest.skipUnless(available(), 'Install requirements-p2p.txt with Python 3.11+')
class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_viewers_receive_media_and_pause_seek_stop(self):
        asyncio.get_running_loop().set_debug(False)
        from app.p2p.engine import P2PEngine
        from app.p2p.mailbox import MediaMailbox
        from p2p_fixture import make_video
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.mkv'
            await asyncio.to_thread(make_video, path)
            queue = asyncio.Queue()
            failures = []
            engines = {}
            def status(text, connected):
                if '失败' in text or '超时' in text:
                    failures.append(text)
            for name in ('host', 'a', 'b'):
                engines[name] = P2PEngine(lambda msg, sender=name: queue.put_nowait((sender, msg)), status, MediaMailbox())
            host = engines['host']
            async def route():
                while True:
                    sender, msg = await queue.get()
                    if msg['type'] == 'p2p_state':
                        for name in ('a', 'b'):
                            await engines[name].set_state(msg)
                    elif msg['type'] == 'p2p_signal':
                        await engines[msg['target']].signal({**msg, 'from_peer': sender})
            routing = asyncio.create_task(route())
            async def wait(check, timeout=12):
                deadline = time.monotonic() + timeout
                while not check():
                    if routing.done():
                        routing.result()

                    self.assertLess(time.monotonic(), deadline, 'WebRTC media timed out')
                    await asyncio.sleep(.025)
            try:
                host.viewers.add('a')
                await host.load(str(path))
                await wait(lambda: engines['a'].mailbox.video is not None and any(engines['a'].mailbox.audio))
                await host.offer('b')  # Late join starts at the current source position.
                await wait(lambda: engines['b'].mailbox.video is not None and any(engines['b'].mailbox.audio))
                self.assertTrue(all(p['pc'].connectionState == 'connected' for p in host.peers.values()))
                before = host.source.position
                await host.pause(True)
                await asyncio.sleep(.25)
                self.assertAlmostEqual(host.source.position, before, delta=.04)
                await host.pause(False)
                await asyncio.sleep(.2)
                self.assertGreater(host.source.position, before + .1)
                previous = host.descriptor['stream_id']
                await host.load(str(path), position=3, playing=False)
                self.assertNotEqual(previous, host.descriptor['stream_id'])
                await wait(lambda: engines['a'].mailbox.video is not None and engines['b'].mailbox.video is not None)
                self.assertAlmostEqual(host.source.position, 3, delta=.05)
                await host.stop_source()
                await wait(lambda: all(not engines[n].peers for n in ('a', 'b')))
                self.assertFalse(host.peers)
            finally:
                routing.cancel()
                await asyncio.gather(routing, return_exceptions=True)
                for engine in engines.values():
                    await asyncio.wait_for(engine.close(),5)
                    self.assertFalse(engine.tasks)

    def test_mailbox_drops_stale_generation_and_bounds_audio(self):
        from app.p2p.mailbox import MediaMailbox
        box = MediaMailbox()
        box.reset('new')
        box.put_audio('old', b'1234')
        self.assertFalse(box.audio)
        box.put_audio('new', b'1' * 100000)
        self.assertEqual(len(box.audio), box.MAX_AUDIO_BYTES)
