"""Generate deterministic audio/video input without downloading external media."""
from array import array
from fractions import Fraction
import math
from pathlib import Path
import av
from PIL import Image, ImageDraw


def make_video(path, seconds=12):
    with av.open(str(path), 'w', format='matroska') as output:
        video = output.add_stream('ffv1', rate=20)
        video.width, video.height, video.pix_fmt = 320, 180, 'bgr0'
        audio = output.add_stream('pcm_s16le', rate=48000)
        audio.layout = 'stereo'
        sample = 0
        for index in range(seconds * 20):
            image = Image.new('RGB', (320, 180), (30 + index % 150, 70, 130))
            ImageDraw.Draw(image).text((20, 80), 'P2P LOCAL SOURCE %d' % index, fill='white')
            frame = av.VideoFrame.from_image(image)
            frame.pts, frame.time_base = index, Fraction(1, 20)
            for packet in video.encode(frame):
                output.mux(packet)
            for _ in range(2 + index % 2):
                pcm = array('h')
                for i in range(960):
                    value = int(2500 * math.sin(2 * math.pi * 440 * (sample + i) / 48000))
                    pcm.extend((value, value))
                frame = av.AudioFrame(format='s16', layout='stereo', samples=960)
                frame.planes[0].update(pcm.tobytes())
                frame.sample_rate, frame.pts, frame.time_base = 48000, sample, Fraction(1, 48000)
                sample += 960
                for packet in audio.encode(frame):
                    output.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode():
                output.mux(packet)
