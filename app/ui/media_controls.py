"""Vector media buttons and the right-hand video information card."""
from functools import lru_cache
from PySide6.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QSlider, QLineEdit, QStackedWidget,
    QComboBox, QMenu, QHBoxLayout, QVBoxLayout, QSizePolicy,
)


@lru_cache(maxsize=16)
def media_icon(name):
    """Paint dark, crisp glyphs instead of font-dependent emoji."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(64 / 24, 64 / 24)
    ink = QColor('#29343d')
    painter.setPen(QPen(ink, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(ink)
    if name == 'play':
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)]))
    elif name == 'pause':
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(6, 5, 4, 14), 1.2, 1.2)
        painter.drawRoundedRect(QRectF(14, 5, 4, 14), 1.2, 1.2)
    elif name == 'stop':
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name in ('volume', 'volume-low', 'muted'):
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(3, 9), QPointF(7, 9), QPointF(12, 5),
                                      QPointF(12, 19), QPointF(7, 15), QPointF(3, 15)]))
        painter.setPen(QPen(ink, 1.8, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        if name == 'muted':
            painter.drawLine(QPointF(16, 9), QPointF(21, 15))
            painter.drawLine(QPointF(21, 9), QPointF(16, 15))
        else:
            painter.drawArc(QRectF(10, 8, 8, 8), -50 * 16, 100 * 16)
            if name == 'volume':
                painter.drawArc(QRectF(7, 4, 15, 16), -50 * 16, 100 * 16)
    elif name == 'fullscreen':
        for x, y, dx, dy in ((5, 5, 5, 5), (19, 5, -5, 5), (5, 19, 5, -5), (19, 19, -5, -5)):
            painter.drawLine(x, y, x + dx, y)
            painter.drawLine(x, y, x, y + dy)
    painter.end()
    return QIcon(pixmap)


BUTTON_STYLE = """
QPushButton { background: rgba(255,255,255,225); border: 1px solid rgba(255,255,255,170);
    border-radius: 11px; padding: 0; }
QPushButton:hover { background: rgba(255,255,255,250); border-color: #bdc5cb; }
QPushButton:pressed { background: rgba(218,225,230,235); }
QPushButton:focus { border: 2px solid #9caebc; }
"""


def build_controls(self, menu_style):
    layout = QHBoxLayout(self)
    layout.setContentsMargins(14, 10, 14, 12)
    layout.setSpacing(10)

    def icon_button(icon, title):
        button = QPushButton()
        button.setFixedSize(38, 38)
        button.setIcon(media_icon(icon))
        button.setIconSize(QSize(24, 24))
        button.setToolTip(title)
        button.setAccessibleName(title)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(BUTTON_STYLE)
        return button

    self._play_btn = icon_button('play', '播放 / 暂停')
    self._play_btn.clicked.connect(self._on_toggle_play)
    layout.addWidget(self._play_btn)
    self._stop_btn = icon_button('stop', '停止播放')
    self._stop_btn.clicked.connect(self.stop_requested)
    layout.addWidget(self._stop_btn)

    self._time_label = QLabel('00:00 / 00:00')
    self._time_label.setObjectName('time_label')
    self._time_label.setAlignment(Qt.AlignCenter)
    self._time_label.setStyleSheet('background: rgba(255,255,255,225); color: #34404a; border-radius: 10px; padding: 0 3px; font-size: 12px;')
    self._time_label.setCursor(Qt.PointingHandCursor)
    self._time_label.setToolTip('点击输入时间跳转（秒数、分:秒、时:分:秒）')
    self._time_label.installEventFilter(self)
    self._time_editor = QLineEdit()
    self._time_editor.setAlignment(Qt.AlignCenter)
    self._time_editor.setMaxLength(12)
    self._time_editor.setAccessibleName('跳转到时间')
    self._time_editor.setToolTip('回车跳转，Esc取消')
    self._time_editor.returnPressed.connect(self._submit_time)
    self._time_editor.installEventFilter(self)
    self._time_stack = QStackedWidget()
    self._time_stack.setFixedSize(125, 38)
    self._time_stack.addWidget(self._time_label)
    self._time_stack.addWidget(self._time_editor)
    layout.addWidget(self._time_stack)
    self._seek_bar = QSlider(Qt.Horizontal)
    self._seek_bar.setRange(0, 1000)
    self._seek_bar.setMinimumWidth(60)
    self._seek_bar.setStyleSheet('''
        QSlider::groove:horizontal { background: rgba(235,239,242,180); height: 5px; border-radius: 2px; }
        QSlider::sub-page:horizontal { background: #bf8964; border-radius: 2px; }
        QSlider::handle:horizontal { background: #fff; border: 2px solid #bf8964; width: 12px; margin: -5px 0; border-radius: 7px; }
    ''')
    self._seek_bar.sliderPressed.connect(self._on_seek_press)
    self._seek_bar.sliderReleased.connect(self._on_seek_release)
    self._seek_bar.installEventFilter(self)
    layout.addWidget(self._seek_bar, 1)
    self._vol_btn = icon_button('volume', '音量: 80，点击静音')
    self._vol_btn.clicked.connect(self._on_vol_toggle)
    self._vol_btn.installEventFilter(self)
    layout.addWidget(self._vol_btn)
    self._fs_btn = icon_button('fullscreen', '切换全屏')
    self._fs_btn.clicked.connect(self.fullscreen_toggled)
    layout.addWidget(self._fs_btn)

    self._vol_popup = QFrame(self.window())
    self._vol_popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
    self._vol_popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
    self._vol_popup.setStyleSheet('QFrame { background: #fafcfd; border: 1px solid #d1d8de; border-radius: 11px; }')
    self._vol_popup.setFixedSize(38, 120)
    self._vol_popup.installEventFilter(self)
    popup_layout = QVBoxLayout(self._vol_popup)
    popup_layout.setContentsMargins(10, 12, 10, 12)
    self._vol_slider_v = QSlider(Qt.Vertical)
    self._vol_slider_v.setRange(0, 100)
    self._vol_slider_v.setValue(80)
    self._vol_slider_v.setStyleSheet('''
        QSlider::groove:vertical { background: #dbe1e6; width: 4px; border-radius: 2px; }
        QSlider::sub-page:vertical { background: #dbe1e6; }
        QSlider::add-page:vertical { background: #ad8062; }
        QSlider::handle:vertical { background: #fff; border: 2px solid #ad8062; height: 10px; margin: 0 -5px; border-radius: 6px; }
    ''')
    self._vol_slider_v.valueChanged.connect(self._on_volume)
    popup_layout.addWidget(self._vol_slider_v)
    self._vol_hide_timer = QTimer(self)
    self._vol_hide_timer.timeout.connect(self._vol_hide_check)

    # A separate panel is installed above the room/chat controls by MainWindow.
    self.media_panel = QWidget()
    self.media_panel.setObjectName('mediaInfo')
    panel = QVBoxLayout(self.media_panel)
    panel.setContentsMargins(18, 18, 18, 14)
    panel.setSpacing(10)
    self._media_source = QLabel('当前影片')
    self._media_source.setObjectName('eyebrow')
    panel.addWidget(self._media_source)
    self._media_title = QLabel('尚未打开视频')
    self._media_title.setTextFormat(Qt.PlainText)
    self._media_title.setWordWrap(True)
    self._media_title.setFixedHeight(44)
    self._media_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    self._media_title.setStyleSheet('font-size: 15px; font-weight: 600; color: #3d4145;')
    panel.addWidget(self._media_title)
    quality_row = QHBoxLayout()
    self._quality_label = QLabel('画质: —')
    self._quality_label.setStyleSheet('color: #7d858d; font-size: 11px;')
    quality_row.addWidget(self._quality_label, 1)
    self._quality_combo = QComboBox()
    self._quality_combo.setMinimumWidth(88)
    self._quality_combo.setMaximumWidth(120)
    self._quality_combo.setStyleSheet('QComboBox { background: #faf9f7; border: 1px solid #dedbd7; border-radius: 6px; padding: 5px; } QComboBox QAbstractItemView { background: white; color: #37404a; selection-background-color: #ede4db; }')
    self._quality_combo.currentTextChanged.connect(self._on_quality_change)
    self._quality_combo.hide()
    quality_row.addWidget(self._quality_combo)
    panel.addLayout(quality_row)
    actions = QHBoxLayout()
    self._open_btn = QPushButton('打开视频')
    open_menu = QMenu(self.media_panel)
    open_menu.setStyleSheet(menu_style)
    open_menu.addAction('打开本地视频…', self._on_open_file)
    open_menu.addAction('打开网页视频…', self._on_url_dialog)
    self._open_btn.setMenu(open_menu)
    actions.addWidget(self._open_btn)
    self._more_btn = QPushButton('其他功能')
    self._more_menu = QMenu(self.media_panel)
    self._more_menu.setStyleSheet(menu_style)
    self._more_btn.setMenu(self._more_menu)
    actions.addWidget(self._more_btn)
    self._rebuild_more_menu()
    panel.addLayout(actions)
    chat_row = QHBoxLayout()
    self._danmaku_input = QLineEdit()
    self._danmaku_input.setMaxLength(4000)
    self._danmaku_input.setPlaceholderText('发个弹幕…')
    self._danmaku_input.returnPressed.connect(self._on_danmaku)
    chat_row.addWidget(self._danmaku_input, 1)
    self._danmaku_btn = QPushButton('发送')
    self._danmaku_btn.clicked.connect(self._on_danmaku)
    chat_row.addWidget(self._danmaku_btn)
    panel.addLayout(chat_row)
