import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PySide6 import QtCore, QtTest, QtWidgets
from observer.main import Observer
from observer.source_index import SourceIndex
from observer.telemetry_client import TelemetryClient
from scripts.prepare_lab import prepare
from seed.seed import Telemetry


def receive(client, server=None, data=None):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        message = client.poll()
        if server:
            server.publish(data)
        message = client.poll() or message
        if message:
            return message
        time.sleep(0.01)
    raise AssertionError('no current telemetry received')


def test_source_index_and_real_mouse_hover_synchronize_views(plant):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    identifier = plant.grow()
    plant.grow('filter', inline=False)
    view = Observer(plant.tree.root)
    view.timer.stop()
    view.show()
    app.processEvents()
    try:
        assert len(view.index.spans) == 2
        target = next(i for i, span in enumerate(view.morphology.rows) if span.id == identifier)
        point = view.morphology.row_rect(target).center().toPoint()
        QtTest.QTest.mouseMove(view.morphology, point)
        app.processEvents()
        assert view.code.highlighted == identifier
        assert view.graph.highlighted == identifier
        assert 'def tissue_' + identifier in view.code.textCursor().selectedText()
        plant.mark_dying(identifier)
        plant.age += plant.genome.decay_seconds
        assert plant.prune(identifier)
        view.refresh()
        assert identifier not in view.index.spans
        assert 'def tissue_' + identifier not in view.code.toPlainText()
        assert all(s.id != identifier for s in view.morphology.rows)
    finally:
        view.close()
        app.processEvents()


def test_socket_one_way_reconnect_and_no_observer_commands(plant):
    with tempfile.TemporaryDirectory(prefix='ds-') as short:
        server = Telemetry(short)
        client = TelemetryClient(short)
        try:
            msg = receive(client, server, plant.telemetry())
            assert msg['version'] == 1
            client.close()
            plant.grow()
            msg = receive(client, server, plant.telemetry())
            assert len(msg['nodes']) == 1
            assert not hasattr(client, 'send')
        finally:
            client.close()
            server.close()


def test_live_seed_is_independent_process_and_observer_reopens():
    with tempfile.TemporaryDirectory(prefix='ds-live-') as temp:
        root = prepare(Path(temp) / 'laboratory')
        (root.parent / 'environment.json').write_text('{"nutrients": 8}')
        proc = subprocess.Popen([sys.executable, str(root / 'seed.py'), '--no-audio',
                                 '--random-seed', '17', '--duration', '15'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        client = TelemetryClient(root)
        try:
            deadline = time.monotonic() + 10
            msg = None
            while time.monotonic() < deadline:
                msg = client.poll() or msg
                if msg and len(msg['nodes']) >= 2 and msg['counters']['calls'] > 0:
                    break
                if proc.poll() is not None:
                    raise AssertionError(proc.communicate())
                time.sleep(0.05)
            assert msg and len(msg['nodes']) >= 2
            assert msg['pid'] == proc.pid != os.getpid()
            previous_age = msg['age']
            client.close()
            assert proc.poll() is None
            reopened = receive(client)
            assert reopened['pid'] == proc.pid
            assert reopened['age'] >= previous_age
            index = SourceIndex(root)
            index.refresh()
            assert set(index.spans) == {n['id'] for n in reopened['nodes']}
        finally:
            client.close()
            if proc.poll() is None:
                proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            assert proc.returncode == 0, (stdout, stderr)
