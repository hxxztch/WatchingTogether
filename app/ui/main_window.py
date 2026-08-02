"""Main application window."""
import os as _os, sys, logging, subprocess, shutil, re, json, urllib.request
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
import base64
import hashlib
from PySide6.QtGui import QIcon, QPixmap

from app.player import MpvWidget
from app.network import NetworkClient
from app.ui.room_panel import RoomPanel
from app.ui.controls import ControlsBar
from app.ui.danmaku import DanmakuOverlay

logging.basicConfig(level=logging.INFO)

if getattr(sys, 'frozen', False):
    _ASSETS = _os.path.join(sys._MEIPASS, "assets")
else:
    _ASSETS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "assets")

STYLE = """
QMainWindow { background-color: #1a1a1a; }
QWidget { color: #e0e0e0; }
QLabel { color: #d0d0d0; }
QLineEdit {
    background-color: #2a2a2a; color: #e0e0e0;
    border: 1px solid #555; border-radius: 3px; padding: 4px 8px;
}
QPushButton {
    background-color: #444; color: #fff; border: none;
    border-radius: 3px; padding: 6px 12px; font-size: 12px;
}
QPushButton:hover { background-color: #555; }
QPushButton#create_btn { background-color: #2196F3; }
QPushButton#create_btn:hover { background-color: #1976D2; }
QPushButton#join_btn { background-color: #4CAF50; }
QPushButton#join_btn:hover { background-color: #388E3C; }
QPushButton#leave_btn { background-color: #f44336; }
QPushButton#leave_btn:hover { background-color: #D32F2F; }
QPushButton#play_btn { background-color: #2196F3; font-size: 16px; padding: 4px; }
QPushButton#play_btn:hover { background-color: #1976D2; }
QLabel#panel_title { font-size: 18px; font-weight: bold; color: #fff; }
QLabel#room_label { font-size: 15px; font-weight: bold; color: #FFD54F; }
QLabel#status_label { color: #999; font-size: 11px; }
QLabel#time_label { color: #aaa; font-size: 11px; min-width: 100px; }
QListWidget {
    background-color: #2a2a2a; color: #d0d0d0;
    border: 1px solid #444; border-radius: 3px;
}
QSlider::groove:horizontal {
    background: #444; height: 4px; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #2196F3; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}
QMessageBox {
    background-color: #2d2d2d; color: #e0e0e0;
}
QMessageBox QLabel {
    color: #e0e0e0; font-size: 13px;
}
QMessageBox QPushButton {
    background-color: #555; color: #fff;
    padding: 6px 20px; border-radius: 3px; min-width: 70px;
}
"""


class MainWindow(QMainWindow):
    _hotkey = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("超时空会夜机")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)
        self.setStyleSheet(STYLE)
        _pix = QPixmap()
        _pix.loadFromData(base64.b64decode("""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"""))
        if not _pix.isNull():
            self.setWindowIcon(QIcon(_pix))

        self._room_code = ""
        self._bili_info = None  # {bvid, avid, cid, headers, quality_map, current_qn}
        self._my_name = ""
        self._syncing = False

        self._room_panel = RoomPanel()
        self._room_panel.create_requested.connect(self._on_create_room)
        self._room_panel.join_requested.connect(self._on_join_room)
        self._room_panel.leave_requested.connect(self._on_leave_room)
        self._room_panel.chat_message.connect(self._on_chat)
        self._room_panel.refresh_connection.connect(self._reconnect_network)

        self._controls = ControlsBar()
        self._controls.danmaku_sent.connect(self._on_chat)
        self._controls.play_toggled.connect(self._on_toggle_play)
        self._controls.seek_requested.connect(self._on_seek)
        self._controls.volume_changed.connect(self._player_volume)
        self._controls.file_selected.connect(self._on_load_file)
        self._controls.url_submitted.connect(self._on_load_url)
        self._controls.stop_requested.connect(self._on_stop)
        self._controls.audio_selected.connect(self._on_audio_select)
        self._controls.quality_selected.connect(self._on_quality_change)
        self._controls.page_changed.connect(self._on_page_change)
        self._controls.fullscreen_toggled.connect(self._on_fullscreen)

        self._network = NetworkClient(self._room_panel.get_server_url())
        self._network.signals.connected.connect(self._on_connected)
        self._network.signals.disconnected.connect(self._on_disconnected)
        self._network.signals.message_received.connect(self._on_message)
        self._network.signals.error_occurred.connect(self._on_net_error)
        self._network.start()

        self._player = MpvWidget()
        self._player.position_changed.connect(self._on_position)
        self._player.playback_started.connect(lambda: self._controls.set_playing(True))
        self._player.playback_paused.connect(lambda: self._controls.set_playing(False))

        self._danmaku = DanmakuOverlay(self)
        self._danmaku.track(self._player)

        self._hotkey.connect(self._on_hotkey)

        center = QWidget()
        hlayout = QHBoxLayout(center)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)

        left = QWidget()
        left.setStyleSheet("background-color: #1e1e1e; border-right: 1px solid #333;")
        l2 = QVBoxLayout(left)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.addWidget(self._room_panel)

        right = QWidget()
        r2 = QVBoxLayout(right)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(0)
        r2.addWidget(self._player, stretch=1)
        # Controls float over the player instead of pushing it up
        self._controls.setParent(right)
        self._player_container = right

        s = QSplitter(Qt.Horizontal)
        s.addWidget(left)
        s.addWidget(right)
        s.setStretchFactor(0, 0)
        s.setStretchFactor(1, 1)
        s.setSizes([260, 1020])
        self._splitter = s
        hlayout.addWidget(s)
        self.setCentralWidget(center)

        self._left_panel = left

        from PySide6.QtCore import QTimer as _QTimer
        self._fs_timer = _QTimer()
        self._fs_timer.setSingleShot(True)
        self._fs_timer.timeout.connect(self._hide_fs_controls)
        self._fs_mouse_timer = _QTimer()
        self._fs_mouse_timer.timeout.connect(self._check_fs_mouse)
        self._fs_mouse_timer.start(200)

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _reconnect_network(self, url: str):
        """Stop current connection and reconnect to a new server URL."""
        self._room_panel.set_status("正在连接...", "#FFD54F")
        if hasattr(self, '_network') and self._network:
            self._network.stop()
            self._network.wait(3000)
            self._network.deleteLater()
        self._network = NetworkClient(url)
        self._vid_info_timer = QTimer()
        self._vid_info_timer.timeout.connect(self._poll_video_info)
        self._vid_info_timer.start(2000)  # check every 2s
        self._network.signals.connected.connect(self._on_connected)
        self._network.signals.disconnected.connect(self._on_disconnected)
        self._network.signals.message_received.connect(self._on_message)
        self._network.signals.error_occurred.connect(self._on_net_error)
        self._network.start()

    def _player_volume(self, vol):
        if hasattr(self, "_player"):
            self._player.set_volume(vol)

    def _on_stop(self):
        self._bili_info = None
        self._controls.set_video_quality("", None)
        self._player.stop()

    def _on_audio_select(self, track_id):
        self._player.set_audio_track(track_id)

    def _refresh_audio_tracks(self):
        QTimer.singleShot(500, lambda: self._do_refresh_audio())

    def _do_refresh_audio(self):
        tracks = self._player.get_audio_tracks()
        if tracks:
            self._controls.set_audio_tracks(tracks)

    def _on_connected(self):
        self._room_panel.set_status("已连接", "#4CAF50")
        self._room_panel.update_server_label(self._room_panel.get_server_url())
    def _on_disconnected(self):
        self._room_panel.set_status("未连接", "#f44336")
        self._room_panel.set_in_room(False)
        self._room_code = ""
        self._bili_info = None  # {bvid, avid, cid, headers, quality_map, current_qn}

    def _on_net_error(self, err): self._room_panel.set_status(err, "#f44336")

    def _on_message(self, msg):
        mtype = msg.get("type", "")
        self._syncing = True
        try:
            if mtype == "room_created":
                self._room_code = msg["room"]
                self._room_panel.set_in_room(True, self._room_code, msg.get("members", [self._my_name]))
                self._room_panel.set_status("Room " + self._room_code, "#FFD54F")
            elif mtype == "room_joined":
                self._room_code = msg["room"]
                self._my_name = msg.get("name", "")
                self._room_panel.set_in_room(True, self._room_code, msg.get("members", []))
                self._room_panel.set_status("已加入房间 " + self._room_code, "#4CAF50")
                st = msg.get("state", {})
                pos = st.get("position", 0)
                if pos > 0:
                    self._player.seek(pos)
                if st.get("playing"):
                    self._player.play()
            elif mtype == "left_room":
                self._room_code = ""
                self._room_panel.set_in_room(False)
                self._room_panel.set_status("已离开房间", "#999")
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
            elif mtype == "seek_rel":
                self._player.seek_relative(msg.get("delta", 0))
            elif mtype == "seek":
                pos = msg.get("position", 0)
                self._player.seek(pos)
            elif mtype == "chat":
                self._room_panel.add_chat(msg.get("from", ""), msg.get("message", "")); self._danmaku.show_danmaku(msg.get("from", ""), msg.get("message", ""))
            elif mtype == "sync_state":
                st = msg.get("state", {})
                pos = st.get("position", 0)
                if pos > 0:
                    self._player.seek(pos)
                if st.get("playing"):
                    self._player.play()
            elif mtype == "error":
                QMessageBox.warning(self, "错误", msg.get("message", ""))
        finally:
            self._syncing = False

    
    _wbi_mix_key = None
    _wbi_expires = 0

    def _get_wbi_mix_key(self):
        """Fetch and cache WBI mixin key for API signing."""
        import time
        now = int(time.time())
        if self._wbi_mix_key and now < self._wbi_expires:
            return self._wbi_mix_key
        try:
            req = urllib.request.Request(
                "https://api.bilibili.com/x/web-interface/nav",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                         "Referer": "https://www.bilibili.com/"})
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
            wi = resp["data"]["wbi_img"]
            ik = wi["img_url"].split("/")[-1].split(".")[0]
            sk = wi["sub_url"].split("/")[-1].split(".")[0]
            self._wbi_mix_key = (ik + sk)[:32]
            self._wbi_expires = now + 3600  # cache 1 hour
            return self._wbi_mix_key
        except Exception:
            return None

    def _wbi_sign_url(self, base_url, params):
        """Sign URL params with WBI and return full URL string."""
        import time
        mix_key = self._get_wbi_mix_key()
        if not mix_key:
            return None
        params["wts"] = str(int(time.time()))
        sorted_keys = sorted(params.keys())
        qs = "&".join(f"{k}={params[k]}" for k in sorted_keys)
        w_rid = hashlib.md5((qs + mix_key).encode()).hexdigest()
        params["w_rid"] = w_rid
        return base_url + "?" + "&".join(f"{k}={params[k]}" for k in params)

    def _resolve_bilibili_wbi(self, avid, cid, bvid, headers, qn=120):
        """Fetch playurl using WBI-signed API. Returns (play_data, quality_map, actual_qn)."""
        params = {
            "avid": str(avid), "cid": str(cid), "qn": str(qn),
            "platform": "web", "otype": "json", "fourk": "1", "fnval": "4048",
        }
        url = self._wbi_sign_url("https://api.bilibili.com/x/player/wbi/playurl", params)
        if not url:
            return None, {}, 80
        req = urllib.request.Request(url, headers=headers)
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
        if resp.get("code") != 0:
            return None, {}, 80
        pd = resp["data"]
        actual_qn = pd.get("quality", qn)
        accept_quality = pd.get("accept_quality", [actual_qn])
        accept_desc = pd.get("accept_description", [])
        quality_map = {}
        for i, q in enumerate(accept_quality):
            desc = accept_desc[i] if i < len(accept_desc) else str(q) + "P"
            quality_map[str(q)] = desc
        if not quality_map and "support_formats" in pd:
            for fmt in pd["support_formats"]:
                q = fmt.get("quality")
                d = fmt.get("new_description", "") or fmt.get("display_desc", "") or (str(q) + "P")
                if q is not None:
                    quality_map[str(q)] = d
        return pd, quality_map, actual_qn

    def _on_create_room(self, name):
        self._my_name = name
        self._network.send({"type": "create_room", "name": name})

    def _on_join_room(self, room, name):
        self._my_name = name
        self._network.send({"type": "join_room", "room": room, "name": name})

    def _on_leave_room(self):
        self._network.send({"type": "leave_room"})
        self._room_code = ""
        self._bili_info = None  # {bvid, avid, cid, headers, quality_map, current_qn}

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
        self._player.seek(pos)
        if self._room_code:
            self._network.send({"type": "seek", "position": pos})

    def _on_load_file(self, path):
        self._bili_info = None
        self._controls.set_video_quality("", None)
        self._controls.set_pages([], 0)
        self._controls.set_audio_tracks([], -1)
        self._player.load(path)
        self._player.play()
        self._refresh_audio_tracks()
        if self._room_code:
            self._network.send({"type": "load", "path": path})

    def _resolve_bilibili(self, url):
        """Resolve Bilibili video URL. Returns dict or None."""
        bvid_match = re.search(r'BV[a-zA-Z0-9]{10}', url)
        if not bvid_match:
            return None
        bvid = bvid_match.group()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        try:
            # Step 1: get basic video info
            req = urllib.request.Request(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", headers=headers)
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            if resp.get("code") != 0:
                return None
            data = resp["data"]
            avid, cid = data["aid"], data["cid"]
            pages = data.get("pages", [])
            page_list = [(p.get("page", i+1), p.get("part", "P" + str(i+1))) for i, p in enumerate(pages)]

            # Step 2: get quality list from WBI (gives full list: 1080P/480P/etc)
            wbi_pd, wbi_quality_map, wbi_actual_qn = self._resolve_bilibili_wbi(avid, cid, bvid, headers)

            # Step 3: get FLV URL from old API (always works, single file)
            play_url = f"https://api.bilibili.com/x/player/playurl?avid={avid}&cid={cid}&qn=120&platform=html5&otype=json&fnval=1"
            play_req = urllib.request.Request(play_url, headers=headers)
            play_resp = json.loads(urllib.request.urlopen(play_req, timeout=15).read().decode("utf-8"))
            if play_resp.get("code") != 0:
                return None
            pd = play_resp["data"]

            # Fallback quality map from old API if WBI failed
            quality_map = wbi_quality_map
            actual_qn = wbi_actual_qn
            if not quality_map:
                old_aq = pd.get("accept_quality", [pd.get("quality", 80)])
                old_ad = pd.get("accept_description", [])
                for i, q in enumerate(old_aq):
                    desc = old_ad[i] if i < len(old_ad) else str(q) + "P"
                    quality_map[str(q)] = desc
                actual_qn = pd.get("quality", 80)

            # Get playable URL
            if "durl" in pd and pd["durl"]:
                video_url = pd["durl"][0]["url"]
            else:
                return None

            current_desc = quality_map.get(str(actual_qn), str(actual_qn) + "P")

            # Store for quality switching
            self._bili_info = {
                "bvid": bvid, "avid": avid, "cid": cid,
                "headers": headers, "quality_map": quality_map,
                "current_qn": actual_qn,
                "pages": page_list,
            }

            return {
                "video_url": video_url,
                "quality_map": quality_map,
                "current_qn": str(actual_qn),
                "current_desc": current_desc,
                "pages": page_list,
            }
        except:
            pass
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
                    [ytdlp, '-f', 'best[ext=mp4]/best', '-g', '--no-warnings', '--no-check-certificate', url],
                    capture_output=True, text=True, timeout=60,
                    startupinfo=si, creationflags=flags
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip().split(chr(10))[0]
            except Exception as e:
                pass
        # Try Python module (fallback)
        try:
            from yt_dlp import YoutubeDL
            with YoutubeDL({'quiet': True, 'no_warnings': True, 'format': 'best'}) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    u = info.get('url') or (info.get('requested_formats') or [{}])[0].get('url')
                    return u
        except:
            pass
        return None

    def _on_load_url(self, url):
        self._controls.set_audio_tracks([], -1)
        bili = self._resolve_bilibili(url)
        if bili:
            self._room_panel.set_status("B站解析成功: " + bili.get("current_desc", ""), "#4CAF50")
            if bili.get("audio_url"):
                self._player.load_with_audio(bili["video_url"], bili["audio_url"])
            else:
                self._player.load(bili["video_url"])
            # Set quality dropdown + page selector
            qmap = bili.get("quality_map", {})
            current_desc = bili.get("current_desc", "")
            qualities = list(qmap.values())
            self._controls.set_video_quality(current_desc, qualities)
            pages = bili.get("pages", [])
            if pages and len(pages) > 1:
                self._controls.set_pages(pages, 0)
            else:
                self._controls.set_pages([], 0)
        else:
            resolved = self._resolve_ytdlp(url)
            if resolved:
                self._room_panel.set_status("解析成功", "#4CAF50")
                url = resolved
            self._player.load(url)
            self._bili_info = None
            self._controls.set_video_quality("", None)
            self._controls.set_pages([], 0)
        self._player.play()
        self._refresh_audio_tracks()
        if self._room_code:
            self._network.send({"type": "load", "path": url})

    def _poll_video_info(self):
        """Periodically check video resolution."""
        if self._bili_info:
            label = self._player.get_quality_label()
            if label:
                self._controls._quality_label.setText(label)
            return
        label = self._player.get_quality_label()
        if label:
            self._controls.set_video_quality(label, None)

    def _on_quality_change(self, quality_text):
        """Switch B站 video quality."""
        if not self._bili_info or not quality_text:
            self._room_panel.set_status("画质切换: 无B站信息或空文本", "#f44336")
            return
        bi = self._bili_info
        qn = None
        for q, desc in bi["quality_map"].items():
            if desc == quality_text:
                qn = int(q)
                break
        if qn is None:
            self._room_panel.set_status("画质切换: 未找到qn", "#f44336")
            return
        if qn == bi["current_qn"]:
            self._room_panel.set_status("已是最佳画质", "#FFD54F")
            return

        try:
            # Use WBI DASH API for quality switching (supports 1080P+ etc)
            pd, _, new_qn = self._resolve_bilibili_wbi(bi["avid"], bi["cid"], bi.get("bvid", ""), bi["headers"], qn)
            if pd is None:
                self._room_panel.set_status("画质切换失败: API错误", "#f44336")
                return
            if "dash" not in pd:
                self._room_panel.set_status("画质切换失败: 无DASH流", "#f44336")
                return

            v = pd["dash"].get("video", [{}])[0]
            a = pd["dash"].get("audio", [{}])[0]
            video_url = v.get("base_url", "")
            audio_url = a.get("base_url", "")
            if not video_url:
                self._room_panel.set_status("画质切换失败: 无视频URL", "#f44336")
                return

            was_playing = self._player.is_playing

            if audio_url:
                # load_dash now captures position internally after pausing
                self._player.load_dash(video_url, audio_url, was_playing)
            else:
                self._player.loadfile(video_url)
                self._player.pause = not was_playing

            bi["current_qn"] = new_qn
            actual_desc = bi["quality_map"].get(str(new_qn), quality_text)
            self._controls._quality_label.setText(actual_desc)
            idx = self._controls._quality_combo.findText(actual_desc)
            if idx >= 0:
                self._controls._quality_combo.blockSignals(True)
                self._controls._quality_combo.setCurrentIndex(idx)
                self._controls._quality_combo.blockSignals(False)
            self._room_panel.set_status("画质切换到: " + actual_desc, "#4CAF50")
        except Exception as e:
            self._room_panel.set_status("画质切换失败: " + str(e)[:30], "#f44336")
            import traceback
            logging.error(f"Quality switch error: {e}\n{traceback.format_exc()}")

    def _on_page_change(self, page_idx):
        """Switch to a different episode/page of a B\u7ad9 video."""
        bi = self._bili_info
        if not bi or not bi.get("pages"):
            return
        pages = bi["pages"]
        if page_idx < 0 or page_idx >= len(pages):
            return
        page_num, page_title = pages[page_idx - 1]
        new_cid = None
        try:
            headers = bi["headers"]
            req = urllib.request.Request(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bi['bvid']}", headers=headers)
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            if resp.get("code") == 0:
                all_pages = resp["data"].get("pages", [])
                for p in all_pages:
                    if p.get("page") == page_num:
                        new_cid = p.get("cid")
                        break
        except Exception:
            pass
        if not new_cid:
            self._room_panel.set_status("\u5206P\u5207\u6362\u5931\u8D25", "#f44336")
            return
        bi["cid"] = new_cid
        switched_url = ""
        try:
            pd, quality_map, actual_qn = self._resolve_bilibili_wbi(
                bi["avid"], new_cid, bi["bvid"], headers, bi["current_qn"])
            if pd is None:
                self._room_panel.set_status("\u5206P\u5207\u6362\u5931\u8D25", "#f44336")
                return
            if "dash" in pd:
                v = pd["dash"].get("video", [{}])[0]
                a = pd["dash"].get("audio", [{}])[0]
                video_url = v.get("base_url", "")
                audio_url = a.get("base_url", "")
                switched_url = video_url
                if video_url:
                    self._player.load_dash(video_url, audio_url, True, 0)
                    self._player.play()
            else:
                play_url = f'https://api.bilibili.com/x/player/playurl?avid={bi["avid"]}&cid={new_cid}&qn=120&platform=html5&otype=json&fnval=1'
                play_req = urllib.request.Request(play_url, headers=headers)
                play_resp = json.loads(urllib.request.urlopen(play_req, timeout=15).read().decode("utf-8"))
                if play_resp.get("code") == 0 and "durl" in play_resp["data"]:
                    self._player.load(play_resp["data"]["durl"][0]["url"])
                    self._player.play()
            bi["current_qn"] = actual_qn
            current_desc = bi["quality_map"].get(str(actual_qn), str(actual_qn) + "P")
            self._controls.set_video_quality(current_desc, list(bi["quality_map"].values()))
            self._room_panel.set_status("\u5207\u6362\u5230: " + page_title, "#4CAF50")
            if self._room_code and switched_url:
                self._network.send({"type": "load", "path": switched_url})
        except Exception as e:
            self._room_panel.set_status("\u5206P\u5207\u6362\u5931\u8D25: " + str(e)[:30], "#f44336")
            logging.error(f"Page switch error: {e}")

    def _on_position(self, pos):
        self._controls.set_position(pos, self._player.duration)

    def _on_hotkey(self, action):
        if action == "left":
            self._player.seek_relative(-2.5)
            if self._room_code:
                self._network.send({"type": "seek_rel", "delta": -2.5})
        elif action == "right":
            self._player.seek_relative(2.5)
            if self._room_code:
                self._network.send({"type": "seek_rel", "delta": 2.5})
        elif action == "esc" and self.isFullScreen():
            self._exit_fullscreen()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            # Don't steal keys from text input widgets
            from PySide6.QtWidgets import QLineEdit
            if QApplication.focusWidget() is not None and isinstance(QApplication.focusWidget(), QLineEdit):
                return super().eventFilter(obj, event)
            k = event.key()
            if k == Qt.Key_Left:
                self._player.seek_relative(-2.5)
                if self._room_code:
                    self._network.send({"type": "seek_rel", "delta": -2.5})
                return True
            elif k == Qt.Key_Right:
                self._player.seek_relative(2.5)
                if self._room_code:
                    self._network.send({"type": "seek_rel", "delta": 2.5})
                return True
            elif k == Qt.Key_Space:
                self._on_toggle_play()
                return True
            elif k == Qt.Key_Escape and self.isFullScreen():
                self._exit_fullscreen()
                return True
        if obj is self._player and event.type() == QEvent.Resize:
            self._danmaku.track(self._player)
        if hasattr(self, '_player_container') and obj is self._player_container and event.type() == QEvent.Resize:
            self._position_controls()
        return super().eventFilter(obj, event)

    def _on_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._left_panel.hide()
        self._controls.hide()
        self._fs_timer.stop()
        # Save splitter sizes and give all space to player
        self._saved_sizes = self._splitter.sizes()
        self._splitter.setSizes([0, self._splitter.width()])
        self.showFullScreen()
        self._position_controls()
        # Force mpv to fill the entire window (fixes black bar at top on Windows)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._player.update())

    def _exit_fullscreen(self):
        self._left_panel.show()
        self._controls.show()
        self._fs_timer.stop()
        self.showNormal()
        self._position_controls()
        # Restore splitter sizes
        if hasattr(self, '_saved_sizes'):
            self._splitter.setSizes(self._saved_sizes)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._player.update())

    def _position_controls(self):
        """Position controls bar at the bottom of its parent, floating over video."""
        if self._controls.parent():
            pw = self._controls.parent().width()
            ph = self._controls.parent().height()
            ch = self._controls.sizeHint().height()
            self._controls.setGeometry(0, ph - ch, pw, ch)
            self._controls.raise_()

    def _hide_fs_controls(self):
        if self.isFullScreen():
            self._controls.hide()

    def _check_fs_mouse(self):
        if not self.isFullScreen():
            return
        from PySide6.QtGui import QCursor
        pos = QCursor.pos()
        geo = self.geometry()
        rel_y = pos.y() - geo.y()
        if rel_y > geo.height() - 60:
            self._controls.show(); self._controls.raise_()
            self._position_controls()
            self._fs_timer.start(3000)

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
                self._player.load_subtitle(path)
                self._room_panel.add_chat("系统", "字幕: " + path.split("/")[-1].split("\\")[-1])
                self._danmaku.show_danmaku("字幕", "已加载")

    def closeEvent(self, event):
        self._vid_info_timer.stop()
        self._danmaku.close()
        self._player.stop()
        self._network.stop()
        super().closeEvent(event)