import http.cookiejar
import threading
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import Qt
from app.bili_login import LoginAPI, LoginSession


def install_cookie(api):
    api.cookies.set_cookie(http.cookiejar.Cookie(
        0, 'SESSDATA', 'synthetic-test-value', None, False, '.bilibili.com', True, True,
        '/', True, True, None, True, None, None, {}))


class LoginAPITests(unittest.TestCase):
    def test_poll_cookie_skips_cross_domain_and_verifies_once(self):
        api = LoginAPI()
        install_cookie(api)
        with patch.object(api, '_request', return_value={'isLogin': True, 'mid': 1, 'uname': 'test'}) as request, \
                patch.object(api.opener, 'open') as cross:
            result = api.complete({'url': 'https://passport.biligame.com/crossDomain'}, threading.Event())
            self.assertEqual(result['bili_cookie'], 'SESSDATA=synthetic-test-value')
            request.assert_called_once_with('https://api.bilibili.com/x/web-interface/nav')
            cross.assert_not_called()

    def test_missing_cookie_uses_fallback_once(self):
        api = LoginAPI()
        def exchange(*args, **kwargs):
            install_cookie(api)
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response
        with patch.object(api, '_request', return_value={'isLogin': True, 'mid': 1, 'uname': 'test'}), \
                patch.object(api.opener, 'open', side_effect=exchange) as cross:
            self.assertTrue(api.complete({'url': 'https://passport.biligame.com/crossDomain'}, threading.Event()))
            self.assertEqual(cross.call_count, 1)

    def test_cancelled_verification_makes_no_request(self):
        api = LoginAPI()
        install_cookie(api)
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(api, '_request') as request:
            self.assertIsNone(api.complete({}, cancelled))
            request.assert_not_called()


class LoginSessionTests(unittest.TestCase):
    def session(self, api):
        session = LoginSession(api, interval=.001, confirm_interval=.001, retry_delay=.001)
        results, failures = [], []
        session.succeeded.connect(results.append, Qt.DirectConnection)
        session.failed.connect(failures.append, Qt.DirectConnection)
        return session, results, failures

    def api(self):
        api = Mock()
        api.generate.return_value = {'url': 'https://example.test/qr', 'qrcode_key': 'synthetic-key'}
        api.poll.return_value = {'code': 0}
        api.complete.return_value = {'bili_uname': 'test'}
        return api

    def run_session(self, session):
        with patch.object(session, '_qr_png', return_value=b'png'):
            session.start()
            session.thread.join(2)
        self.assertFalse(session.thread.is_alive())

    def test_initial_generation_failure_recovers_and_starts_polling(self):
        api = self.api()
        generated = api.generate.return_value
        api.generate.side_effect = [OSError(), generated]
        session, results, errors = self.session(api)
        self.run_session(session)
        self.assertEqual(len(results), 1)
        self.assertFalse(errors)
        api.poll.assert_called_once_with('synthetic-key')

    def test_verified_immediately_after_scan_confirmation(self):
        api = self.api()
        api.poll.side_effect = [{'code': 86101}, {'code': 86090}, {'code': 0}]
        session, results, errors = self.session(api)
        self.run_session(session)
        self.assertEqual(len(results), 1)
        api.complete.assert_called_once()
        self.assertFalse(errors)

    def test_expired_qr_generates_again(self):
        api = self.api()
        api.poll.side_effect = [{'code': 86038}, {'code': 0}]
        session, results, errors = self.session(api)
        self.run_session(session)
        self.assertEqual(api.generate.call_count, 2)
        self.assertEqual(len(results), 1)

    def test_profile_retry_does_not_restart_polling_or_scan(self):
        api = self.api()
        api.complete.side_effect = [TimeoutError(), {'bili_uname': 'test'}]
        session, results, errors = self.session(api)
        self.run_session(session)
        api.poll.assert_called_once()
        self.assertEqual(len(results), 1)

    def test_cancel_during_http_ignores_late_result(self):
        api = self.api()
        entered, release = threading.Event(), threading.Event()
        def complete(*args):
            entered.set()
            release.wait(2)
            return {'bili_uname': 'late'}
        api.complete.side_effect = complete
        session, results, errors = self.session(api)
        with patch.object(session, '_qr_png', return_value=b'png'):
            session.start()
            self.assertTrue(entered.wait(1))
            session.cancel()
            release.set()
            session.thread.join(2)
        self.assertFalse(results)
        self.assertFalse(errors)

    def test_retries_bounded_and_error_does_not_leak_ticket(self):
        api = self.api()
        api.generate.side_effect = OSError('synthetic-secret-ticket')
        session, results, errors = self.session(api)
        self.run_session(session)
        self.assertEqual(api.generate.call_count, 3)
        self.assertEqual(len(errors), 1)
        self.assertNotIn('synthetic-secret-ticket', errors[0])
