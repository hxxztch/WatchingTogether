"""Main application window."""
import os as _os, sys, logging, subprocess, shutil, re, json, urllib.request
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QMessageBox,
    QApplication, QLabel, QPushButton, QScrollArea, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer, QRect
import base64
import threading
from PySide6.QtGui import QIcon, QPixmap

from app.player import MpvWidget
from app.network import NetworkClient
from app.sync import PlaybackSynchronizer
from app.bilibili import BilibiliClient, BilibiliError, QualityUnavailable
from app.ui.room_panel import RoomPanel
from app.ui.controls import ControlsBar
from app.ui.danmaku import DanmakuOverlay
from app.version import CLIENT_NAME
from app.ui.shell import DesktopShell, MiniPlayer, WARM_STYLE, label

logging.basicConfig(level=logging.INFO)

if getattr(sys, 'frozen', False):
    _ASSETS = _os.path.join(sys._MEIPASS, "assets")
else:
    _ASSETS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets")



class MainWindow(QMainWindow):
    _hotkey = Signal(str)
    _quality_result = Signal(int, object)

    def __init__(self, legacy_autoconnect=False):
        super().__init__()
        self.setWindowTitle(CLIENT_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(WARM_STYLE)
        _pix = QPixmap()
        _pix.loadFromData(base64.b64decode("""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"""))
        if not _pix.isNull():
            self.setWindowIcon(QIcon(_pix))

        self._room_code = ""
        self._closing = False
        self._room_ready = False
        self._playback_sync = PlaybackSynchronizer()
        self._bili_info = None  # {bvid, avid, cid, headers, quality_map, current_qn}
        self._bili_api = BilibiliClient()
        self._quality_generation = 0
        self._quality_busy = False
        self._quality_result.connect(self._finish_quality_change)
        self._my_name = ""
        self._syncing = False

        self._room_panel = RoomPanel()
        from app.room_controller import RoomController
        self._rooms = RoomController(self)
        self._room_panel.cancel_requested.connect(self._rooms.cancel)
        self._room_panel.lan_address.currentIndexChanged.connect(self._rooms.update_lan_invitation)
        self._room_panel.create_requested.connect(self._on_create_room)
        self._room_panel.join_requested.connect(self._on_join_room)
        self._room_panel.leave_requested.connect(self._on_leave_room)
        self._room_panel.chat_message.connect(self._on_chat)
        self._room_panel.refresh_connection.connect(self._reconnect_network)
        self._controls = ControlsBar()
        self._controls.bili_login_requested.connect(self._on_bili_login)
        self._controls.bili_logout_requested.connect(self._on_bili_logout)
        self._controls.danmaku_sent.connect(self._on_chat)
        self._controls.play_toggled.connect(self._on_toggle_play)
        self._controls.seek_requested.connect(self._on_seek)
        self._controls.volume_changed.connect(self._player_volume)
        self._controls.file_selected.connect(self._on_load_file)
        self._controls.url_submitted.connect(self._on_load_url)
        self._controls.stop_requested.connect(self._on_stop)
        self._controls.audio_selected.connect(self._on_audio_select)
        self._controls.quality_selected.connect(self._on_quality_change)
        self._restore_bili_login()
        self._controls.page_changed.connect(self._on_page_change)
        self._controls.fullscreen_toggled.connect(self._on_fullscreen)
        self._controls.subtitle_requested.connect(self._choose_subtitle)
        self._controls.subtitle_undo_requested.connect(self._undo_subtitle)

        self._network = NetworkClient(self._room_panel.get_server_url())
        self._network.signals.connected.connect(self._on_connected)
        self._network.signals.disconnected.connect(self._on_disconnected)
        self._network.signals.message_received.connect(self._on_message)
        self._network.signals.error_occurred.connect(self._on_net_error)
        self._network.signals.latency_updated.connect(self._on_latency)
        if legacy_autoconnect:
            self._room_panel.mode.setCurrentIndex(2)
            self._network.start()

        self._player = MpvWidget()
        self._player.subtitles_changed.connect(self._controls._subtitle_undo.setEnabled)
        self.setAcceptDrops(True)
        self._player.position_changed.connect(self._on_position)
        self._player.playback_started.connect(lambda: self._controls.set_playing(True))
        self._player.playback_paused.connect(lambda: self._controls.set_playing(False))
        self._player.media_load_failed.connect(
            lambda: self._room_panel.set_status("视频流加载失败，请重试或重新解析视频链接", "#f44336"))

        self._danmaku = DanmakuOverlay(self)
        self._danmaku.track(self._player)

        self._hotkey.connect(self._on_hotkey)

        center = QWidget()
        hlayout = QHBoxLayout(center)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)

        left = QWidget()
        left.setObjectName("roomCard")
        l2 = QVBoxLayout(left)
        l2.setContentsMargins(0, 0, 0, 0)
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._right_scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')
        side_content = QWidget()
        side_content.setObjectName('sideContent')
        side_content.setStyleSheet('#sideContent { background: #fff; }')
        side_layout = QVBoxLayout(side_content)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(self._controls.media_panel)
        side_layout.addWidget(self._room_panel, 1)
        self._right_scroll.setWidget(side_content)
        l2.addWidget(self._right_scroll)
        left.setFixedWidth(300)

        right = QWidget()
        r2 = QVBoxLayout(right)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(0)
        r2.addWidget(self._player, stretch=1)
        self._video_layout = r2
        # A translucent owned tool window composites over mpv's native HWND.
        # A regular sibling QWidget would blend against Qt's backing store,
        # hiding the video behind a solid rectangle on Windows.
        self._controls.setParent(self, Qt.Tool | Qt.FramelessWindowHint)
        self._controls.setAttribute(Qt.WA_TranslucentBackground, True)
        self._controls.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._controls.setObjectName("controlsBar")
        self._controls.setAttribute(Qt.WA_StyledBackground, True)
        self._controls.setStyleSheet(WARM_STYLE + "\n#controlsBar { background: transparent; border: none; }")
        self._player_container = right

        s = QSplitter(Qt.Horizontal)
        s.addWidget(right)
        s.addWidget(left)
        s.setChildrenCollapsible(False)
        s.setStretchFactor(0, 1)
        s.setStretchFactor(1, 0)
        s.setSizes([1000, 280])
        self._splitter = s
        hlayout.addWidget(s)
        self._left_panel = left
        self._pip = MiniPlayer(self)
        self._controls.media_title_changed.connect(self._pip.refresh_title)
        self._pip.return_requested.connect(lambda: self._switch_page(1))
        self._empty_stage = QWidget(right)
        self._empty_stage.setObjectName("emptyStage")
        self._empty_stage.setAttribute(Qt.WA_StyledBackground, True)
        self._empty_stage.setStyleSheet("#emptyStage { background: #f0f1f2; border-top-left-radius: 14px; border-top-right-radius: 14px; }")
        empty_layout = QVBoxLayout(self._empty_stage)
        empty_layout.setContentsMargins(28, 28, 28, 28)
        empty_layout.addStretch()
        mark = QLabel()
        mark.setPixmap(self.windowIcon().pixmap(64, 64))
        empty_layout.addWidget(mark, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(16)
        empty_layout.addWidget(label("银幕就绪，等你开场", "heading"), alignment=Qt.AlignCenter)
        empty_layout.addWidget(label("打开一部影片，再邀请朋友一起看。", "subtle"), alignment=Qt.AlignCenter)
        empty_layout.addSpacing(16)
        open_row = QHBoxLayout()
        open_row.addStretch()
        self._empty_open = QPushButton("打开本地视频")
        self._empty_open.setObjectName("primary")
        self._empty_open.clicked.connect(self._controls._on_open_file)
        self._empty_url = QPushButton("粘贴视频链接")
        self._empty_url.clicked.connect(self._controls._on_url_dialog)
        open_row.addWidget(self._empty_open)
        open_row.addWidget(self._empty_url)
        open_row.addStretch()
        empty_layout.addLayout(open_row)
        empty_layout.addStretch()
        self._shell = DesktopShell(self, center)
        self._shell.page_requested.connect(self._switch_page)
        self.setCentralWidget(self._shell)

        from PySide6.QtCore import QTimer as _QTimer
        self._vid_info_timer = _QTimer(self)
        self._vid_info_timer.timeout.connect(self._poll_video_info)
        self._vid_info_timer.start(2000)
        self._fs_timer = _QTimer()
        self._fs_timer.setSingleShot(True)
        self._fs_timer.timeout.connect(self._hide_fs_controls)
        self._fs_mouse_timer = _QTimer()
        self._fs_mouse_timer.timeout.connect(self._check_fs_mouse)
        self._fs_mouse_timer.start(100)
        self._controls_hide_delay = 1800

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _reconnect_network(self, url: str):
        """Stop current connection and reconnect to a new server URL."""
        self._room_panel.set_status("正在连接...", "#FFD54F")
        if hasattr(self, '_network') and self._network:
            if not self._network.stop():
                self._room_panel.set_status("连接仍在关闭，请稍后重试", "#f44336")
                return False
            self._network.deleteLater()
        self._room_code = ""
        self._room_ready = False
        self._playback_sync = PlaybackSynchronizer()
        self._room_panel.set_in_room(False)
        self._player.set_speed(1.0)
        self._network = NetworkClient(url, recovery_timeout=90 if self._rooms.integrated else None)
        self._network.signals.connected.connect(self._on_connected)
        self._network.signals.disconnected.connect(self._on_disconnected)
        self._network.signals.message_received.connect(self._on_message)
        self._network.signals.error_occurred.connect(self._on_net_error)
        self._network.signals.latency_updated.connect(self._on_latency)
        self._network.start()
        return True

    def _player_volume(self, vol):
        if hasattr(self, "_player"):
            self._player.set_volume(vol)

    def _on_stop(self):
        self._invalidate_quality_request()
        self._bili_info = None
        self._controls.set_video_quality("", None)
        self._controls.set_pages([], 0)
        self._controls.set_audio_tracks([], -1)
        self._controls.set_position(0, 0)
        self._controls.set_playing(False)
        self._player.stop()
        self._controls.set_media_title('尚未打开视频')

    def _on_audio_select(self, track_id):
        self._player.set_audio_track(track_id)

    def _refresh_audio_tracks(self):
        QTimer.singleShot(500, lambda: self._do_refresh_audio())

    def _do_refresh_audio(self):
        if self._bili_info:
            return
        tracks = self._player.get_audio_tracks()
        if tracks:
            self._controls.set_audio_tracks(tracks)

    def _on_connected(self):
        if not self._current_network_event() or self._network._stopping.is_set():
            return
        self._rooms.connected()
        self._room_panel.set_status("正在恢复房间..." if self._room_code else "已连接", "#4CAF50")
        self._room_panel.update_server_label(self._room_panel.get_server_url())
    def _on_disconnected(self):
        if not self._current_network_event():
            return
        if self._network._stopping.is_set():
            return
        self._room_ready = False
        self._player.set_speed(1.0)
        self._room_panel.set_latency(None)
        self._room_panel.set_status("连接中断，正在自动重连...", "#FFD54F")

    def _on_latency(self, milliseconds):
        if not self._current_network_event():
            return
        if self._room_ready:
            self._room_panel.set_latency(milliseconds)

    def _apply_room_state(self, state, force=False):
        if not self._room_ready or self._player.is_loading:
            return
        try:
            plan = self._playback_sync.plan(
                state, self._player.position, self._player.duration, force=force)
            if plan is None:
                return
            self._player.set_speed(plan["speed"])
            if plan["seek"] is not None:
                self._player.seek(plan["seek"])
            if plan["playing"]:
                self._player.play()
            else:
                self._player.pause()
        except (TypeError, ValueError, RuntimeError):
            logging.exception("Could not apply room playback state")

    def _current_network_event(self):
        source = self.sender()
        return source is None or source is self._network.signals

    def _on_net_error(self, err):
        if self._current_network_event() and not self._network._stopping.is_set():
            self._room_panel.set_status(err, "#f44336")

    def _on_message(self, msg):
        if not self._current_network_event():
            return
        if self._closing or (self._network._stopping.is_set() and msg.get('type') not in ('room_closed', 'left_room')):
            return
        self._rooms.message(msg)
        mtype = msg.get("type", "")
        self._syncing = True
        try:
            if mtype in ("room_created", "room_joined"):
                self._room_code = msg["room"]
                self._room_ready = True
                self._playback_sync = PlaybackSynchronizer()
                self._my_name = msg.get("name", self._my_name)
                self._room_panel.set_in_room(True, self._room_code, msg.get("members", []))
                self._room_panel.set_status(
                    ("已恢复房间 " if msg.get("resumed") else "已加入房间 ") + self._room_code,
                    "#4CAF50")
                self._apply_room_state(msg.get("state", {}), force=True)
            elif mtype == "left_room":
                self._room_code = ""
                self._room_ready = False
                self._player.set_speed(1.0)
                self._room_panel.set_in_room(False)
                self._room_panel.set_status("已离开房间", "#999")
            elif mtype in ("session_expired", "room_closed"):
                self._room_code = ""
                self._room_ready = False
                self._player.set_speed(1.0)
                self._room_panel.set_in_room(False)
                self._room_panel.set_status(msg.get('message', "房主已离开，房间已解散") if mtype == "room_closed" else
                                            "房间已过期或服务端已重启，请重新创建或加入", "#95724f")
            elif mtype == "delivery_failed":
                self._room_panel.add_chat("系统", msg["message"])
            elif mtype == "member_joined":
                self._room_panel.add_chat("系统", msg["name"] + " 加入了")
                self._room_panel.update_members(msg.get("members", []))
            elif mtype == "member_left":
                self._room_panel.add_chat("系统", msg["name"] + " 离开了")
                self._room_panel.update_members(msg.get("members", []))
            elif mtype == "load":
                self._room_panel.add_chat("系统", msg.get("from", "") + " 加载了文件")
            elif mtype == "play":
                target = msg.get("position", 0)
                if abs(target - self._player.position) > 1.0:
                    self._player.seek(target)
                self._player.play()
            elif mtype == "pause":
                self._player.pause()
                self._player.set_speed(1.0)
                if "position" in msg:
                    self._player.seek(msg["position"])
            elif mtype == "seek_rel":
                self._player.seek_relative(msg.get("delta", 0))
            elif mtype == "seek":
                pos = msg.get("position", 0)
                self._player.seek(pos)
            elif mtype == "chat":
                self._room_panel.add_chat(msg.get("from", ""), msg.get("message", "")); self._danmaku.show_danmaku(msg.get("from", ""), msg.get("message", ""))
            elif mtype == "sync_state":
                if msg.get("room", self._room_code) == self._room_code:
                    self._apply_room_state(msg.get("state", {}))
            elif mtype == "error":
                QMessageBox.warning(self, "错误", msg.get("message", ""))
        finally:
            self._syncing = False

    
    def _fetch_bilibili_streams(self, avid, cid, qn, headers, strict=False):
        from app.config import load as load_config
        return self._bili_api.fetch_streams(
            avid, cid, qn, headers, cookie=load_config().get("bili_cookie", ""), strict=strict)

    def _on_create_room(self, name):
        self._my_name = name
        if self._room_panel.mode.currentIndex() != 2:
            self._rooms.create(name)
            return
        if self._network._ws is None:
            self._rooms.connect(self._room_panel.get_server_url(), {'type': 'create_room', 'name': name})
            return
        self._network.send({"type": "create_room", "name": name})

    def _on_join_room(self, room, name):
        self._my_name = name
        if self._room_panel.mode.currentIndex() != 2:
            self._rooms.join(room, name)
            return
        if self._network._ws is None:
            self._rooms.connect(self._room_panel.get_server_url(), {'type': 'join_room', 'room': room, 'name': name})
            return
        self._network.send({"type": "join_room", "room": room, "name": name})

    def _on_leave_room(self):
        if self._rooms.host is not None or self._rooms.integrated:
            self._rooms.cancel()
            return
        self._network.send({"type": "leave_room"})
        self._room_code = ""
        self._room_ready = False
        self._player.set_speed(1.0)

    def _on_bili_login(self):
        from app.ui.bili_login_dialog import BiliLoginDialog
        from PySide6.QtWidgets import QDialog
        dialog = BiliLoginDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.login_result:
            name = dialog.login_result["bili_uname"]
            self._controls.set_bili_status(True, name)
            self._room_panel.set_status("bilibili\u767b\u5f55\u6210\u529f: " + name, "#4CAF50")
        dialog.deleteLater()

    def _on_bili_logout(self):
        from app.config import save as _cfg_save
        if not _cfg_save(bili_cookie="", bili_uid="", bili_uname=""):
            message = '退出登录未保存，请检查配置目录的写入权限后重试。'
            self._room_panel.set_status(message, '#b36b4a')
            if hasattr(self, '_shell'):
                self._shell.profile.feedback.setText(message)
            return
        self._invalidate_quality_request()
        self._controls.set_bili_status(False)

    def _restore_bili_login(self):
        """Restore bilibili login status from config on startup."""
        try:
            from app.config import load as _cfg_load
            cfg = _cfg_load()
            cookie = cfg.get("bili_cookie", "")
            uname = cfg.get("bili_uname", "")
            if cookie and uname:
                self._controls.set_bili_status(True, uname)
            else:
                self._controls.set_bili_status(False)
        except Exception:
            self._controls.set_bili_status(False)


    def _on_chat(self, text):
        if self._room_code:
            self._network.send({"type": "chat", "message": text})
            self._room_panel.add_chat("我", text)
            self._danmaku.show_danmaku("我", text)

    def _on_toggle_play(self):
        if self._player.is_playing:
            pos = self._player.position
            self._player.pause()
            if self._room_code:
                self._network.send({"type": "pause", "position": pos})
        else:
            pos = self._player.position
            self._player.play()
            if self._room_code:
                self._network.send({"type": "play", "position": pos})

    def _on_seek(self, pos):
        if self._player.is_loading or self._player.duration <= 0:
            self._room_panel.set_status("请等待视频加载完成后再跳转", "#FFD54F")
            return
        self._player.seek(pos)
        if self._room_code:
            self._network.send({"type": "seek", "position": pos})

    def _on_load_file(self, path):
        self._controls.set_media_title(_os.path.basename(path.replace('\\', '/')), '本地视频')
        self._empty_stage.hide()
        self._invalidate_quality_request()
        self._bili_info = None
        self._controls.set_video_quality("", None)
        self._controls.set_pages([], 0)
        self._controls.set_audio_tracks([], -1)
        self._player.load(path, resume_play=True)
        self._refresh_audio_tracks()
        if self._room_code:
            self._network.send({"type": "load", "path": path})

    def _resolve_bilibili(self, url):
        """Resolve a Bilibili video URL using the unified stream fetcher.

        Uses DASH by default so that the initial load and quality switches share
        the same playback path.  Falls back to FLV only when DASH is unavailable.
        """
        bvid_match = re.search(r"BV[a-zA-Z0-9]{10}", url)
        if not bvid_match:
            return None
        bvid = bvid_match.group()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        try:
            req = urllib.request.Request(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                headers=headers,
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            if resp.get("code") != 0:
                return None
            data = resp["data"]
            avid, cid = data["aid"], data["cid"]
            pages = data.get("pages", [])
            page_list = [
                (p.get("page", i + 1), p.get("part", "P" + str(i + 1)))
                for i, p in enumerate(pages)
            ]

            video_url, audio_url, actual_qn, quality_map = self._fetch_bilibili_streams(
                avid, cid, 120, headers
            )
            if not video_url:
                return None

            current_desc = quality_map.get(str(actual_qn), str(actual_qn) + "P")

            self._bili_info = {
                "title": data.get("title", bvid),
                "bvid": bvid,
                "avid": avid,
                "cid": cid,
                "headers": headers,
                "quality_map": quality_map,
                "current_qn": actual_qn,
                "pages": page_list,
            }

            return {
                "title": data.get("title", bvid),
                "video_url": video_url,
                "audio_url": audio_url,
                "quality_map": quality_map,
                "current_qn": str(actual_qn),
                "current_desc": current_desc,
                "pages": page_list,
            }
        except Exception:
            return None


    def _resolve_ytdlp(self, url):
        """Use yt-dlp to resolve a site URL to a direct media URL."""
        if any(url.lower().endswith(e) for e in ('.mp4', '.mkv', '.avi', '.m3u8', '.flv', '.webm', '.mov')):
            return None
        ytdlp = shutil.which('yt-dlp')
        if ytdlp:
            try:
                # Hide console window on Windows
                si = None
                if hasattr(subprocess, 'STARTUPINFO'):
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                flags = 0x08000000 if _os.name == 'nt' else 0  # CREATE_NO_WINDOW
                r = subprocess.run(
                    [ytdlp, '-f', 'best[ext=mp4]/best', '--dump-single-json', '--no-playlist', '--no-warnings', url],
                    capture_output=True, text=True, timeout=60,
                    startupinfo=si, creationflags=flags
                )
                if r.returncode == 0 and r.stdout.strip():
                    info = json.loads(r.stdout)
                    self._resolved_title = info.get('title') or ''
                    return info.get('url') or (info.get('requested_formats') or [{}])[0].get('url')
            except Exception as e:
                pass
        # Try Python module (fallback)
        try:
            from yt_dlp import YoutubeDL
            with YoutubeDL({'quiet': True, 'no_warnings': True, 'format': 'best'}) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    self._resolved_title = info.get('title') or ''
                    u = info.get('url') or (info.get('requested_formats') or [{}])[0].get('url')
                    return u
        except:
            pass
        return None

    def _on_load_url(self, url):
        """Load from URL.  B站 videos use unified DASH-first path."""
        from urllib.parse import urlsplit, unquote
        parsed = urlsplit(url)
        fallback_title = unquote(parsed.path.rstrip('/').split('/')[-1]) or parsed.hostname or '网页视频'
        self._resolved_title = ''
        self._controls.set_media_title(fallback_title, '网页视频')
        self._invalidate_quality_request()
        self._bili_info = None
        self._controls.set_audio_tracks([], -1)
        bili = self._resolve_bilibili(url)
        if bili:
            self._controls.set_media_title(bili.get('title') or fallback_title, 'bilibili')
            audio_url = bili.get("audio_url", "")
            current_desc = bili.get("current_desc", "")
            self._room_panel.set_status("B站解析成功: " + current_desc, "#4CAF50")

            if audio_url:
                self._player.load_dash(bili["video_url"], audio_url, resume_play=True, seek_pos=0)
            else:
                self._player.replace_flv(bili["video_url"], 0, True)

            qmap = bili.get("quality_map", {})
            self._controls.set_video_quality(current_desc, qmap)
            pages = bili.get("pages", [])
            if pages and len(pages) > 1:
                self._controls.set_pages(pages, 0)
            else:
                self._controls.set_pages([], 0)
        else:
            resolved = self._resolve_ytdlp(url)
            if resolved:
                self._controls.set_media_title(self._resolved_title or fallback_title, '网页视频')
                self._room_panel.set_status("解析成功", "#4CAF50")
                url = resolved
            self._player.load(url, resume_play=True)
            self._bili_info = None
            self._controls.set_video_quality("", None)
            self._controls.set_pages([], 0)
        self._player.play()
        self._refresh_audio_tracks()
        if self._room_code:
            self._network.send({"type": "load", "path": url})


    def _poll_video_info(self):
        """Show actual mpv resolution in the quality label."""
        if self._player.is_loading:
            return
        label = self._player.get_quality_label()
        if not label:
            # Still show prefix even when mpv hasnt reported resolution yet
            if self._bili_info:
                self._controls._quality_label.setText("画质: ")
            return
        if self._bili_info:
            self._controls._quality_label.setText("画质: " + label)
        else:
            self._controls.set_video_quality(label, None)

    def _invalidate_quality_request(self):
        self._quality_generation += 1
        self._quality_busy = False
        self._controls.set_quality_busy(False)

    def _restore_quality_controls(self, bi):
        current = bi["quality_map"].get(str(bi["current_qn"]), "")
        self._controls.set_video_quality(current, bi["quality_map"])
        self._poll_video_info()

    def _on_quality_change(self, selection):
        """Resolve a specific representation without blocking Qt or room synchronization."""
        bi = self._bili_info
        if not bi or not selection:
            return
        if self._quality_busy or self._player.is_loading:
            self._restore_quality_controls(bi)
            self._room_panel.set_status("视频正在加载，请稍后切换", "#FFD54F")
            return
        qn = int(selection) if selection in bi["quality_map"] else next(
            (int(q) for q, desc in bi["quality_map"].items() if desc == selection), None)
        if qn is None:
            return
        if qn == bi["current_qn"] and self._player.duration > 0:
            self._room_panel.set_status("当前已是所选清晰度", "#FFD54F")
            return

        self._quality_generation += 1
        generation = self._quality_generation
        self._quality_busy = True
        self._controls.set_quality_busy(True)
        self._room_panel.set_status("正在获取清晰度: " + bi["quality_map"][str(qn)], "#FFD54F")

        def fetch():
            try:
                result = self._fetch_bilibili_streams(
                    bi["avid"], bi["cid"], qn, bi["headers"], strict=True)
            except Exception as exc:
                result = exc
            try:
                self._quality_result.emit(generation, (bi, result))
            except RuntimeError:
                pass  # Window was closed while the HTTP request completed.

        threading.Thread(target=fetch, daemon=True).start()

    def _finish_quality_change(self, generation, payload):
        if generation != self._quality_generation:
            return
        bi, result = payload
        if bi is not self._bili_info:
            return
        self._quality_busy = False
        self._controls.set_quality_busy(False)
        if isinstance(result, Exception):
            if isinstance(result, QualityUnavailable):
                bi["quality_map"] = result.available
            self._restore_quality_controls(bi)
            detail = str(result) if isinstance(result, BilibiliError) else type(result).__name__
            self._room_panel.set_status("画质切换失败: " + detail, "#f44336")
            return

        video_url, audio_url, new_qn, quality_map = result
        try:
            # Capture the position now, not before the potentially slow API request.
            pos, was_playing = self._player.position, self._player.is_playing
            if audio_url:
                self._player.load_dash(video_url, audio_url, was_playing, pos)
            else:
                self._player.replace_flv(video_url, pos, was_playing)
            bi["current_qn"] = new_qn
            bi["quality_map"] = quality_map
            actual_desc = quality_map[str(new_qn)]
            self._controls.set_video_quality(actual_desc, quality_map)
            self._controls._quality_label.setText("画质: 加载中")
            self._room_panel.set_status("正在加载: " + actual_desc, "#FFD54F")
            logging.info("Bilibili stream selected: qn=%s", new_qn)
        except Exception as exc:
            self._restore_quality_controls(bi)
            self._room_panel.set_status("视频流加载失败: " + type(exc).__name__, "#f44336")


    def _on_page_change(self, page_idx):
        """Switch to a different episode / page of a B站 video."""
        self._invalidate_quality_request()
        bi = self._bili_info
        if not bi or not bi.get("pages"):
            return
        pages = bi["pages"]
        if page_idx < 1 or page_idx > len(pages):
            return
        page_num, page_title = pages[page_idx - 1]

        new_cid = None
        try:
            headers = bi["headers"]
            req = urllib.request.Request(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bi['bvid']}",
                headers=headers,
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            if resp.get("code") == 0:
                for p in resp["data"].get("pages", []):
                    if p.get("page") == page_num:
                        new_cid = p.get("cid")
                        break
        except Exception:
            pass
        if not new_cid:
            self._room_panel.set_status("分P切换失败", "#f44336")
            return

        try:
            video_url, audio_url, actual_qn, quality_map = self._fetch_bilibili_streams(
                bi["avid"], new_cid, bi["current_qn"], bi["headers"]
            )
            if not video_url:
                self._room_panel.set_status("分P切换失败", "#f44336")
                return

            if audio_url:
                self._player.load_dash(video_url, audio_url, resume_play=True, seek_pos=0)
            else:
                self._player.replace_flv(video_url, 0, True)

            bi["cid"] = new_cid
            self._controls.set_media_title((bi.get('title') or bi['bvid']) + ' · ' + page_title, 'bilibili')
            bi["current_qn"] = actual_qn
            if quality_map:
                bi["quality_map"] = quality_map
            current_desc = bi["quality_map"].get(str(actual_qn), str(actual_qn) + "P")
            self._controls.set_video_quality(current_desc, bi["quality_map"])
            self._room_panel.set_status("切换到: " + page_title, "#4CAF50")
            if self._room_code and video_url:
                self._network.send({"type": "load", "path": video_url})
        except Exception as e:
            self._room_panel.set_status("分P切换失败: " + str(e)[:30], "#f44336")
            logging.error("Page switch error: %s", e)


    def _on_position(self, pos):
        if self._closing:
            return
        self._controls.set_position(pos, self._player.duration)

    def _on_hotkey(self, action):
        if action in ("left", "right"):
            delta = -5.0 if action == "left" else 5.0
            if self._room_code:
                if not self._room_ready:
                    self._room_panel.set_status("正在恢复房间，暂时无法同步跳转", "#FFD54F")
                    return
                # One operation at the server's current timeline. Applying the
                # returned absolute snapshot also avoids rapid-key local races.
                message = {"type": "seek_rel", "delta": delta}
                if not self._player.is_loading and self._player.duration > 0:
                    message["duration"] = self._player.duration
                self._network.send(message)
            elif self._player.duration > 0 and not self._player.is_loading:
                self._player.seek_relative(delta)
        elif action == "esc" and self.isFullScreen():
            self._exit_fullscreen()

    def eventFilter(self, obj, event):
        if obj is self and event.type() in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.WindowStateChange):
            QTimer.singleShot(0, self._position_controls)
        if event.type() == QEvent.KeyPress:
            # Navigation on Home must not issue playback commands to the room.
            in_pip = hasattr(self, '_pip') and isinstance(obj, QWidget) and obj.window() is self._pip
            if hasattr(self, '_shell') and self._shell.pages.currentIndex() != 1 and not in_pip:
                return super().eventFilter(obj, event)
            # Don't steal keys from text input widgets
            from PySide6.QtWidgets import QLineEdit
            if isinstance(obj, QLineEdit) or isinstance(QApplication.focusWidget(), QLineEdit):
                return super().eventFilter(obj, event)
            # A global filter must not process another window's keys or steal
            # navigation from an open dialog/menu.
            if isinstance(obj, QWidget) and obj.window() not in (self, self._controls) and not in_pip:
                return super().eventFilter(obj, event)
            if QApplication.activeModalWidget() or QApplication.activePopupWidget():
                return super().eventFilter(obj, event)
            k = event.key()
            if k in (Qt.Key_Left, Qt.Key_Right):
                if not event.isAutoRepeat():
                    self._on_hotkey("left" if k == Qt.Key_Left else "right")
                return True
            elif k == Qt.Key_Space:
                if not event.isAutoRepeat():
                    self._on_toggle_play()
                return True
            elif k == Qt.Key_Escape and self.isFullScreen():
                self._exit_fullscreen()
                return True
        if obj is self._player and event.type() == QEvent.Resize:
            self._danmaku.track(self._player)
            self._position_controls()
        if hasattr(self, '_player_container') and obj is self._player_container and event.type() == QEvent.Resize:
            self._position_controls()
        return super().eventFilter(obj, event)

    def _on_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._switch_page(1)
        self._was_maximized = self.isMaximized()
        self._shell.fullscreen(True)
        self._left_panel.hide()
        self._controls.hide()
        self._fs_timer.stop()
        # Save splitter sizes and give all space to player
        self._saved_sizes = self._splitter.sizes()
        self._splitter.setSizes([self._splitter.width(), 0])
        self.showFullScreen()
        self._position_controls()
        # Force mpv to fill the entire window (fixes black bar at top on Windows)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._player.update())

    def _exit_fullscreen(self):
        self._shell.fullscreen(False)
        self._left_panel.show()
        self._fs_timer.stop()
        self.showMaximized() if getattr(self, '_was_maximized', False) else self.showNormal()
        self._position_controls()
        # Restore splitter sizes
        if hasattr(self, '_saved_sizes'):
            self._splitter.setSizes(self._saved_sizes)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._player.update())

    def _position_controls(self):
        """Follow the native video surface with a genuinely transparent overlay."""
        if hasattr(self, '_empty_stage'):
            self._empty_stage.setGeometry(self._player.geometry())
        if not hasattr(self, '_shell'):
            return
        if self._shell.pages.currentIndex() != 1 or not self.isVisible() or self.isMinimized():
            self._controls.hide()
            self._controls._vol_popup.hide()
            return
        origin = self._player.mapToGlobal(self._player.rect().topLeft())
        compact = self._player.width() < 680
        self._controls.layout().setSpacing(4 if compact else 10)
        margin = 8 if compact else 14
        self._controls.layout().setContentsMargins(margin, 10, margin, 12)
        for button in (self._controls._play_btn, self._controls._stop_btn,
                       self._controls._vol_btn, self._controls._fs_btn):
            button.setFixedWidth(32 if compact else 38)
        ch = self._controls.sizeHint().height()
        self._controls.setGeometry(origin.x(), origin.y() + self._player.height() - ch,
                                   self._player.width(), ch)

    def _controls_hovered(self):
        from PySide6.QtGui import QCursor
        if not self._player.isVisible():
            return False
        origin = self._player.mapToGlobal(self._player.rect().topLeft())
        zone = QRect(origin.x(), origin.y() + max(0, self._player.height() - 76),
                     self._player.width(), min(76, self._player.height()))
        if not zone.contains(QCursor.pos()):
            return False
        under_pointer = QApplication.widgetAt(QCursor.pos())
        if under_pointer is not None:
            return under_pointer.window() in (self, self._controls, self._danmaku)
        # Native mpv HWNDs / input-transparent overlays aren't always mapped by
        # widgetAt on Windows. Only use this fallback while our window is active.
        return QApplication.activeWindow() in (self, self._controls)

    def _controls_interacting(self):
        return (self._controls._bar_danmaku_input.hasFocus() or
                self._controls.is_editing_time or self._controls._dragging_seek or
                self._controls._seek_bar.isSliderDown() or self._controls._vol_slider_v.isSliderDown() or
                self._controls._vol_popup.isVisible())

    def _switch_page(self, index):
        if index != 1 and self.isFullScreen():
            self._exit_fullscreen()
        if index != 1 and self._player.is_playing and self._player.duration > 0:
            if not self._pip.isVisible():
                self._video_layout.removeWidget(self._player)
                self._pip.body.insertWidget(0, self._player, 1)
                self._player.show()
                self._controls._vol_popup.hide()
                screen = self.screen().availableGeometry()
                self._pip.move(screen.right() - self._pip.width() - 24,
                               screen.bottom() - self._pip.height() - 24)
                self._pip.show()
        elif index == 1 and self._player.parentWidget() is self._pip:
            self._pip.body.removeWidget(self._player)
            self._video_layout.insertWidget(0, self._player, 1)
            self._pip.hide()
            self._player.show()
        self._shell.set_page(index)
        if index != 1:
            self._controls.hide()
            self._controls._vol_popup.hide()
        self._shell.refresh_status()
        QTimer.singleShot(0, self._position_controls)
        self._danmaku.track(self._player)
        if index == 1:
            self._player.setFocus()

    def _hide_fs_controls(self):
        if self._controls_interacting() or self._controls_hovered():
            return
        self._controls.hide()

    def _check_fs_mouse(self):
        if QApplication.activeModalWidget():
            self._controls.hide()
            self._controls._vol_popup.hide()
            return
        if not hasattr(self, '_shell'):
            return
        if (self._shell.pages.currentIndex() != 1 or not self.isVisible() or
                self.isMinimized() or self._pip.isVisible()):
            self._fs_timer.stop()
            self._controls.hide()
            self._controls._vol_popup.hide()
            return
        if self._controls_hovered() or self._controls_interacting():
            self._position_controls()
            if not self._controls.isVisible():
                self._controls.show()
                self._controls.raise_()
            self._fs_timer.stop()
        elif self._controls.isVisible() and not self._fs_timer.isActive():
            self._fs_timer.start(self._controls_hide_delay)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith((".srt", ".ass", ".ssa", ".sub", ".vtt", ".txt")):
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith((".srt", ".ass", ".ssa", ".sub", ".vtt", ".txt")):
                self._import_subtitle(path)
                event.acceptProposedAction()

    def _choose_subtitle(self):
        if self._player.duration <= 0 or self._player.is_loading:
            self._room_panel.set_status('请先打开视频，再导入字幕。', '#95724f')
            return
        path, _ = QFileDialog.getOpenFileName(self, '导入外挂字幕', '',
            '字幕文件 (*.srt *.ass *.ssa *.sub *.vtt *.txt)')
        if path:
            self._import_subtitle(path)

    def _import_subtitle(self, path):
        try:
            self._player.load_subtitle(path)
            self._room_panel.set_status('已导入字幕：' + _os.path.basename(path), '#95724f')
            self._room_panel.add_chat('系统', '外挂字幕已在本机加载；右侧可撤销。')
        except Exception:
            self._room_panel.set_status('字幕未能加载，请确认视频已打开、字幕文件格式有效。', '#b36b4a')

    def _undo_subtitle(self):
        try:
            removed = self._player.undo_subtitle()
            self._room_panel.set_status('已撤销最近导入的外挂字幕，原文件保留。' if removed else
                                        '没有可以撤销的手动外挂字幕。', '#95724f')
        except Exception:
            self._room_panel.set_status('字幕移除失败，请稍后重试。', '#b36b4a')

    def closeEvent(self, event):
        self._closing = True
        self._rooms.cancel()
        self._shell.timer.stop()
        self._pip.timer.stop()
        self._pip.hide()
        self._controls._vol_popup.hide()
        self._controls.hide()
        self._controls._vol_hide_timer.stop()
        self._invalidate_quality_request()
        self._fs_timer.stop()
        self._fs_mouse_timer.stop()
        QApplication.instance().removeEventFilter(self)
        self._vid_info_timer.stop()
        self._danmaku.close()
        self._player.stop()
        self._network.stop()
        super().closeEvent(event)
