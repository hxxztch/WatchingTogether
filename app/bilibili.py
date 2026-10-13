"""Bilibili web playback requests and selection of actual DASH representations."""
import hashlib
import json
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


WBI_ORDER = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
QUALITY_NAMES = {16: "360P", 32: "480P", 64: "720P", 74: "720P 60帧",
                 80: "1080P", 112: "1080P 高码率", 116: "1080P 60帧",
                 120: "4K", 125: "HDR", 126: "杜比视界", 127: "8K"}
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}


class BilibiliError(Exception):
    pass


class QualityUnavailable(BilibiliError):
    def __init__(self, requested, available):
        self.available = available
        label = QUALITY_NAMES.get(requested, str(requested))
        super().__init__(f"当前账号或视频未返回{label}视频流；可用：{'、'.join(available.values())}")


def mixin_key(image_url, sub_url):
    lookup = "".join(urlparse(url).path.rsplit("/", 1)[-1].split(".")[0]
                     for url in (image_url, sub_url))
    if len(lookup) < 64:
        raise BilibiliError("B站签名信息不完整")
    return "".join(lookup[index] for index in WBI_ORDER)[:32]


def sign_params(params, key, timestamp=None):
    values = dict(params)
    values["wts"] = int(time.time() if timestamp is None else timestamp)
    cleaned = {name: "".join(char for char in str(value) if char not in "!'()*")
               for name, value in sorted(values.items())}
    query = urlencode(cleaned)
    cleaned["w_rid"] = hashlib.md5((query + key).encode("utf-8")).hexdigest()
    return cleaned


def stream_url(stream):
    for field in ("baseUrl", "base_url", "url"):
        value = stream.get(field)
        if isinstance(value, str) and urlparse(value).scheme in ("http", "https"):
            return value
    for field in ("backupUrl", "backup_url"):
        for value in stream.get(field) or []:
            if isinstance(value, str) and urlparse(value).scheme in ("http", "https"):
                return value
    return ""


def _number(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return default


def _descriptions(data):
    names = dict(QUALITY_NAMES)
    for qn, description in zip(data.get("accept_quality") or [], data.get("accept_description") or []):
        if description:
            names[_number(qn)] = str(description)
    for item in data.get("support_formats") or []:
        description = item.get("new_description") or item.get("display_desc")
        if description:
            names[_number(item.get("quality"))] = str(description)
    return names


def select_streams(data, requested, strict=False):
    """Return URL pair, selected representation ID, and genuinely playable qualities.

    The top-level 'quality' and list order do not identify the selected DASH stream.
    Advertised VIP qualities without a returned URL aren't selectable.
    """
    requested = int(requested)
    names = _descriptions(data)
    dash = data.get("dash") or {}
    videos = [item for item in dash.get("video") or []
              if _number(item.get("id")) > 0 and stream_url(item)]
    if videos:
        available = sorted({_number(item["id"]) for item in videos}, reverse=True)
        quality_map = {str(qn): names.get(qn, f"画质 {qn}") for qn in available}
        if strict and requested not in available:
            raise QualityUnavailable(requested, quality_map)
        selected = requested if requested in available else next(
            (qn for qn in available if qn <= requested), min(available))
        matching = [item for item in videos if _number(item["id"]) == selected]
        # Prefer AVC for compatibility, then bitrate within that codec preference.
        video = max(matching, key=lambda item: (
            _number(item.get("codecid")) == 7 or str(item.get("codecs", "")).startswith("avc"),
            _number(item.get("bandwidth"))))
        audios = [item for item in dash.get("audio") or [] if stream_url(item)]
        audio = max(audios, key=lambda item: (
            str(item.get("codecs", "")).startswith("mp4a"), _number(item.get("bandwidth"))),
            default={})
        return stream_url(video), stream_url(audio), selected, quality_map

    progressive = data.get("durl") or []
    if len(progressive) > 1:
        raise BilibiliError("接口返回分段视频，当前无法完整切换；请重试DASH视频流")
    if len(progressive) == 1 and stream_url(progressive[0]):
        selected = _number(data.get("quality"))
        if selected <= 0:
            raise BilibiliError("接口未提供视频清晰度信息")
        quality_map = {str(selected): names.get(selected, f"画质 {selected}")}
        if strict and selected != requested:
            raise QualityUnavailable(requested, quality_map)
        return stream_url(progressive[0]), "", selected, quality_map
    raise BilibiliError("B站未返回可播放的视频流")


class BilibiliClient:
    def __init__(self):
        self._key = None
        self._key_expires = 0

    @staticmethod
    def _request(url, headers):
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_key(self, headers):
        if self._key is not None and time.monotonic() < self._key_expires:
            return self._key
        data = self._request("https://api.bilibili.com/x/web-interface/nav", headers)
        images = data.get("data", {}).get("wbi_img", {})
        self._key = mixin_key(images.get("img_url", ""), images.get("sub_url", ""))
        self._key_expires = time.monotonic() + 30
        return self._key

    def fetch_streams(self, avid, cid, qn, headers=None, cookie="", strict=False):
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        if cookie:
            req_headers["Cookie"] = cookie
        params = {"avid": str(avid), "cid": str(cid), "qn": str(qn),
                  "fnver": "0", "fnval": "4048", "fourk": "1", "platform": "web"}
        errors = []
        for signed in (True, False):
            try:
                if signed:
                    query = sign_params(params, self._get_key(req_headers))
                    endpoint = "https://api.bilibili.com/x/player/wbi/playurl"
                else:
                    query = params
                    endpoint = "https://api.bilibili.com/x/player/playurl"
                result = self._request(endpoint + "?" + urlencode(query), req_headers)
                if result.get("code") != 0:
                    self._key = None
                    raise BilibiliError(f"B站播放接口返回错误 {result.get('code', 'unknown')}")
                return select_streams(result.get("data") or {}, qn, strict=strict)
            except QualityUnavailable:
                raise  # Don't turn account restrictions into a fake successful switch.
            except BilibiliError as exc:
                errors.append(str(exc))
            except Exception as exc:
                # Exception strings may contain signed stream URLs; don't expose them.
                errors.append("B站接口请求失败（" + type(exc).__name__ + "）")
        raise BilibiliError(errors[-1] if errors else "B站视频解析失败")
