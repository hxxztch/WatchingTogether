"""Chinese edit menus, including dynamically created dialogs and combo editors."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit


def edit_menu(widget):
    menu = widget.createStandardContextMenu()
    translations = {'Undo': '撤销', 'Redo': '重做', 'Cut': '剪切', 'Copy': '复制',
                    'Paste': '粘贴', 'Delete': '删除', 'Select All': '全选'}
    for action in menu.actions():
        title, *shortcut = action.text().split('\t', 1)
        title = title.replace('&', '').strip()
        if title in translations:
            action.setText(translations[title] + ('\t' + shortcut[0] if shortcut else ''))
    return menu


class ChineseEditMenus(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.ContextMenu:
            return False
        editor = obj
        if isinstance(obj.parent(), (QTextEdit, QPlainTextEdit)):
            editor = obj.parent()
        if isinstance(editor, (QLineEdit, QTextEdit, QPlainTextEdit)):
            menu = edit_menu(editor)
            menu.exec(event.globalPos())
            menu.deleteLater()
            return True
        return False


def install_edit_menus():
    app = QApplication.instance()
    if not hasattr(app, '_chinese_edit_menus'):
        app._chinese_edit_menus = ChineseEditMenus(app)
        app.installEventFilter(app._chinese_edit_menus)
