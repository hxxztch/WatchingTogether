"""Bounded inline image messages; no remote image URLs or extra server needed."""
import base64
import binascii
import json

MAX_ORIGINAL_BYTES = 10 * 1024 * 1024
MAX_IMAGE_BYTES = 512 * 1024
MAX_GIF_BYTES = 1024 * 1024
MAX_IMAGE_EDGE = 1024
MAX_GIF_EDGE = 320
MAX_GIF_FRAMES = 240
MAX_GIF_DURATION_MS = 30000
MAX_GIF_PIXELS = 16000000
MAX_GIF_SOURCE_PIXELS = 128000000
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_HISTORY_BYTES = 8 * 1024 * 1024
MAX_OUTBOX_BYTES = 16 * 1024 * 1024
LEGACY_IMAGE_BYTES = 24 * 1024
LEGACY_GIF_BYTES = 20 * 1024


def wire_size(message):
    return len(json.dumps(message, ensure_ascii=False).encode('utf-8'))


def _check_gif(raw, width, height, max_frames=MAX_GIF_FRAMES,
               max_pixels=MAX_GIF_PIXELS, max_duration=MAX_GIF_DURATION_MS):
    """Check all frame rectangles before handing untrusted bytes to Qt."""
    offset = 13 + (3 * (2 ** ((raw[10] & 7) + 1)) if raw[10] & 128 else 0)
    frames = 0
    duration = 0
    delay = 100

    def blocks(pos):
        while pos < len(raw):
            count = raw[pos]
            pos += 1
            if not count:
                return pos
            pos += count
        raise ValueError('GIF 数据不完整')

    while offset < len(raw):
        marker = raw[offset]
        offset += 1
        if marker == 0x3B and offset == len(raw) and frames:
            return
        if marker == 0x21:
            if offset >= len(raw):
                raise ValueError('GIF 数据不完整')
            if raw[offset] == 0xF9:
                if offset + 7 > len(raw) or raw[offset + 1] != 4:
                    raise ValueError('GIF 控制数据无效')
                delay = max(40, int.from_bytes(raw[offset + 3:offset + 5], 'little') * 10)
            offset = blocks(offset + 1)
        elif marker == 0x2C and offset + 9 <= len(raw):
            left = int.from_bytes(raw[offset:offset + 2], 'little')
            top = int.from_bytes(raw[offset + 2:offset + 4], 'little')
            w = int.from_bytes(raw[offset + 4:offset + 6], 'little')
            h = int.from_bytes(raw[offset + 6:offset + 8], 'little')
            flags = raw[offset + 8]
            frames += 1
            duration += delay
            delay = 100
            if (not w or not h or left + w > width or top + h > height or frames > max_frames
                    or width * height * frames > max_pixels or duration > max_duration):
                raise ValueError('GIF 尺寸、帧数、时长或解码量超出限制')
            offset += 9 + (3 * (2 ** ((flags & 7) + 1)) if flags & 128 else 0)
            if offset >= len(raw) or not 2 <= raw[offset] <= 8:
                raise ValueError('GIF 编码无效')
            offset = blocks(offset + 1)
        else:
            break
    raise ValueError('GIF 数据无效')


def image_bytes(value, legacy=False):
    maximum = LEGACY_IMAGE_BYTES if legacy else max(MAX_IMAGE_BYTES, MAX_GIF_BYTES)
    if not isinstance(value, str) or len(value) > (maximum + 2) // 3 * 4:
        raise ValueError('图片消息过大')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('无效图片消息')
    if raw.startswith((b'GIF87a', b'GIF89a')):
        if len(raw) > (LEGACY_GIF_BYTES if legacy else MAX_GIF_BYTES) or len(raw) < 14 or raw[-1:] != b';':
            raise ValueError('GIF 数据无效或超过发送大小限制')
        width, height = int.from_bytes(raw[6:8], 'little'), int.from_bytes(raw[8:10], 'little')
        edge = 160 if legacy else MAX_GIF_EDGE
        if not 0 < width <= edge or not 0 < height <= edge:
            raise ValueError('GIF 尺寸过大')
        _check_gif(raw, width, height, max_frames=80 if legacy else MAX_GIF_FRAMES,
                   max_duration=15000 if legacy else MAX_GIF_DURATION_MS)
        return raw
    if not raw or len(raw) > (LEGACY_IMAGE_BYTES if legacy else MAX_IMAGE_BYTES) or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('图片格式无效')
    # PNG IHDR: reject oversized dimensions before any decoder allocates pixels.
    if len(raw) < 33 or raw[12:16] != b'IHDR':
        raise ValueError('图片头无效')
    width, height = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
    edge = 320 if legacy else MAX_IMAGE_EDGE
    if not 0 < width <= edge or not 0 < height <= edge:
        raise ValueError('图片尺寸过大')
    return raw
