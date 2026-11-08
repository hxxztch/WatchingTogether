"""Bounded GIF encoding and Qt playback; originals are never sent to peers."""
import base64
from io import BytesIO

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize
from PySide6.QtGui import QMovie

from app.chat_media import (MAX_GIF_BYTES, MAX_GIF_EDGE, MAX_GIF_FRAMES, MAX_GIF_DURATION_MS,
                            MAX_GIF_SOURCE_PIXELS, MAX_GIF_PIXELS, _check_gif, image_bytes)


def prepare_gif(raw):
    from PIL import Image
    if len(raw) < 14:
        raise ValueError('GIF 数据无效。')
    width, height = int.from_bytes(raw[6:8], 'little'), int.from_bytes(raw[8:10], 'little')
    if not width or not height or width * height > 16000000:
        raise ValueError('GIF 尺寸过大。')
    _check_gif(raw, width, height, max_pixels=MAX_GIF_SOURCE_PIXELS)
    frames, durations = [], []
    preserve = True
    with Image.open(BytesIO(raw)) as source:
        if source.n_frames > MAX_GIF_FRAMES:
            raise ValueError('GIF 最多支持 240 帧，请选择较短的动画。')
        if source.width * source.height * source.n_frames > MAX_GIF_SOURCE_PIXELS:
            raise ValueError('GIF 解码量过大，请先缩小原图尺寸或减少帧数。')
        for index in range(source.n_frames):
            source.seek(index)
            if source.width * source.height > 16000000:
                raise ValueError('GIF 尺寸过大。')
            frame = source.convert('RGBA')
            frame.thumbnail((MAX_GIF_EDGE, MAX_GIF_EDGE), Image.Resampling.LANCZOS)
            frames.append(frame)
            delay = source.info.get('duration', 100)
            preserve = preserve and delay >= 40
            durations.append(max(40, delay))
    if sum(durations) > MAX_GIF_DURATION_MS:
        raise ValueError('GIF 最多支持 30 秒，请选择较短的动画。')
    if preserve and len(raw) <= MAX_GIF_BYTES:
        try:
            value = base64.b64encode(raw).decode('ascii')
            image_bytes(value)
            return value
        except ValueError:
            pass
    maximum_edge = min(MAX_GIF_EDGE, int((MAX_GIF_PIXELS // len(frames)) ** .5))
    for edge, colors in ((320, 128), (256, 96), (192, 64), (128, 48), (96, 32), (64, 24)):
        edge = min(edge, maximum_edge)
        encoded = []
        for frame in frames:
            small = frame.copy()
            small.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            # Reserve a palette entry for alpha; preserve GIF disposal compositing.
            palette = small.convert('RGB').quantize(colors=colors - 1, method=Image.Quantize.FASTOCTREE)
            palette.paste(colors - 1, mask=small.getchannel('A').point(lambda a: 255 if a < 128 else 0))
            palette.info['transparency'] = colors - 1
            encoded.append(palette)
        output = BytesIO()
        encoded[0].save(output, format='GIF', save_all=True, append_images=encoded[1:],
                        duration=durations, loop=0, disposal=2, optimize=True)
        data = output.getvalue()
        if len(data) <= MAX_GIF_BYTES:
            value = base64.b64encode(data).decode('ascii')
            image_bytes(value)
            return value
    raise ValueError('GIF 压缩后仍超过 1 MB，请选择更简单或更短的动画。')


def set_label_image(label, value, edge=160):
    from app.ui.chat_images import image_pixmap
    raw = image_bytes(value)
    pixmap = image_pixmap(value, edge)
    label.setFixedSize(pixmap.size())
    if raw.startswith((b'GIF87a', b'GIF89a')):
        buffer = QBuffer(label)
        buffer.setData(QByteArray(raw))
        buffer.open(QIODevice.ReadOnly)
        movie = QMovie(buffer, QByteArray(b'gif'), label)
        movie.setScaledSize(QSize(pixmap.width(), pixmap.height()))
        movie.setCacheMode(QMovie.CacheNone)
        label.setMovie(movie)
        movie.start()
    else:
        label.setPixmap(pixmap)
