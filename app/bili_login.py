"""Cancelable Bilibili QR login; all HTTP work runs outside the Qt thread."""
import http.cookiejar
import io
import json
import threading
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor

from PySide6.QtCore import QObject, Signal
from app.bilibili import DEFAULT_HEADERS, BilibiliError


class LoginAPI:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def _request(self, url):
        with self.opener.open(Request(url, headers=DEFAULT_HEADERS), timeout=6) as response:
            result = json.loads(response.read().decode('utf-8'))
        if result.get('code') != 0:
            raise BilibiliError('B站接口暂不可用，请重试')
        return result.get('data') or {}

    def generate(self):
        return self._request('https://passport.bilibili.com/x/passport-login/web/qrcode/generate')

    def poll(self, key):
        return self._request('https://passport.bilibili.com/x/passport-login/web/qrcode/poll?' +
                             urlencode({'qrcode_key': key}))

    def _session_cookie(self):
        return next((c.value for c in self.cookies if c.name == 'SESSDATA' and
                     (c.domain.lstrip('.') == 'bilibili.com' or c.domain.endswith('.bilibili.com'))), '')

    def complete(self, data, cancelled):
        # poll already sets login cookies on normal web responses. Reuse them
        # instead of always visiting the slower cross-domain gaming login page.
        if not self._session_cookie():
            url = data.get('url', '')
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in (
                    'passport.bilibili.com', 'passport.biligame.com'):
                raise BilibiliError('未获取到登录凭据，请重新扫码')
            if cancelled.is_set():
                return None
            with self.opener.open(Request(url, headers=DEFAULT_HEADERS), timeout=6) as response:
                response.read(1024)
        if cancelled.is_set():
            return None
        session = self._session_cookie()
        if not session:
            raise BilibiliError('未获取到登录凭据，请重新扫码')
        profile = self._request('https://api.bilibili.com/x/web-interface/nav')
        if not profile.get('isLogin'):
            raise BilibiliError('登录状态验证失败，请重新扫码')
        return {'bili_cookie': 'SESSDATA=' + session,
                'bili_uid': str(profile['mid']), 'bili_uname': profile['uname']}


class LoginSession(QObject):
    qr_ready = Signal(bytes)
    status_changed = Signal(str)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, api=None, interval=1.0, confirm_interval=0.5, retry_delay=1.0):
        super().__init__()
        self.api = api or LoginAPI()
        self.cancelled = threading.Event()
        self.interval = interval
        self.confirm_interval = confirm_interval
        self.retry_delay = retry_delay
        self.thread = None

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name='BiliQRLogin')
            self.thread.start()

    def cancel(self):
        self.cancelled.set()

    def _emit(self, signal, value):
        if not self.cancelled.is_set():
            try:
                signal.emit(value)
            except RuntimeError:
                self.cancel()

    @staticmethod
    def _qr_png(url):
        import segno
        buffer = io.BytesIO()
        segno.make(url, error='m').save(buffer, kind='png', scale=8, border=2)
        return buffer.getvalue()

    def _run(self):
        key = None
        confirmed = None
        failures = 0
        started = time.monotonic()
        while not self.cancelled.is_set():
            if time.monotonic() - started > 180:
                self._emit(self.failed, '登录超时，请点击重新生成')
                return
            try:
                if confirmed is not None:
                    self._emit(self.status_changed, '已确认，正在验证账号信息…')
                    result = self.api.complete(confirmed, self.cancelled)
                    if result is not None:
                        self._emit(self.succeeded, result)
                    return
                if key is None:
                    self._emit(self.status_changed, '正在生成二维码…')
                    generated = self.api.generate()
                    png = self._qr_png(generated['url'])
                    key = generated['qrcode_key']
                    self._emit(self.qr_ready, png)
                    self._emit(self.status_changed, '等待扫码…')
                    failures = 0
                if self.cancelled.is_set():
                    return
                data = self.api.poll(key)
                code = data.get('code')
                if code == 0:
                    confirmed = data
                    failures = 0
                    continue  # Verify immediately; don't wait for the next timer tick.
                if code == 86038:
                    key = None
                    self._emit(self.status_changed, '二维码已过期，正在重新生成…')
                elif code == 86090:
                    self._emit(self.status_changed, '已扫码，请在APP中确认')
                elif code != 86101:
                    raise BilibiliError('扫码状态异常，请稍后重试')
                failures = 0
                if self.cancelled.wait(self.confirm_interval if code == 86090 else self.interval):
                    return
            except Exception as exc:
                failures += 1
                # No exception payloads: they may include QR keys or login tickets.
                if failures >= 3:
                    self._emit(self.failed, str(exc) if isinstance(exc, BilibiliError)
                               else '网络请求失败，请检查连接后重新生成')
                    return
                self._emit(self.status_changed, f'请求未完成，正在重试（{failures}/3）…')
                if self.cancelled.wait(self.retry_delay):
                    return
