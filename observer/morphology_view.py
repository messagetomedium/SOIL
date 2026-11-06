from PySide6 import QtCore, QtGui, QtWidgets

COLORS = {'new': '#64db8b', 'stable': '#8d9ca4', 'dying': '#ef655e'}


class MorphologyView(QtWidgets.QWidget):
    hovered = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(110)
        self.rows = []
        self.states = {}
        self.selected = ''

    def update_sources(self, index, nodes):
        self.rows = index.ordered()
        self.states = {n['id']: n.get('state', 'stable') for n in nodes}
        self.update()

    def row_rect(self, index):
        height = max(1.0, (self.height() - 12) / max(1, len(self.rows)))
        return QtCore.QRectF(10, 6 + index * height, min(230, self.width() * 0.35), max(1, height - 2))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor('#111b20'))
        if not self.rows:
            painter.setPen(QtGui.QColor('#8d9ca4'))
            painter.drawText(16, 28, 'No grown tissue — waiting for germination')
        for i, span in enumerate(self.rows):
            rect = self.row_rect(i)
            color = '#e8f2c2' if span.id == self.selected else COLORS.get(self.states.get(span.id), '#8d9ca4')
            painter.fillRect(rect, QtGui.QColor(color))
            if rect.height() >= 13:
                painter.setPen(QtGui.QColor('#c3cdd2'))
                painter.drawText(QtCore.QPointF(rect.right() + 12, rect.center().y() + 4),
                                 f'{span.path}:{span.start}–{span.end} · {span.id}')

    def mouseMoveEvent(self, event):
        for i, span in enumerate(self.rows):
            if self.row_rect(i).contains(event.position()):
                self.selected = span.id
                self.hovered.emit(span.id)
                self.setToolTip(f'{span.path}:{span.start}–{span.end}')
                self.update()
                return
        self.selected = ''
        self.hovered.emit('')
        self.update()

    def leaveEvent(self, event):
        self.selected = ''
        self.hovered.emit('')
        self.update()
