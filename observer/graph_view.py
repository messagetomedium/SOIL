import pyqtgraph as pg
from PySide6 import QtGui
from .morphology_view import COLORS


class GraphView(pg.PlotWidget):
    def __init__(self):
        super().__init__(background='#111b20')
        self.hideAxis('bottom')
        self.hideAxis('left')
        self.setMenuEnabled(False)
        self.nodes = []
        self.spans = []
        self.highlighted = ''
        self.scatter = None
        self.setMinimumHeight(160)

    def update_sources(self, index, nodes):
        spans = index.ordered()
        if spans == self.spans and nodes == self.nodes:
            return
        self.spans, self.nodes = spans, nodes
        self.draw()

    def draw(self):
        self.clear()
        metadata = {n['id']: n for n in self.nodes}
        positions = {'core': (0, 0)}
        for i, span in enumerate(self.spans):
            positions[span.id] = (len(span.path.split('/')), -i - 1)
        spots = [{'pos': positions['core'], 'data': 'core', 'brush': '#c3cdd2', 'size': 13}]
        core = pg.TextItem('stable kernel · seed.py', color='#c3cdd2', anchor=(0, 1))
        core.setPos(0, 0)
        self.addItem(core)
        for span in self.spans:
            node = metadata.get(span.id, {})
            pos = positions[span.id]
            for parent in node.get('parents') or ['core']:
                if parent in positions:
                    x, y = positions[parent]
                    self.plot([x, pos[0]], [y, pos[1]], pen=pg.mkPen('#45606b', width=1))
                    # Arrow identifies computation direction, toward the receiving tissue.
                    arrow = pg.ArrowItem(pos=pos, angle=90 if pos[0] == x else 135,
                                         headLen=7, brush='#45606b', pen=None)
                    self.addItem(arrow)
            color = '#f4f5be' if span.id == self.highlighted else COLORS.get(node.get('state'), '#8d9ca4')
            spots.append({'pos': pos, 'data': span.id, 'brush': color,
                          'size': 19 if span.id == self.highlighted else 12})
            label = pg.TextItem(f"{node.get('kind', 'tissue')} {span.id[:6]} · {span.path}",
                                color=color, anchor=(0, 1))
            label.setPos(*pos)
            self.addItem(label)
        self.scatter = pg.ScatterPlotItem(spots=spots, pen=pg.mkPen('#1c2e36'))
        self.addItem(self.scatter)
        self.autoRange(padding=0.15)

    def highlight(self, identifier):
        if self.highlighted != identifier:
            self.highlighted = identifier
            self.draw()
