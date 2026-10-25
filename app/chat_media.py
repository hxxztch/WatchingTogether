"""Bounded inline image messages; no remote image URLs or extra server needed."""
import base64
import binascii

MAX_IMAGE_BYTES = 24 * 1024


def image_bytes(value):
    if not isinstance(value, str) or len(value) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise ValueError('图片消息过大')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('无效图片消息')
    if not raw or len(raw) > MAX_IMAGE_BYTES or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('图片格式无效')
    # PNG IHDR: reject oversized dimensions before any decoder allocates pixels.
    if len(raw) < 33 or raw[12:16] != b'IHDR':
        raise ValueError('图片头无效')
    width, height = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
    if not 0 < width <= 320 or not 0 < height <= 320:
        raise ValueError('图片尺寸过大')
    return raw
