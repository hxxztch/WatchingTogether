"""Two complete title lines with an ellipsis; never vertically crop a glyph."""
import math
import re
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPainter, QTextLayout, QTextOption, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedTitle(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._update_height()

    def _update_height(self):
        self.setFixedHeight(math.ceil(self.fontMetrics().lineSpacing()) * 2 + 6)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange, QEvent.Polish):
            self._update_height()

    def display_lines(self):
        text = re.sub(r'\s+', ' ', self.text()).strip()
        width = max(1, self.contentsRect().width() - 2)
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        line = layout.createLine()
        if not line.isValid():
            layout.endLayout()
            return []
        line.setLineWidth(width)
        count = line.textLength()
        layout.endLayout()
        # QTextLine offsets count UTF-16 code units, while Python indexes code
        # points. Convert explicitly so emoji don't push the first line outside.
        encoded = text.encode('utf-16-le', errors='replace')
        result = [encoded[:count * 2].decode('utf-16-le').rstrip()]
        remaining = encoded[count * 2:].decode('utf-16-le').lstrip()
        if remaining:
            result.append(self.fontMetrics().elidedText(remaining, Qt.ElideRight, width))
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.WindowText))
        metrics = self.fontMetrics()
        baseline = self.contentsRect().top() + 3 + metrics.ascent()
        for text in self.display_lines():
            painter.drawText(self.contentsRect().left() + 1, baseline, text)
            baseline += metrics.lineSpacing()
