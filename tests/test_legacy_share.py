import unittest
from app.room_share import make_legacy_invitation, make_share, parse_share

class LegacyShareTests(unittest.TestCase):
    def test_server_paths_and_room_are_preserved(self):
        for endpoint in ('ws://192.168.1.5:9877', 'wss://example.com/socket?key=abc', 'ws://[::1]:9877'):
            invite = parse_share(make_share(make_legacy_invitation(endpoint, '1234')))
            self.assertTrue(invite.legacy)
            self.assertEqual((invite.endpoint, invite.room), (endpoint, '1234'))
    def test_invalid_servers_and_room_are_rejected(self):
        for endpoint in ('https://example.com', 'ws://user:password@example.com', 'ws://host:99999', 'ws://host/#x'):
            with self.assertRaises(ValueError): make_legacy_invitation(endpoint, '1234')
        with self.assertRaises(ValueError): make_legacy_invitation('ws://host', '12')
