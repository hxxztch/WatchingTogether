import unittest

from app.voice_buffer import VoiceBuffer


class VoiceBufferTests(unittest.TestCase):
    def test_short_utterance_starts_without_filling_buffer(self):
        buffer = VoiceBuffer()
        buffer.put(0, b'first')
        self.assertIsNone(buffer.take(.02))
        self.assertEqual(buffer.take(.05), b'first')

    def test_buffer_grows_after_short_gap_and_resets_after_silence(self):
        buffer = VoiceBuffer()
        buffer.put(0, b'first')
        self.assertEqual(buffer.take(.05), b'first')
        self.assertIsNone(buffer.take(.07))
        buffer.put(.10, b'next')
        self.assertEqual(buffer.depth, 4)
        self.assertEqual(buffer.underruns, 1)
        self.assertEqual(buffer.take(.17), b'next')
        self.assertIsNone(buffer.take(.19))
        buffer.put(.50, b'new utterance')
        self.assertEqual(buffer.depth, 3)

    def test_burst_keeps_newest_frames_and_expired_frames_are_dropped(self):
        buffer = VoiceBuffer()
        for index in range(12):
            buffer.put(.01, bytes([index]))
        self.assertEqual(buffer.dropped, 7)
        self.assertEqual(buffer.take(.02), b'\x07')
        self.assertIsNone(buffer.take(.21))
        self.assertEqual(buffer.dropped, 11)
