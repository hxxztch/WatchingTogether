"""Version-one human-readable embedded room invitations."""
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import urlsplit, parse_qs, urlencode

HEADER = '【超时空会夜机 · 房间邀请】'
MAX_TEXT = 8192

@dataclass(frozen=True)
class Invitation:
    endpoint: str
    room: str
    link: str
    legacy: bool = False

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
    links = re.findall(r'(?:wss?|watchingtogether)://[^\s<>"\u3000]+', text.strip())
    invitations = {}
    for link in links:
        # Only presentation punctuation may be trimmed, never query credentials.
        link = link.rstrip('，。；）】')
        if link.startswith('watchingtogether://'):
            try:
                parts = urlsplit(link)
                values = parse_qs(parts.query, strict_parsing=True)
                if parts.netloc != 'join' or parts.path or parts.fragment or set(values) != {'server', 'room'}:
                    raise ValueError()
                if any(len(v) != 1 for v in values.values()):
                    raise ValueError()
                endpoint, room = values['server'][0], values['room'][0]
                canonical = make_legacy_invitation(endpoint, room)
                invitation = Invitation(endpoint, room, canonical, True)
                invitations[invitation.identity] = invitation
            except ValueError:
                pass
            continue
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


def make_legacy_invitation(endpoint, room):
    parts = urlsplit(endpoint)
    if (parts.scheme not in ('ws', 'wss') or not parts.hostname or parts.username or parts.password or
            parts.fragment or len(endpoint) > 2048 or any(c.isspace() or ord(c) < 32 for c in endpoint) or
            (parts.port is not None and not 1 <= parts.port <= 65535) or
            not re.fullmatch(r'[0-9]{4}', room)):
        raise ValueError('服务器地址或房间号无效')
    return 'watchingtogether://join?' + urlencode({'server': endpoint, 'room': room})


def make_share(link, host='', watching='同步观影', connection='公共通道'):
    invitation = parse_share(link)
    def line(value):
        return str(value).replace('\r', ' ').replace('\n', ' ')[:64]
    details = ('服务器地址：' + invitation.endpoint + '\n房间号：' + invitation.room + '\n'
               if invitation.legacy else '')
    return '\n'.join((HEADER, '邀请人：' + line(host or '朋友'), '观影模式：' + line(watching),
                      '连接方式：' + line(connection), '', '邀请链接：' + invitation.link,
                      details, '复制这段信息，打开超时空会夜机客户端即可识别。'))
