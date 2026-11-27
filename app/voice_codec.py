"""Small binding to the packaged Opus codec."""
import ctypes as c
from pathlib import Path
import sys

RATE = 48000
SAMPLES = 960
MAX_PACKET = 256


class Opus:
    def __init__(self):
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        dll = root / 'tools/opus/opus.dll'
        if not getattr(sys, 'frozen', False):
            dll = root / 'tools/opus/Library/bin/opus.dll'
        self.lib = c.CDLL(str(dll))
        functions = {
            'opus_encoder_create': (c.c_void_p, [c.c_int, c.c_int, c.c_int, c.POINTER(c.c_int)]),
            'opus_decoder_create': (c.c_void_p, [c.c_int, c.c_int, c.POINTER(c.c_int)]),
            'opus_encoder_destroy': (None, [c.c_void_p]),
            'opus_decoder_destroy': (None, [c.c_void_p]),
            'opus_encoder_ctl': (c.c_int, [c.c_void_p, c.c_int]),
            'opus_encode': (c.c_int, [c.c_void_p, c.c_void_p, c.c_int, c.c_void_p, c.c_int]),
            'opus_decode': (c.c_int, [c.c_void_p, c.c_char_p, c.c_int, c.c_void_p, c.c_int, c.c_int]),
        }
        for name, (result, args) in functions.items():
            fn = getattr(self.lib, name)
            fn.restype, fn.argtypes = result, args
        self.encoder = None
        self.decoders = {}

    def start_capture(self):
        error = c.c_int()
        self.encoder = self.lib.opus_encoder_create(RATE, 1, 2048, c.byref(error))
        if not self.encoder:
            raise OSError('Opus encoder unavailable')
        if self.lib.opus_encoder_ctl(self.encoder, 4002, c.c_int(24000)) != 0:
            self.stop_capture()
            raise OSError('Opus bitrate setup failed')

    def stop_capture(self):
        if self.encoder:
            self.lib.opus_encoder_destroy(self.encoder)
            self.encoder = None

    def encode(self, pcm):
        if len(pcm) != SAMPLES * 2 or not self.encoder:
            raise ValueError('Invalid audio frame')
        samples = (c.c_int16 * SAMPLES).from_buffer_copy(pcm)
        out = c.create_string_buffer(MAX_PACKET)
        count = self.lib.opus_encode(self.encoder, samples, SAMPLES, out, MAX_PACKET)
        return out.raw[:count] if count > 0 else b''

    def decode(self, slot, packet):
        if slot not in self.decoders:
            error = c.c_int()
            decoder = self.lib.opus_decoder_create(RATE, 1, c.byref(error))
            if not decoder:
                return b''
            self.decoders[slot] = decoder
        out = c.create_string_buffer(SAMPLES * 2)
        count = self.lib.opus_decode(self.decoders[slot], packet, len(packet), out, SAMPLES, 0)
        return out.raw if count == SAMPLES else b''

    def reset_peer(self, slot):
        decoder = self.decoders.pop(slot, None)
        if decoder:
            self.lib.opus_decoder_destroy(decoder)

    def close(self):
        self.stop_capture()
        for slot in list(self.decoders):
            self.reset_peer(slot)
