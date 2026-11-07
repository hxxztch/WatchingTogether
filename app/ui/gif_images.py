"""Bounded GIF encoding and Qt playback; originals are never sent to peers."""
import base64
from io import BytesIO

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize
from PySide6.QtGui import QMovie

from app.chat_media import MAX_GIF_BYTES, image_bytes


def prepare_gif(raw):
    from PIL import Image
    frames, durations = [], []
    with Image.open(BytesIO(raw)) as source:
        if source.n_frames > 80:
            raise ValueError('GIF 最多支持 80 帧，请选择较短的动画。')
        if source.width * source.height * source.n_frames > 64000000:
            raise ValueError('GIF 解码量过大，请先缩小原图尺寸或减少帧数。')
        for index in range(source.n_frames):
            source.seek(index)
            if source.width * source.height > 16000000:
                raise ValueError('GIF 尺寸过大。')
            frame = source.convert('RGBA')
            frame.thumbnail((160, 160), Image.Resampling.LANCZOS)
            frames.append(frame)
            durations.append(max(40, min(2000, source.info.get('duration', 100))))
    if sum(durations) > 15000:
        raise ValueError('GIF 最多支持 15 秒，请选择较短的动画。')
    for edge, colors in ((160, 64), (128, 48), (96, 32), (64, 24), (48, 16)):
        encoded = []
        for frame in frames:
            small = frame.copy()
            small.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            # Reserve a palette entry for alpha; preserve GIF disposal compositing.
            palette = small.convert('RGB').quantize(colors=colors - 1)
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
    raise ValueError('GIF 压缩后仍超过 20 KB，请选择更简单或更短的动画。')


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
