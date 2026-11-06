from PySide6 import QtGui, QtWidgets


class CodeView(QtWidgets.QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(self.LineWrapMode.NoWrap)
        self.setFont(QtGui.QFont('Monospace', 10))
        self.offsets = {}
        self.spans = {}
        self.highlighted = None
        self.files = None

    def update_sources(self, index):
        self.spans = dict(index.spans)
        if index.files == self.files:
            return
        self.files = dict(index.files)
        lines, offsets = [], {}
        for path, text in index.files.items():
            lines.append('# FILE: ' + path)
            offsets[path] = len(lines)
            lines.extend(text.splitlines())
            lines.append('')
        position = self.verticalScrollBar().value()
        self.setPlainText('\n'.join(lines))
        self.offsets = offsets
        self.verticalScrollBar().setValue(position)
        self.highlight(self.highlighted)

    def highlight(self, identifier):
        self.highlighted = identifier
        span = self.spans.get(identifier)
        if not span:
            self.setExtraSelections([])
            return
        offset = self.offsets[span.path]
        cursor = QtGui.QTextCursor(self.document().findBlockByNumber(offset + span.start - 1))
        cursor.setPosition(self.document().findBlockByNumber(offset + span.end - 1).position(),
                           QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.EndOfBlock,
                            QtGui.QTextCursor.MoveMode.KeepAnchor)
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QtGui.QColor('#284e42'))
        self.setExtraSelections([selection])
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
