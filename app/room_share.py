"""Version-one human-readable embedded room invitations."""
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import urlsplit

HEADER = '【超时空会夜机 · 房间邀请】'
MAX_TEXT = 8192

@dataclass(frozen=True)
class Invitation:
    endpoint: str
    room: str
    link: str

    @property
    def identity(self):
        return hashlib.sha256((self.endpoint + '\n' + self.room).encode('utf-8')).hexdigest()

    @property
    def public_address(self):
        parts = urlsplit(self.endpoint)
        return parts.scheme + '://' + parts.netloc


def parse_share(text):
    from app.hosting import parse_invitation, make_invitation
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError('房间分享信息过长或格式无效')
    links = re.findall(r'wss?://[^\s<>"\u3000]+', text.strip())
    invitations = {}
    for link in links:
        # Only presentation punctuation may be trimmed, never query credentials.
        link = link.rstrip('，。；）】')
        try:
            endpoint, room = parse_invitation(link)
        except ValueError:
            continue
        if any(ord(c) < 32 for c in endpoint):
            continue
        canonical = make_invitation(endpoint, room)
        invitation = Invitation(endpoint, room, canonical)
        invitations[invitation.identity] = invitation
    if len(invitations) != 1:
        raise ValueError('请复制一份完整房间邀请；检测到多个不同邀请时请单独复制')
    return next(iter(invitations.values()))


def make_share(link, host='', watching='同步观影', connection='公共通道'):
    invitation = parse_share(link)
    def line(value):
        return str(value).replace('\r', ' ').replace('\n', ' ')[:64]
    return '\n'.join((HEADER, '邀请人：' + line(host or '朋友'), '观影模式：' + line(watching),
                      '连接方式：' + line(connection), '', '邀请链接：' + invitation.link,
                      '', '复制这段信息，打开超时空会夜机客户端即可识别。'))
