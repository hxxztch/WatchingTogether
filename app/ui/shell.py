"""Warm desktop navigation and home page for the isolated UI preview."""
from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QToolButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QSizePolicy, QProgressBar, QDialog, QListView,
)
from app.version import CLIENT_VERSION, SERVER_VERSION


WARM_STYLE = """
QMainWindow, QDialog { background: #f8f5f1; }
QWidget { color: #3f3731; font-family: 'Microsoft YaHei UI'; font-size: 12px; }
QLabel { background: transparent; }
QFrame#sidebar { background: #f3ece6; border-right: 1px solid #e9e0d8; }
QWidget#workspace, QScrollArea, QScrollArea > QWidget > QWidget { background: #f8f5f1; border: none; }
QFrame#card, QWidget#roomCard { background: #ffffff; border: 1px solid #eee7e0; border-radius: 16px; }
QFrame#hero { background: #f4e8dc; border: 1px solid #eadccc; border-radius: 18px; }
QLabel#eyebrow { color: #aa7657; font-size: 11px; letter-spacing: 2px; }
QLabel#heading { font-size: 25px; font-weight: 600; }
QLabel#heroHeading { font-size: 30px; font-weight: 600; color: #503d30; }
QLabel#subtle { color: #8e8176; }
QLabel#cardTitle, QLabel#panel_title { font-size: 16px; font-weight: 600; color: #493c32; }
QLabel#badge { background: #eee6dd; color: #95724f; border-radius: 9px; padding: 5px 10px; font-size: 11px; }
QLabel#room_label { color: #b86b43; font-size: 18px; font-weight: 600; }
QLabel#time_label { color: #675d54; background: rgba(255, 255, 255, 210); border-radius: 6px; padding: 4px; }
QLineEdit { background: #fcfaf7; border: 1px solid #e3d9cf; border-radius: 7px; padding: 7px 9px; selection-background-color: #d99c76; }
QLineEdit:focus { border: 1px solid #c78258; background: #fff; }
QComboBox { background: #fcfaf7; border: 1px solid #e3d9cf; border-radius: 7px; padding: 7px 9px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: white; color: #3f3731; selection-background-color: #eedbc9; }
QPushButton { background: rgba(255, 255, 255, 205); color: #675547; border: 1px solid rgba(210, 205, 200, 170); border-radius: 7px; padding: 7px 12px; }
QPushButton:hover { background: rgba(255, 255, 255, 240); border-color: #c8b8a9; }
QPushButton:pressed { background: rgba(245, 242, 238, 230); }
QPushButton#primary, QPushButton#create_btn, QPushButton#join_btn, QPushButton#play_btn { background: rgba(255, 255, 255, 215); color: #9b623e; border: 1px solid rgba(198, 172, 147, 180); }
QPushButton#primary:hover, QPushButton#create_btn:hover, QPushButton#join_btn:hover, QPushButton#play_btn:hover { background: rgba(255, 255, 255, 250); }
QPushButton#leave_btn { background: rgba(255, 255, 255, 205); border-color: #e4d2c8; color: #b36b4a; }
QToolButton#nav { border: none; border-radius: 9px; padding: 11px; background: transparent; color: #837367; text-align: left; }
QToolButton#nav:hover { background: #ece1d7; }
QToolButton#nav:checked { background: #e9d6c4; color: #9b5937; font-weight: 600; }
QToolButton#collapse { border: none; border-radius: 6px; background: #eae0d6; padding: 0;
    font-size: 22px; font-weight: 600; }
QListWidget, QListView { background: #faf8f5; border: 1px solid #eee7e0; border-radius: 8px; padding: 6px; }
QListWidget::item, QListView::item { padding: 5px 3px; }
QListWidget::item:selected, QListView::item:selected { background: #eedbc9; color: #66462f; }
QSlider::groove:horizontal { background: #e5dbd0; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #c78b63; border-radius: 2px; }
QSlider::handle:horizontal { background: #b8754c; width: 12px; margin: -4px 0; border-radius: 6px; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #d9cabe; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #fffaf3; color: #634b38; border: 1px solid #dbc8b5; padding: 5px; }
QMessageBox { background: #f8f5f1; }
"""


def line_icon(kind, color="#987a63"):
    """Small resolution-independent navigation glyphs, without icon-font dependencies."""
    pix = QPixmap(48, 48)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(2, 2)
    painter.setPen(QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if kind == "home":
        for x, y in ((4, 4), (14, 4), (4, 14), (14, 14)):
            painter.drawRoundedRect(x, y, 6, 6, 1, 1)
    elif kind == "cinema":
        painter.drawRoundedRect(3, 4, 18, 14, 2, 2)
        painter.drawLine(8, 21, 16, 21)
        painter.drawLine(12, 18, 12, 21)
        painter.drawLine(10, 8, 15, 11)
        painter.drawLine(15, 11, 10, 14)
        painter.drawLine(10, 14, 10, 8)
    elif kind == "profile":
        painter.drawEllipse(3, 3, 18, 18)
        painter.drawEllipse(9, 6, 6, 6)
        painter.drawArc(6, 12, 12, 10, 0, 180 * 16)
    elif kind == "room":
        painter.drawEllipse(8, 3, 8, 8)
        painter.drawArc(4, 12, 16, 12, 0, 180 * 16)
        painter.drawLine(4, 18, 20, 18)
    elif kind == "settings":
        painter.drawEllipse(5, 5, 14, 14)
        painter.drawEllipse(10, 10, 4, 4)
        for start, end in (((12, 1), (12, 5)), ((12, 19), (12, 23)),
                           ((1, 12), (5, 12)), ((19, 12), (23, 12)),
                           ((4, 4), (7, 7)), ((17, 17), (20, 20)),
                           ((4, 20), (7, 17)), ((17, 7), (20, 4))):
            painter.drawLine(*start, *end)
    else:
        painter.drawLine(9, 7, 14, 12)
        painter.drawLine(14, 12, 9, 17)
    painter.end()
    return QIcon(pix)


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def card(title=None):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(14)
    if title:
        layout.addWidget(label(title, "cardTitle"))
    return frame, layout


class DesktopShell(QWidget):
    page_requested = Signal(int)

    def __init__(self, owner, theatre):
        super().__init__(owner)
        self.owner = owner
        self.expanded = False
        self.setObjectName("workspace")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 24, 12, 18)
        side.setSpacing(12)
        brand_row = QHBoxLayout()
        self.logo = QLabel()
        self.logo.setPixmap(owner.windowIcon().pixmap(34, 34))
        self.logo.setFixedSize(40, 40)
        self.logo.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(self.logo)
        self.brand_text = label("超时空会夜机", "cardTitle")
        brand_row.addWidget(self.brand_text)
        side.addLayout(brand_row)
        side.addSpacing(28)
        self.nav_buttons = []
        for index, (text, icon) in enumerate((("首页", "home"), ("播放影厅", "cinema"), ("房间", "room"), ("个人中心", "profile"))):
            button = QToolButton()
            button.setObjectName("nav")
            button.setText(text)
            button.setToolTip(text)
            button.setAccessibleName(text)
            button.setIcon(line_icon(icon))
            button.setIconSize(QSize(22, 22))
            button.setCheckable(True)
            button.setMinimumHeight(46)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, page=index: self.page_requested.emit(page))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch()
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("nav")
        self.settings_button.setText("设置")
        self.settings_button.setToolTip("设置")
        self.settings_button.setAccessibleName("设置")
        self.settings_button.setIcon(line_icon("settings"))
        self.settings_button.setIconSize(QSize(22, 22))
        self.settings_button.setCheckable(True)
        self.settings_button.setMinimumHeight(46)
        self.settings_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_button.clicked.connect(lambda: self.page_requested.emit(4))
        self.nav_buttons.append(self.settings_button)
        side.addWidget(self.settings_button)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("collapse")
        self.collapse_button.setMinimumHeight(34)
        self.collapse_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        side.addWidget(self.collapse_button)
        self.collapse_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.side_note = label("一起看，才好看。\nv" + CLIENT_VERSION, "subtle")
        side.addWidget(self.side_note)
        root.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.pages.addWidget(self._home())
        theatre_page = QWidget()
        theatre_layout = QVBoxLayout(theatre_page)
        theatre_layout.setContentsMargins(24, 24, 24, 24)
        theatre_layout.setSpacing(18)
        self.theatre_header = QWidget()
        heading = QHBoxLayout(self.theatre_header)
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addWidget(label("播放影厅", "heading"))
        heading.addStretch()
        self.theatre_status = label("独自观影也很好", "badge")
        heading.addWidget(self.theatre_status)
        self.members_details = QPushButton('详情')
        self.members_details.setToolTip('查看当前房间成员')
        self.members_details.clicked.connect(self.show_members)
        heading.addWidget(self.members_details)
        theatre_layout.addWidget(self.theatre_header)
        theatre_layout.addWidget(theatre, 1)
        self.pages.addWidget(theatre_page)
        rooms = QScrollArea()
        rooms.setWidgetResizable(True)
        room_page = QWidget()
        room_columns = QHBoxLayout(room_page)
        room_columns.setContentsMargins(24, 24, 24, 24)
        room_columns.addStretch()
        room_cards = QWidget()
        room_cards.setMaximumWidth(840)
        room_columns.addWidget(room_cards, 1)
        room_columns.addStretch()
        room_layout = QVBoxLayout(room_cards)
        room_layout.setContentsMargins(0, 0, 0, 0)
        room_layout.setSpacing(18)
        room_layout.addWidget(owner._room_panel.management, 0, Qt.AlignTop)
        room_layout.addWidget(owner._room_panel.members_card, 0, Qt.AlignTop)
        room_layout.addStretch()
        rooms.setWidget(room_page)
        self.pages.addWidget(rooms)
        from app.ui.profile import ProfilePage
        self.profile = ProfilePage(owner)
        profile_scroll = QScrollArea()
        profile_scroll.setWidgetResizable(True)
        profile_page = QWidget()
        profile_columns = QHBoxLayout(profile_page)
        profile_columns.setContentsMargins(24, 24, 24, 24)
        profile_columns.addStretch()
        profile_cards = QWidget()
        profile_cards.setMaximumWidth(720)
        profile_columns.addWidget(profile_cards, 1)
        profile_columns.addStretch()
        profile_layout = QVBoxLayout(profile_cards)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(18)
        profile_layout.addWidget(self.profile, 0, Qt.AlignTop)
        from app.ui.chat_images import StickerManager
        self.sticker_manager = StickerManager()
        profile_layout.addWidget(self.sticker_manager, 0, Qt.AlignTop)
        profile_layout.addStretch()
        profile_scroll.setWidget(profile_page)
        self.pages.addWidget(profile_scroll)
        from app.ui.settings import SettingsPage
        self.settings = SettingsPage(self)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self.settings)
        self.pages.addWidget(settings_scroll)
        self.settings.update_available.connect(self._show_update_badge)
        root.addWidget(self.pages, 1)
        self._theatre_layout = theatre_layout
        self.set_page(0)
        self._apply_sidebar()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(800)
        self.refresh_status()

    def show_members(self):
        dialog = QDialog(self.owner)
        dialog.setWindowTitle('当前房间成员')
        dialog.resize(320, 300)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('当前房间成员' if self.owner._room_code else '尚未加入房间', 'cardTitle'))
        members = QListView()
        members.setWordWrap(True)
        members.setModel(self.owner._room_panel._member_list.model())
        layout.addWidget(members)
        close = QPushButton('关闭')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()
        dialog.deleteLater()

    def _home(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.setSpacing(22)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("WELCOME HOME", "eyebrow"))
        titles.addWidget(label("首页", "heading"))
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(label("界面预览  /  01", "badge"), alignment=Qt.AlignVCenter)
        layout.addLayout(header)

        columns = QGridLayout()
        columns.setSpacing(20)
        columns.setColumnStretch(0, 3)
        columns.setColumnStretch(1, 2)
        hero, hero_layout = card()
        hero.setObjectName("hero")
        hero.setMinimumHeight(258)
        hero_layout.setSpacing(18)
        hero_layout.addWidget(label("超 时 空 会 夜 机", "eyebrow"))
        hero_layout.addWidget(label("把相聚，留在这一帧。", "heroHeading", True))
        hero_layout.addWidget(label("无论相隔多远，\n一起按下播放，就是同一个夜晚。", "subtle", True))
        hero_layout.addStretch()
        self.enter_button = QPushButton("进入播放影厅   →")
        self.enter_button.setObjectName("primary")
        self.enter_button.setFixedHeight(40)
        self.enter_button.clicked.connect(lambda: self.page_requested.emit(1))
        hero_layout.addWidget(self.enter_button, alignment=Qt.AlignLeft)
        columns.addWidget(hero, 0, 0)

        versions, versions_layout = card("关于这次相聚")
        logo_row = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(self.owner.windowIcon().pixmap(58, 58))
        mark.setFixedSize(66, 66)
        logo_row.addWidget(mark)
        names = QVBoxLayout()
        names.addWidget(label("超时空会夜机", "cardTitle"))
        names.addWidget(label("Watching Together", "subtle"))
        logo_row.addLayout(names)
        logo_row.addStretch()
        versions_layout.addLayout(logo_row)
        for title, version in (("客户端", CLIENT_VERSION), ("配套服务端", SERVER_VERSION)):
            row = QHBoxLayout()
            row.addWidget(label(title, "subtle"))
            row.addStretch()
            row.addWidget(label("v" + version, "badge"))
            versions_layout.addLayout(row)
        columns.addWidget(versions, 0, 1)

        guide, guide_layout = card("从这里开始")
        for number, title, detail in (
            ("01", "走进你的影厅", "连接服务器，创建房间，或输入朋友的房间号。"),
            ("02", "挑一部想看的影片", "打开本地视频或视频链接，每位成员各自准备片源。"),
            ("03", "分享同一段时光", "同步播放与跳转，边看边聊。")
        ):
            row = QHBoxLayout()
            number_label = label(number, "badge")
            number_label.setFixedWidth(42)
            row.addWidget(number_label, alignment=Qt.AlignTop)
            texts = QVBoxLayout()
            texts.addWidget(label(title, "cardTitle"))
            texts.addWidget(label(detail, "subtle", True))
            row.addLayout(texts, 1)
            guide_layout.addLayout(row)
            guide_layout.addSpacing(8)
        columns.addWidget(guide, 1, 0)

        now, now_layout = card("此刻")
        now_layout.addWidget(label("房间状态", "subtle"))
        self.room_status = label("尚未加入房间", "cardTitle", True)
        now_layout.addWidget(self.room_status)
        now_layout.addSpacing(6)
        now_layout.addWidget(label("正在播放", "subtle"))
        from app.ui.elided_title import ElidedTitle
        self.playback_title = ElidedTitle('尚未打开视频')
        self.playback_title.setObjectName('cardTitle')
        now_layout.addWidget(self.playback_title)
        self.playback_status = label("等待一部好影片", "cardTitle", True)
        now_layout.addWidget(self.playback_status)
        now_layout.addStretch()
        now_layout.addWidget(label("切换到首页时，播放中的视频会在小窗继续。", "subtle", True))
        columns.addWidget(now, 1, 1)
        layout.addLayout(columns)

        notices, notices_layout = card()
        notice_header = QHBoxLayout()
        notice_header.addWidget(label("公告与说明", "cardTitle"))
        notice_header.addStretch()
        notice_header.addWidget(label("内容待补充", "badge"))
        notices_layout.addLayout(notice_header)
        notices_layout.addWidget(label("这里将展示使用说明、版本动态和更多消息。", "subtle", True))
        layout.addWidget(notices)
        layout.addStretch()
        layout.addWidget(label("不同的地点，同一段时光。", "subtle"), alignment=Qt.AlignCenter)
        scroll.setWidget(page)
        return scroll

    def set_page(self, index):
        self.pages.setCurrentIndex(index)
        for number, button in enumerate(self.nav_buttons):
            button.setChecked(number == index)

    def _show_update_badge(self, version):
        text = "设置 · 有更新" if version else "设置"
        self.settings_button.setText(text)
        self.settings_button.setToolTip(text)
        self.settings_button.setAccessibleName(text)

    def toggle_sidebar(self):
        self.expanded = not self.expanded
        self._apply_sidebar()

    def _apply_sidebar(self):
        self.sidebar.setFixedWidth(224 if self.expanded else 76)
        self.brand_text.setVisible(self.expanded)
        self.side_note.setVisible(self.expanded)
        for button in self.nav_buttons:
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if self.expanded else Qt.ToolButtonIconOnly)
        self.collapse_button.setText("‹" if self.expanded else "›")
        self.collapse_button.setToolTip("收起侧栏" if self.expanded else "展开侧栏")
        self.collapse_button.setAccessibleName(self.collapse_button.toolTip())

    def fullscreen(self, enabled):
        self.sidebar.setVisible(not enabled)
        self.theatre_header.setVisible(not enabled)
        margin = 0 if enabled else 24
        self._theatre_layout.setContentsMargins(margin, margin, margin, margin)
        self._theatre_layout.setSpacing(0 if enabled else 18)

    def refresh_status(self):
        owner = self.owner
        room = "房间 " + owner._room_code if owner._room_code else "尚未加入房间"
        if owner._room_code and not owner._room_ready:
            room += " · 正在重连"
        if owner._room_ready:
            room += " · " + str(owner._room_panel._member_list.count()) + " 人在线"
        self.room_status.setText(room)
        latency = owner._room_panel._latency
        latency_text = f'{latency:.0f} ms' if owner._room_ready and latency is not None else '—'
        self.theatre_status.setText(room + ' · 延迟 ' + latency_text if owner._room_code else "独自观影也很好")
        player = owner._player
        title = owner._controls._media_title.text()
        self.playback_title.setText(title)
        self.playback_title.setToolTip(title)
        self.playback_status.setText(
            ("播放中" if player.is_playing else "已暂停") + " · " +
            str(int(player.position // 60)).zfill(2) + ":" + str(int(player.position % 60)).zfill(2)
            if player.duration > 0 else "等待一部好影片")
        if hasattr(owner, "_empty_stage"):
            owner._empty_stage.setVisible(not player.is_loading and player.duration <= 0 and
                                          not owner._pip.isVisible())
            if owner._empty_stage.isVisible():
                owner._empty_stage.raise_()


class MiniPlayer(QWidget):
    """Hosts the same native mpv widget; never opens another media stream."""
    return_requested = Signal()

    def __init__(self, owner):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.owner = owner
        self.setWindowTitle("超时空会夜机 · 小窗播放")
        self.setWindowIcon(owner.windowIcon())
        self.setStyleSheet(WARM_STYLE)
        self.setMinimumSize(360, 240)
        self.resize(520, 340)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setStyleSheet('QProgressBar { border: none; background: #e5dbd0; } QProgressBar::chunk { background: #b8754c; }')
        self.body.addWidget(self.progress)
        self.time_label = QLabel('00:00 / 00:00')
        self.time_label.setAlignment(Qt.AlignRight)
        self.time_label.setContentsMargins(8, 3, 8, 2)
        self.body.addWidget(self.time_label)
        toolbar = QWidget()
        toolbar.setObjectName("miniToolbar")
        toolbar.setAttribute(Qt.WA_StyledBackground, True)
        toolbar.setStyleSheet("#miniToolbar { background: #f7f8f9; }")
        buttons = QHBoxLayout(toolbar)
        buttons.setContentsMargins(10, 8, 10, 8)
        self.play = QPushButton("暂停")
        self.play.clicked.connect(owner._on_toggle_play)
        self.mute = QPushButton("静音")
        self.mute.clicked.connect(owner._controls._on_vol_toggle)
        self.restore = QPushButton("返回影厅 ↗")
        self.restore.setObjectName("primary")
        self.restore.clicked.connect(self.return_requested)
        buttons.addWidget(self.play)
        buttons.addWidget(self.mute)
        buttons.addStretch()
        buttons.addWidget(self.restore)
        self.body.addWidget(toolbar)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)

    def refresh(self):
        if self.isVisible():
            from app.timecode import format_timecode
            self.refresh_title()
            player = self.owner._player
            self.progress.setValue(max(0, min(1000, int(player.position / player.duration * 1000))) if player.duration > 0 else 0)
            self.time_label.setText(format_timecode(player.position) + ' / ' + format_timecode(player.duration))
            self.play.setText("暂停" if self.owner._player.is_playing else "播放")
            self.mute.setText("恢复声音" if self.owner._player.volume == 0 else "静音")

    def refresh_title(self):
        title = self.owner._controls._media_title.text()
        self.setWindowTitle(self.fontMetrics().elidedText(title, Qt.ElideRight, max(80, self.width() - 180)))
        self.setToolTip(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_title()

    def closeEvent(self, event):
        event.ignore()
        self.return_requested.emit()
