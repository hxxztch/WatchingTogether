import unittest
from app.room_share import make_share, parse_share

class ShareTests(unittest.TestCase):
    def setUp(self):
        self.link='wss://example.com/room/secret?room=1234'
    def test_text_and_raw_link_have_same_identity(self):
        text=make_share(self.link,'朋友','房主推流 · P2P')
        self.assertEqual(parse_share(text),parse_share(self.link))
        self.assertEqual(parse_share(text.replace('\n',' ')),parse_share(self.link))
    def test_duplicate_identical_links_are_one_invitation(self):
        self.assertEqual(parse_share(self.link+'\n'+self.link).room,'1234')
    def test_different_rooms_and_malformed_inputs_rejected(self):
        for text in ('', '1234','https://example.com', 'ws://a/host/secret?room=1234',
                     'ws://user:password@example.com/room/a?room=1234', 'x'*8193,
                     self.link+'\n'+self.link.replace('1234','5678')):
            with self.subTest(text=text[:60]),self.assertRaises(ValueError):parse_share(text)
    def test_room_identity_includes_secret_path_and_endpoint(self):
        a=parse_share(self.link)
        self.assertNotEqual(a.identity,parse_share(self.link.replace('secret','other')).identity)
        self.assertNotEqual(a.identity,parse_share(self.link.replace('example.com','other.com')).identity)
    def test_display_address_does_not_include_invitation_secret(self):
        self.assertEqual(parse_share(self.link).public_address,'wss://example.com')
    def test_share_metadata_cannot_inject_second_invitation(self):
        self.assertEqual(make_share(self.link,'x\n邀请人：y').count('\n邀请人：'),1)
