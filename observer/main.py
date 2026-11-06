"""SOIL OBSERVER: separate, read-only current-state application."""
import argparse
from pathlib import Path
import sys
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg
from .code_view import CodeView
from .graph_view import GraphView
from .morphology_view import MorphologyView
from .source_index import SourceIndex
from .telemetry_client import TelemetryClient


class Observer(QtWidgets.QMainWindow):
    def __init__(self, root):
        super().__init__()
        self.setWindowTitle('DIGITAL SOIL 0.1 · THE FIRST SEED · OBSERVER')
        self.resize(1150, 950)
        self.index = SourceIndex(root)
        self.client = TelemetryClient(root)
        self.stats = QtWidgets.QLabel('Waiting for plant telemetry…')
        self.stats.setWordWrap(True)
        self.graph = GraphView()
        self.code = CodeView()
        self.morphology = MorphologyView()
        self.wave = pg.PlotWidget(background='#111b20', title='Wave · diagnostic')
        self.spectrum = pg.PlotWidget(background='#111b20', title='Spectrum · diagnostic')
        self.wave_line = self.wave.plot(pen='#64db8b')
        self.spectrum_line = self.spectrum.plot(pen='#c1bf86')
        self.wave.setYRange(-0.16, 0.16)
        self.wave.setMaximumHeight(110)
        self.spectrum.setMaximumHeight(110)
        self.morphology.hovered.connect(self.code.highlight)
        self.morphology.hovered.connect(self.graph.highlight)
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.stats)
        audio = QtWidgets.QHBoxLayout()
        audio.addWidget(self.wave)
        audio.addWidget(self.spectrum)
        layout.addLayout(audio)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        for title, view in [('COMPUTATIONAL BODY', self.graph), ('LIVING SOURCE', self.code),
                            ('CODE MORPHOLOGY · hover a tissue line', self.morphology)]:
            panel = QtWidgets.QWidget()
            box = QtWidgets.QVBoxLayout(panel)
            box.setContentsMargins(0, 3, 0, 0)
            box.addWidget(QtWidgets.QLabel(title))
            box.addWidget(view)
            splitter.addWidget(panel)
        splitter.setSizes([240, 360, 180])
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self.setStyleSheet('QWidget { background: #142127; color: #d4dedb; }'
                           'QPlainTextEdit { background: #101a20; selection-background-color: #365f49; }')
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)
        self.refresh()

    def refresh(self):
        self.client.poll()
        self.index.refresh()
        data = self.client.latest or {}
        nodes = data.get('nodes', []) if self.client.connected else []
        self.code.update_sources(self.index)
        self.graph.update_sources(self.index, nodes)
        self.morphology.update_sources(self.index, nodes)
        if self.client.connected:
            metrics = data.get('metrics', {})
            self.stats.setText(f"LIVE · pid {data['pid']} · age {data['age']:.1f}s · "
                               f"functions / sound nodes {len(nodes)} · code {data['source_bytes']} B · "
                               f"energy {data['energy']:.2f} · resources {data['resources']:.2f} · "
                               f"RMS {metrics.get('rms', 0):.4f} · richness {metrics.get('richness', 0):.3f}\n"
                               f"{data.get('audio', {}).get('status', '')} {data.get('error', '')}")
            self.wave_line.setData(data.get('wave', []))
            self.spectrum_line.setData(data.get('spectrum', []))
        else:
            self.stats.setText('OFFLINE · reading current files · reconnecting automatically · '
                               + (self.index.error or self.client.error))

    def closeEvent(self, event):
        self.timer.stop()
        self.client.close()
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plant', nargs='?', type=Path, default=Path('laboratory/plant_001'))
    args = parser.parse_args(argv)
    app = QtWidgets.QApplication(sys.argv[:1])
    window = Observer(args.plant)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
