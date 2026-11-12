"""P2P signaling never discloses membership credentials or permits cross-peer control."""
import unittest
from server import Server, Room, Member

class Inbox:
    def __init__(self):
        self.messages=[]
    def send(self,message):
        self.messages.append(message)

class SignalingTests(unittest.TestCase):
    def setUp(self):
        self.server=Server(hosted=True)
        self.room=Room('1234')
        self.room.watch_mode='p2p'
        self.members=[Member(name,Inbox()) for name in ('host','a','b')]
        self.host,self.a,self.b=self.members
        self.room.members={m.token:m for m in self.members}
        self.room.publisher_id=self.host.peer_id
        self.stream={'type':'p2p_state','active':True,'stream_id':'a'*32,'title':'movie',
                     'duration':20,'position':0,'playing':True}
        self.server._p2p(self.room,self.host,self.stream)
        for m in self.members:m.peer.messages.clear()
    def test_ready_and_offer_are_targeted_without_tokens(self):
        self.server._p2p(self.room,self.a,{'type':'p2p_ready'})
        self.assertEqual(self.host.peer.messages[0]['from_peer'],self.a.peer_id)
        self.assertFalse(self.b.peer.messages)
        offer={'type':'p2p_signal','target':self.a.peer_id,'kind':'offer',
               'stream_id':'a'*32,'connection_id':'b'*32,'sdp':'v=0'}
        self.server._p2p(self.room,self.host,offer)
        self.assertEqual(self.a.peer.messages[0]['from_peer'],self.host.peer_id)
        self.assertNotIn(self.host.token,str(self.a.peer.messages))
        self.assertFalse(self.b.peer.messages)
    def test_viewer_cannot_publish_or_signal_another_viewer(self):
        with self.assertRaises(ValueError):self.server._p2p(self.room,self.a,self.stream)
        with self.assertRaises(ValueError):
            self.server._p2p(self.room,self.a,{'type':'p2p_signal','target':self.b.peer_id})
    def test_stale_stream_and_oversized_sdp_are_rejected(self):
        offer={'type':'p2p_signal','target':self.a.peer_id,'kind':'offer',
               'stream_id':'old','connection_id':'b'*32,'sdp':'v=0'}
        with self.assertRaises(ValueError):self.server._p2p(self.room,self.host,offer)
        offer.update(stream_id='a'*32,sdp='x'*65537)
        with self.assertRaises(ValueError):self.server._p2p(self.room,self.host,offer)
    def test_nonfinite_source_position_is_rejected(self):
        with self.assertRaises(ValueError):
            self.server._p2p(self.room,self.host,{**self.stream,'position':float('nan')})
