"""Windows TLS selection must fail closed instead of reverting to OpenSSL."""
import unittest
from unittest.mock import patch

from app import runtime

runtime.configure_runtime()
from PySide6.QtNetwork import QSslSocket


class QtTlsTests(unittest.TestCase):
    def test_windows_selects_schannel_once(self):
        with patch.object(runtime.sys, 'platform', 'win32'), \
                patch.object(runtime, '_qt_tls_ready', False), \
                patch.object(QSslSocket, 'setActiveBackend', return_value=True) as select:
            self.assertTrue(runtime.configure_qt_tls())
            self.assertTrue(runtime.configure_qt_tls())
            select.assert_called_once_with('schannel')

    def test_missing_native_plugin_does_not_select_openssl(self):
        with patch.object(runtime.sys, 'platform', 'win32'), \
                patch.object(runtime, '_qt_tls_ready', False), \
                patch.object(QSslSocket, 'setActiveBackend', return_value=False) as select:
            self.assertFalse(runtime.configure_qt_tls())
            self.assertFalse(runtime._qt_tls_ready)
            select.assert_called_once_with('schannel')

    def test_other_platform_keeps_its_native_default(self):
        with patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(QSslSocket, 'setActiveBackend') as select:
            self.assertTrue(runtime.configure_qt_tls())
            select.assert_not_called()
