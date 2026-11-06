"""Reconnecting, receive-only protocol v1 client. No plant imports."""
import errno
import json
from pathlib import Path
import socket
import time


class TelemetryClient:
    def __init__(self, root):
        self.path = str(Path(root) / 'telemetry.sock')
        self.socket = None
        self.buffer = b''
        self.latest = None
        self.connected = False
        self.retry_at = 0
        self.error = ''

    def close(self):
        if self.socket:
            self.socket.close()
        self.socket = None
        self.buffer = b''
        self.connected = False

    def poll(self):
        if self.socket is None:
            if time.monotonic() < self.retry_at:
                return None
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.setblocking(False)
            code = sock.connect_ex(self.path)
            if code not in (0, errno.EINPROGRESS, errno.EAGAIN):
                sock.close()
                self.retry_at = time.monotonic() + 0.5
                return None
            self.socket = sock
        fresh = None
        try:
            for _ in range(4):
                try:
                    chunk = self.socket.recv(32768)
                except BlockingIOError:
                    break
                if not chunk:
                    raise ConnectionError('plant disconnected')
                self.buffer += chunk
                if len(self.buffer) > 131072:
                    raise ValueError('telemetry buffer limit')
                while b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n', 1)
                    msg = json.loads(line)
                    if (msg.get('protocol') != 'digital-soil' or msg.get('version') != 1
                            or not isinstance(msg.get('nodes'), list) or len(msg['nodes']) > 48
                            or len(msg.get('wave', [])) > 256 or len(msg.get('spectrum', [])) > 64):
                        raise ValueError('unsupported telemetry')
                    self.latest = fresh = msg
                    self.connected = True
                    self.error = ''
        except (OSError, ValueError, AttributeError) as exc:
            self.error = str(exc)
            self.close()
            self.retry_at = time.monotonic() + 0.5
        return fresh
