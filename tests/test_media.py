import unittest
from unittest.mock import patch
from app.bilibili import BilibiliClient, BilibiliError, QualityUnavailable, mixin_key, sign_params, select_streams
from app.timecode import parse_timecode, format_timecode


class TimecodeTests(unittest.TestCase):
    def test_valid_formats_and_boundaries(self):
        for text, expected in [('0', 0), ('90', 90), ('01:30', 90), ('90:00', 5400), ('01:02:03', 3723)]:
            self.assertEqual(parse_timecode(text, 5400), expected)
        self.assertEqual(format_timecode(3723), '01:02:03')
        self.assertEqual(format_timecode(90), '01:30')

    def test_invalid_and_unknown_duration(self):
        for text in ['', '-1', 'NaN', '1.5', '1:60', '1:99:00', '1:2:3:4', '601']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_timecode(text, 600)
        with self.assertRaises(ValueError):
            parse_timecode('0', 0)


class BilibiliTests(unittest.TestCase):
    def fixture(self):
        return {'quality': 120, 'accept_quality': [120, 80, 64, 32, 16],
                'dash': {'video': [{'id': q, 'codecid': 7, 'baseUrl': f'https://example.test/{q}'}
                                   for q in (80, 120, 16, 64)],
                         'audio': [{'base_url': 'https://example.test/audio', 'codecs': 'mp4a'}]}}

    def test_requested_quality_matches_actual_representation(self):
        for quality in [120, 80, 64, 16]:
            video, audio, selected, available = select_streams(self.fixture(), quality, True)
            self.assertEqual(selected, quality)
            self.assertTrue(video.endswith('/' + str(quality)))
            self.assertTrue(audio.endswith('/audio'))
            self.assertNotIn('32', available)

    def test_permission_fallback_and_strict_switch(self):
        data = self.fixture()
        data['dash']['video'] = [{'id': 32, 'base_url': 'https://example.test/480'}]
        self.assertEqual(select_streams(data, 120)[2], 32)
        with self.assertRaises(QualityUnavailable) as error:
            select_streams(data, 120, True)
        self.assertEqual(list(error.exception.available), ['32'])

    def test_codec_preference_and_backup_url(self):
        data = self.fixture()
        data['dash']['video'].append({'id': 80, 'codecid': 12, 'bandwidth': 999999,
                                     'baseUrl': 'https://example.test/hevc'})
        data['dash']['video'][0] = {'id': 80, 'codecid': 7, 'backup_url': ['https://example.test/avc']}
        self.assertTrue(select_streams(data, 80)[0].endswith('/avc'))

    def test_progressive_rejects_wrong_quality_and_partial_video(self):
        data = {'quality': 32, 'durl': [{'url': 'https://example.test/480'}]}
        with self.assertRaises(QualityUnavailable):
            select_streams(data, 80, True)
        data['durl'] *= 2
        with self.assertRaises(BilibiliError):
            select_streams(data, 32)

    def test_known_wbi_signature_vector(self):
        key = mixin_key('https://example.test/7cd084941338484aae1ad9425b84077c.png',
                        'https://example.test/4932caff0ff746eab6f01bf08b70ac45.png')
        self.assertEqual(key, 'ea1db124af3c7062474693fa704f4ff8')
        signed = sign_params({'foo': '114', 'bar': '514', 'baz': '1919810'}, key, 1702204169)
        self.assertEqual(signed['w_rid'], '6149fdadf571698ca7e6a567265cd0ee')

    def test_web_fallback_and_no_retry_of_restricted_quality(self):
        client = BilibiliClient()
        with patch.object(client, '_get_key', return_value='test'), patch.object(
                client, '_request', side_effect=[OSError('offline'), {'code': 0, 'data': self.fixture()}]) as request:
            self.assertEqual(client.fetch_streams(1, 2, 80)[2], 80)
            self.assertIn('platform=web', request.call_args[0][0])
        with patch.object(client, '_get_key', return_value='test'), patch.object(
                client, '_request', return_value={'code': 0, 'data': self.fixture()}) as request:
            with self.assertRaises(QualityUnavailable):
                client.fetch_streams(1, 2, 32, strict=True)
            self.assertEqual(request.call_count, 1)
