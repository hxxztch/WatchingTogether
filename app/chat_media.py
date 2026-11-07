"""Bounded inline image messages; no remote image URLs or extra server needed."""
import base64
import binascii

MAX_IMAGE_BYTES = 24 * 1024
MAX_GIF_BYTES = 20 * 1024


def _check_gif(raw, width, height):
    """Check all frame rectangles before handing untrusted bytes to Qt."""
    offset = 13 + (3 * (2 ** ((raw[10] & 7) + 1)) if raw[10] & 128 else 0)
    frames = 0

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
            offset = blocks(offset + 1)
        elif marker == 0x2C and offset + 9 <= len(raw):
            left = int.from_bytes(raw[offset:offset + 2], 'little')
            top = int.from_bytes(raw[offset + 2:offset + 4], 'little')
            w = int.from_bytes(raw[offset + 4:offset + 6], 'little')
            h = int.from_bytes(raw[offset + 6:offset + 8], 'little')
            flags = raw[offset + 8]
            frames += 1
            if not w or not h or left + w > width or top + h > height or frames > 80:
                raise ValueError('GIF 帧尺寸或帧数超出限制')
            offset += 9 + (3 * (2 ** ((flags & 7) + 1)) if flags & 128 else 0)
            if offset >= len(raw) or not 2 <= raw[offset] <= 8:
                raise ValueError('GIF 编码无效')
            offset = blocks(offset + 1)
        else:
            break
    raise ValueError('GIF 数据无效')


def image_bytes(value):
    if not isinstance(value, str) or len(value) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise ValueError('图片消息过大')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('无效图片消息')
    if raw.startswith((b'GIF87a', b'GIF89a')):
        if len(raw) > MAX_GIF_BYTES or len(raw) < 14 or raw[-1:] != b';':
            raise ValueError('GIF 数据无效或超过 20 KB')
        width, height = int.from_bytes(raw[6:8], 'little'), int.from_bytes(raw[8:10], 'little')
        if not 0 < width <= 160 or not 0 < height <= 160:
            raise ValueError('GIF 尺寸过大')
        _check_gif(raw, width, height)
        return raw
    if not raw or len(raw) > MAX_IMAGE_BYTES or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('图片格式无效')
    # PNG IHDR: reject oversized dimensions before any decoder allocates pixels.
    if len(raw) < 33 or raw[12:16] != b'IHDR':
        raise ValueError('图片头无效')
    width, height = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
    if not 0 < width <= 320 or not 0 < height <= 320:
        raise ValueError('图片尺寸过大')
    return raw
