#!/usr/bin/env python3
"""Digital Soil 0.1. Standalone organism; copy into a private laboratory first."""
from __future__ import annotations

import argparse
import ast
from collections import deque
from dataclasses import asdict, dataclass, field
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import signal
import socket
import stat
import time
import uuid

import numpy as np

START = '# <soil:' + 'growth>'
END = '# </soil:' + 'growth>'


@dataclass(frozen=True)
class Genome:
    """Inherited construction rules; acquired Node changes never modify these."""
    growth_chance: float = 0.72
    mutation_chance: float = 0.22
    branching: float = 0.55
    sensitivity: float = 1.0
    growth_cost: float = 2.4
    maintenance: float = 0.12
    processing_cost: float = 0.025
    germination_energy: float = 4.0
    initial_frequency: float = 165.0
    max_nodes: int = 24
    max_depth: int = 4
    max_files: int = 64
    max_source_bytes: int = 262144
    write_interval: float = 0.4
    decay_seconds: float = 2.0


class SafeTree:
    """Linux dir-fd operations: no traversal, no symlink following, atomic replace.

    Root and all traversed directories are held open. Even a concurrent rename
    cannot redirect a write through a substituted symlink outside the tree.
    The lab must still be private: this is not a sandbox for hostile local users.
    """
    def __init__(self, root):
        path = Path(root).absolute()
        if path != path.resolve():
            raise ValueError('plant root must not contain symlinks')
        self.root = path
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _parent(self, name, create=False):
        if not isinstance(name, str) or name.startswith('/'):
            raise ValueError('relative plant path required')
        parts = name.split('/')
        if any(p in ('', '.', '..') or p.startswith('.') for p in parts):
            raise ValueError('unsafe plant path')
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _regular(fd, name, missing=False):
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing:
                return
            raise
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('only private regular files may be used')

    def read(self, name, limit=524288):
        fd, leaf = self._parent(name)
        try:
            self._regular(fd, leaf)
            f = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(f, 'rb') as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError('file exceeds read limit')
            return data.decode('utf-8')
        finally:
            os.close(fd)

    def write(self, name, text):
        fd, leaf = self._parent(name, create=True)
        temp = 'tmp_' + uuid.uuid4().hex
        try:
            self._regular(fd, leaf, missing=True)
            f = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=fd)
            with os.fdopen(f, 'w', encoding='utf-8') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, leaf, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)

    def remove(self, name):
        fd, leaf = self._parent(name)
        try:
            self._regular(fd, leaf)
            os.unlink(leaf, dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)
        # Remove empty branch directories only; never remove the root.
        parent = name.split('/')[:-1]
        while parent:
            directory = '/'.join(parent)
            fd, leaf = self._parent(directory)
            try:
                os.rmdir(leaf, dir_fd=fd)
            except OSError:
                break
            finally:
                os.close(fd)
            parent.pop()

    def sources(self):
        result = []
        def visit(fd, prefix, depth):
            if depth > 5:
                raise ValueError('plant directory depth exceeded')
            for name in os.listdir(fd):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError('symlink in plant tree')
                rel = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        visit(child, rel + '/', depth + 1)
                    finally:
                        os.close(child)
                elif name.endswith('.py'):
                    result.append(rel)
                if len(result) > 64:
                    raise ValueError('too many source files')
        visit(self.fd, '', 0)
        return sorted(result)


_ALLOWED = {ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign,
            ast.Return, ast.BinOp, ast.UnaryOp, ast.Call, ast.Attribute, ast.Name,
            ast.Load, ast.Store, ast.Constant, ast.Subscript, ast.Add, ast.Sub,
            ast.Mult, ast.Div, ast.USub, ast.UAdd}
_NP = {'sin', 'cos', 'tanh', 'roll', 'maximum', 'abs'}


def compile_tissue(source, identifier):
    """Validate the closed grammar, then compile in a capability-free namespace.

    Not a general Python sandbox. No external code strings are accepted by CLI
    or telemetry. Only the organism's bounded construction grammar uses this.
    """
    if len(source) > 4096:
        raise ValueError('tissue too large')
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('one function required')
    func = tree.body[0]
    if (func.name != 'tissue_' + identifier or func.decorator_list or func.returns
            or [a.arg for a in func.args.args] != ['t', 'x', 'z']
            or func.args.defaults or func.args.kwonlyargs or func.args.posonlyargs
            or func.args.vararg or func.args.kwarg):
        raise ValueError('invalid tissue signature')
    if any(a.annotation for a in func.args.args):
        raise ValueError('annotations forbidden')
    names = {'np', 't', 'x', 'z', 'y', 'd'}
    walked = list(ast.walk(tree))
    if len(walked) > 220:
        raise ValueError('tissue expression budget exceeded')
    for node in walked:
        if type(node) not in _ALLOWED:
            raise ValueError('forbidden construct: ' + type(node).__name__)
        if isinstance(node, ast.FunctionDef) and node is not func:
            raise ValueError('nested functions forbidden')
        if isinstance(node, ast.Name) and node.id not in names:
            raise ValueError('forbidden name')
        if isinstance(node, ast.Constant):
            if not (type(node.value) in (int, float) and math.isfinite(node.value)
                    and abs(node.value) <= 48000) and node.value != 'last':
                raise ValueError('invalid literal')
        if isinstance(node, ast.Attribute):
            if not (isinstance(node.value, ast.Name) and
                    ((node.value.id == 'np' and node.attr in _NP)
                     or (node.value.id == 'z' and node.attr == 'get'))):
                raise ValueError('forbidden attribute')
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Attribute) or node.keywords):
            raise ValueError('forbidden call')
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, (ast.Name, ast.Subscript)):
                    raise ValueError('invalid assignment target')
                if isinstance(target, ast.Name) and target.id not in {'y', 'd'}:
                    raise ValueError('invalid assignment')
                if isinstance(target, ast.Subscript) and not (
                    isinstance(target.value, ast.Name) and target.value.id in {'d', 'z'}):
                    raise ValueError('invalid subscript assignment')
    scope = {'__builtins__': {}, 'np': np}
    exec(compile(tree, '<grown:' + identifier + '>', 'exec'), scope)
    return scope[func.name]


@dataclass
class Node:
    id: str
    kind: str
    path: str
    parents: list[str]
    source: str
    born: float
    revision: int = 0
    state: str = 'new'
    dying_since: float | None = None
    function: object = field(default=None, repr=False)
    memory: dict = field(default_factory=dict, repr=False)
    activity: float = 0.0

    def record(self):
        return {k: getattr(self, k) for k in ('id', 'kind', 'path', 'parents', 'born',
                'revision', 'state', 'dying_since')} | {
                    'sha256': hashlib.sha256(self.source.encode()).hexdigest()}


class Plant:
    def __init__(self, root, environment, *, rng_seed=None, genome=None, sample_rate=24000):
        self.tree = SafeTree(root)
        self.environment = Path(environment)
        self.genome = genome or Genome()
        g = self.genome
        if not (1 <= g.max_nodes <= 48 and 1 <= g.max_depth <= 4 and
                2 <= g.max_files <= 64 and 1 <= g.max_source_bytes <= 524288):
            raise ValueError('genome exceeds hard limits')
        self.rng = random.Random(rng_seed)
        self.sample_rate = sample_rate
        self.sample_index = 0
        self.age = 0.0
        self.energy = 3.0
        self.resources = 0.0
        self.nodes = {}
        self.last_write = -math.inf
        self.error = ''
        self.metrics = {'rms': 0.0, 'richness': 0.0, 'processing_seconds': 0.0}
        self.wave = np.zeros(256, dtype=np.float32)
        self.spectrum = np.zeros(64, dtype=np.float32)
        self.previous = 0.0
        self.dc_x = self.dc_y = 0.0
        self.tail = np.zeros(240, dtype=np.float32)
        self.transition = False
        self.counters = {'growth': 0, 'mutation': 0, 'pruned': 0, 'calls': 0}
        # Single writer, but no subordinate runtime process.
        fd, leaf = self.tree._parent('plant.lock')
        try:
            self.tree._regular(fd, leaf, missing=True)
            self.lock = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            source = self.tree.read('seed.py')
            if source.count('\n' + START + '\n') != 1 or source.count('\n' + END + '\n') != 1:
                raise ValueError('missing growth region')
            self.prefix, rest = source.split('\n' + START + '\n')
            _, self.suffix = rest.split('\n' + END + '\n')
            self._restore()
        except BaseException:
            self.close()
            raise

    def close(self):
        if getattr(self, 'lock', None) is not None:
            os.close(self.lock)
            self.lock = None
        self.tree.close()

    def _restore(self):
        try:
            body = json.loads(self.tree.read('body.json'))
        except FileNotFoundError:
            return
        if body.get('version') != 1 or len(body['nodes']) > self.genome.max_nodes:
            raise ValueError('invalid body snapshot')
        seed_source = self.tree.read('seed.py')
        for rec in body['nodes']:
            identifier = rec['id']
            if len(identifier) != 12 or any(c not in '0123456789abcdef' for c in identifier):
                raise ValueError('invalid tissue identifier')
            text = seed_source if rec['path'] == 'seed.py' else self.tree.read(rec['path'])
            syntax = ast.parse(text)
            funcs = [n for n in syntax.body if isinstance(n, ast.FunctionDef)
                     and n.name == 'tissue_' + identifier]
            if len(funcs) != 1:
                raise ValueError('body/source mismatch')
            source = ast.get_source_segment(text, funcs[0]) + '\n'
            if hashlib.sha256(source.encode()).hexdigest() != rec.pop('sha256'):
                raise ValueError('tissue checksum mismatch')
            if any(p not in self.nodes for p in rec['parents']):
                raise ValueError('body is not a DAG')
            node = Node(**rec, source=source, function=compile_tissue(source, identifier))
            self.nodes[identifier] = node
        self.age = float(body['age'])
        self.energy = float(body['energy'])
        self.sample_index = int(body['sample_index'])

    def _seed_source(self, nodes):
        grown = '\n'.join(n.source for n in nodes.values() if n.path == 'seed.py')
        return self.prefix + '\n' + START + '\n' + grown + '\n' + END + '\n' + self.suffix

    def _commit(self, nodes, path, content):
        """Compile/check first; publish registry only after successful disk writes."""
        if time.monotonic() - self.last_write < self.genome.write_interval:
            return False
        current = self.tree.sources()
        seed_source = self._seed_source(nodes)
        size = len(seed_source.encode()) + sum(len(n.source.encode()) for n in nodes.values()
                                                  if n.path != 'seed.py')
        if size > self.genome.max_source_bytes:
            raise ValueError('source byte budget exceeded')
        if len(current) + (path not in current) > self.genome.max_files:
            raise ValueError('file budget exceeded')
        if path == 'seed.py':
            content = seed_source
            compile(content, 'seed.py', 'exec')
        old = None
        try:
            old = self.tree.read(path)
        except FileNotFoundError:
            pass
        snapshot = json.dumps({'version': 1, 'age': self.age, 'energy': self.energy,
                               'sample_index': self.sample_index,
                               'nodes': [n.record() for n in nodes.values()]}, indent=2)
        try:
            if content is None:
                self.tree.remove(path)
            else:
                self.tree.write(path, content)
            self.tree.write('body.json', snapshot)
        except BaseException:
            # Keep the previous executable structure on ordinary I/O failures.
            if old is None:
                try:
                    self.tree.remove(path)
                except FileNotFoundError:
                    pass
            else:
                self.tree.write(path, old)
            raise
        self.nodes = nodes
        self.last_write = time.monotonic()
        self.transition = True
        return True

    def _construct(self, identifier, kind):
        """Compose bounded operations. No catalogue of prebuilt adult modules."""
        f = self.genome.initial_frequency * self.rng.uniform(0.5, 2.8)
        a, b = self.rng.uniform(0.12, 0.8), self.rng.uniform(0.08, 0.65)
        if kind == 'oscillator':
            base = f'np.sin(t * {2 * math.pi * f:.8f})'
            harmonic = self.rng.randint(2, 6)
            if not self.nodes or self.rng.random() < 0.5:
                expr = base
            else:
                expr = f'({base} + {b:.6f} * np.sin(t * {2 * math.pi * f * harmonic:.8f}))'
            lines = [f'y = {expr} * 0.18']
        elif kind == 'pulser':
            op = self.rng.choice(['np.maximum', 'np.abs'])
            wave = f'np.sin(t * {self.rng.uniform(1.2, 18):.7f})'
            envelope = f'{op}(0.0, {wave})' if op == 'np.maximum' else f'{op}({wave})'
            lines = [f'y = x * ({a:.6f} + {1-a:.6f} * {envelope})']
        elif kind == 'resonator':
            if self.rng.random() < 0.5:
                lines = [f'y = x + {b:.6f} * np.sin(x * {self.rng.uniform(2, 8):.6f})']
            else:
                lines = [f'y = x * (1.0 + {b:.6f} * np.cos(t * {f:.7f}))']
        elif kind == 'filter':
            # Stateful one-sample FIR: low-pass or high-pass, continuous at block edges.
            sign = self.rng.choice(['+', '-'])
            lines = ['d = np.roll(x, 1)', "d[0] = z.get('last', 0.0)",
                     "z['last'] = x[-1]", f'y = {a:.6f} * x {sign} {1-a:.6f} * d']
        else:
            raise ValueError('unknown tissue kind')
        return f'def tissue_{identifier}(t, x, z):\n' + ''.join('    ' + l + '\n' for l in lines) + '    return y\n'

    def grow(self, kind=None, inline=None):
        if len(self.nodes) >= self.genome.max_nodes or self.energy < self.genome.growth_cost:
            return False
        identifier = f'{self.rng.getrandbits(48):012x}'
        while identifier in self.nodes:
            identifier = f'{self.rng.getrandbits(48):012x}'
        kind = kind or ('oscillator' if not self.nodes else self.rng.choice(
            ['oscillator', 'pulser', 'resonator', 'filter']))
        if not self.nodes:
            kind = 'oscillator'
        active = [n for n in self.nodes.values() if n.state != 'dying']
        parents = []
        if kind != 'oscillator':
            if not active:
                return False
            parents = [n.id for n in self.rng.sample(active, min(len(active),
                        2 if self.rng.random() < self.genome.branching else 1))]
        if inline is None:
            inline = not self.nodes or self.rng.random() < 0.2
        if inline:
            path = 'seed.py'
        else:
            branch = 'branches'
            if active and self.rng.random() < self.genome.branching:
                ancestor = self.rng.choice(active).path
                if ancestor != 'seed.py':
                    candidate = str(Path(ancestor).parent)
                    if len(Path(candidate).parts) < self.genome.max_depth:
                        branch = candidate
            path = f'{branch}/b_{identifier}/tissue.py'
        source = self._construct(identifier, kind)
        node = Node(identifier, kind, path, parents, source, self.age,
                    function=compile_tissue(source, identifier))
        if self._commit(self.nodes | {identifier: node}, path, source):
            self.energy -= self.genome.growth_cost
            self.counters['growth'] += 1
            return identifier
        return False

    def mutate(self, identifier=None, *, structural=None):
        candidates = [n for n in self.nodes.values() if n.state != 'dying']
        if not candidates or self.energy < 0.8:
            return False
        old = self.nodes[identifier] if identifier else self.rng.choice(candidates)
        if old.state == 'dying':
            return False
        source = self._construct(old.id, old.kind)
        parents = list(old.parents)
        if structural is None:
            structural = self.rng.random() < 0.5
        if structural and old.kind != 'oscillator':
            earlier = []
            for n in self.nodes.values():
                if n.id == old.id:
                    break
                if n.state != 'dying':
                    earlier.append(n.id)
            options = [p for p in earlier if p not in parents]
            if options:
                parents.append(self.rng.choice(options))
            elif len(parents) > 1:
                parents.pop(self.rng.randrange(len(parents)))
            if len(parents) > 3:
                parents = self.rng.sample(parents, 3)
        node = Node(old.id, old.kind, old.path, parents, source, old.born,
                    old.revision + 1, 'new', function=compile_tissue(source, old.id))
        if self._commit(self.nodes | {old.id: node}, old.path, source):
            self.energy -= 0.8
            self.counters['mutation'] += 1
            return True
        return False

    def mark_dying(self, identifier):
        node = self.nodes[identifier]
        node.state = 'dying'
        node.dying_since = self.age

    def prune(self, identifier):
        old = self.nodes[identifier]
        if old.state != 'dying' or self.age - old.dying_since < self.genome.decay_seconds:
            return False
        nodes = {}
        for n in self.nodes.values():
            if n.id != identifier:
                # Reconnect downstream tissue to surviving predecessors; no cycles.
                parents = list(dict.fromkeys(p for p in n.parents if p != identifier))
                if identifier in n.parents:
                    parents += [p for p in old.parents if p not in parents and p in self.nodes
                                and self.nodes[p].state != 'dying']
                nodes[n.id] = Node(n.id, n.kind, n.path, parents, n.source, n.born,
                                   n.revision, n.state, n.dying_since, n.function,
                                   dict(n.memory), n.activity)
        content = '' if old.path == 'seed.py' else None
        if self._commit(nodes, old.path, content):
            self.counters['pruned'] += 1
            return True
        return False

    def sense(self, metrics):
        """Feedback boundary: a future acoustic input can supply the same metrics."""
        self.metrics.update(metrics)

    def step(self, dt=0.5):
        if not 0 < dt <= 5:
            raise ValueError('bounded metabolic timestep required')
        self.age += dt
        try:
            if self.environment.is_symlink():
                raise ValueError('environment symlink rejected')
            with self.environment.open('rb') as f:
                data = json.loads(f.read(4097))
            nutrients = float(data.get('nutrients', 0))
            if not math.isfinite(nutrients):
                raise ValueError('invalid resources')
            self.resources = max(0.0, min(8.0, nutrients))
            self.error = ''
        except (OSError, ValueError, TypeError, AttributeError):
            self.resources = 0.0
            self.error = 'environment unavailable or invalid; conserving energy'
        demand = 0.25 + len(self.nodes) * self.genome.maintenance
        demand += self.genome.processing_cost * sum(n.activity > 0.001 for n in self.nodes.values())
        demand += min(1.0, self.metrics['processing_seconds'] * 10)
        self.energy = max(0.0, min(24.0, self.energy + (self.resources - demand) * dt))
        for node in list(self.nodes.values()):
            if node.state == 'new' and self.age - node.born > 3 and node.revision == 0:
                node.state = 'stable'
            elif node.state == 'new' and node.revision and self.age - getattr(self, '_mutation_age', 0) > 3:
                node.state = 'stable'
            if node.state == 'dying':
                if self.prune(node.id):
                    return
        # Stress, complexity, and observed activity drive senescence; never a timetable.
        if self.nodes and self.energy < self.genome.germination_energy:
            living = [n for n in self.nodes.values() if n.state != 'dying']
            if living:
                weakest = min(living, key=lambda n: n.activity + self.rng.random() * 0.03)
                self.mark_dying(weakest.id)
            return
        surplus = max(0.0, self.energy - self.genome.germination_energy) / 20
        complexity = len(self.nodes) / self.genome.max_nodes
        richness = self.metrics['richness']
        probability = min(0.95, self.genome.growth_chance * (0.3 + surplus) *
                          (1 - complexity) * (1.2 - 0.3 * richness))
        if self.energy >= self.genome.germination_energy and self.rng.random() < probability:
            self.grow()
        elif self.nodes and self.rng.random() < self.genome.mutation_chance * (0.4 + surplus):
            if self.mutate():
                self._mutation_age = self.age
        elif len(self.nodes) > 3 and self.rng.random() < complexity * 0.035 * self.genome.sensitivity:
            candidates = [n for n in self.nodes.values() if n.state != 'dying']
            if candidates:
                self.mark_dying(min(candidates, key=lambda n: n.activity).id)

    def render(self, frames=480):
        if not 1 <= frames <= 4096:
            raise ValueError('audio block limit')
        started = time.perf_counter()
        t = (self.sample_index + np.arange(frames, dtype=np.float64)) / self.sample_rate
        self.sample_index += frames
        zero = np.zeros(frames, dtype=np.float64)
        values = {}
        for n in self.nodes.values():
            x = sum((values[p] for p in n.parents if p in values), start=zero.copy())
            if n.parents:
                x /= len(n.parents)
            try:
                with np.errstate(all='ignore'):
                    y = np.asarray(n.function(t, x, n.memory), dtype=np.float64)
                if y.shape != (frames,):
                    raise ValueError('invalid tissue output shape')
                y = np.clip(np.nan_to_num(y, nan=0, posinf=0, neginf=0), -2.0, 2.0)
            except (ArithmeticError, ValueError, TypeError):
                y = zero.copy()
                self.error = 'invalid tissue output: ' + n.id
            values[n.id] = y
            n.activity = float(np.sqrt(np.mean(y * y)))
            self.counters['calls'] += 1
        consumed = {p for n in self.nodes.values() for p in n.parents}
        sinks = [values[n] for n in values if n not in consumed]
        raw = sum(sinks, start=zero.copy()) / max(1, len(sinks))
        if self.transition:
            count = min(frames, len(self.tail))
            fade = np.linspace(0, 1, count)
            raw[:count] = self.tail[-count:] * (1 - fade) + raw[:count] * fade
            self.transition = False
        self.tail = raw[-min(frames, 240):].copy()
        # DC blocker with state across blocks, soft limiter, conservative gain,
        # final slew limit (also limits first sample after a structural swap).
        output = np.empty(frames, dtype=np.float32)
        for i, v in enumerate(raw):
            dc = float(v) - self.dc_x + 0.995 * self.dc_y
            self.dc_x, self.dc_y = float(v), dc
            target = 0.16 * math.tanh(dc)
            self.previous += max(-0.015, min(0.015, target - self.previous))
            output[i] = self.previous
        rms = float(np.sqrt(np.mean(output * output)))
        spec = abs(np.fft.rfft(output * np.hanning(frames)))
        total = float(spec.sum())
        richness = float(np.exp(-np.sum((spec / total) * np.log(spec / total + 1e-12))) / len(spec)) if total > 1e-9 else 0.0
        self.sense({'rms': rms, 'richness': richness,
                    'processing_seconds': time.perf_counter() - started})
        self.wave = output[np.linspace(0, frames - 1, min(256, frames)).astype(int)]
        self.spectrum = np.interp(np.linspace(0, len(spec)-1, 64), np.arange(len(spec)), spec).astype(np.float32)
        return output

    def telemetry(self, audio=None):
        return {'protocol': 'digital-soil', 'version': 1, 'pid': os.getpid(),
                'age': self.age, 'energy': self.energy, 'resources': self.resources,
                'nodes': [n.record() | {'activity': n.activity} for n in self.nodes.values()],
                'source_bytes': sum(len(self.tree.read(p).encode()) for p in self.tree.sources()),
                'metrics': self.metrics, 'wave': self.wave.tolist(), 'spectrum': self.spectrum.tolist(),
                'counters': dict(self.counters), 'error': self.error, 'audio': audio or {}}


class Telemetry:
    """Bounded one-way NDJSON stream. No command parser, no inbound reads."""
    def __init__(self, root):
        self.path = Path(root) / 'telemetry.sock'
        if len(os.fsencode(self.path)) > 100:
            raise ValueError('Unix socket path too long')
        if self.path.exists() or self.path.is_symlink():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise ValueError('refusing to replace non-socket')
            self.path.unlink()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.server.listen(4)
        self.server.setblocking(False)
        self.clients = {}

    def publish(self, data):
        while True:
            try:
                conn, _ = self.server.accept()
            except BlockingIOError:
                break
            conn.setblocking(False)
            if len(self.clients) >= 4:
                conn.close()
            else:
                self.clients[conn] = b''
        payload = (json.dumps(data, allow_nan=False, separators=(',', ':')) + '\n').encode()
        for conn in list(self.clients):
            pending = self.clients[conn] + payload
            try:
                if len(pending) > 131072:
                    raise ConnectionError('slow observer')
                count = conn.send(pending)
                self.clients[conn] = pending[count:]
            except BlockingIOError:
                self.clients[conn] = pending
            except OSError:
                conn.close()
                del self.clients[conn]

    def close(self):
        for conn in self.clients:
            conn.close()
        self.server.close()
        self.path.unlink(missing_ok=True)


class AudioOutput:
    """Producer queue. Callback only copies bounded prepared blocks; no I/O/locks."""
    def __init__(self, sample_rate, blocksize, enabled=True):
        self.queue = deque(maxlen=6)
        self.stream = None
        self.status = 'buffer only (audio disabled)'
        self.underflows = 0
        self.blocksize = blocksize
        if enabled:
            try:
                import sounddevice as sd
                self.stream = sd.OutputStream(samplerate=sample_rate, blocksize=blocksize,
                                              channels=1, dtype='float32', callback=self.callback)
                self.stream.start()
                self.status = 'device streaming'
            except Exception as exc:
                # Backends also raise sounddevice.PortAudioError, which is not
                # an OSError. Device failure must never stop the organism.
                if self.stream is not None:
                    self.stream.close()
                self.stream = None
                self.status = 'buffer only: ' + str(exc)

    def callback(self, outdata, frames, time_info, status):
        outdata.fill(0)
        try:
            block = self.queue.popleft()
        except IndexError:
            self.underflows += 1
            return
        count = min(frames, len(block))
        outdata[:count, 0] = block[:count]
        if count < frames or status:
            self.underflows += 1

    def submit(self, block):
        self.queue.append(block)

    def close(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, default=Path(__file__).absolute().parent.parent / 'environment.json')
    parser.add_argument('--random-seed', type=int, default=None)
    parser.add_argument('--no-audio', action='store_true')
    parser.add_argument('--duration', type=float, help='optional experiment duration in real seconds')
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error('run the plant as an unprivileged user, never root')
    root = Path(__file__).absolute().parent
    if root.name != 'plant_001' or root.parent.name != 'laboratory':
        parser.error('run a laboratory/plant_001/seed.py copy made by prepare_lab.py')
    # Independent of the genome: bound future heap/mmap allocations on Linux.
    soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    limit = 512 * 1024 * 1024
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_DATA, (limit, hard))
    running = True
    def stop(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    plant = Plant(root, args.environment, rng_seed=args.random_seed)
    telemetry = audio = None
    try:
        telemetry = Telemetry(root)
        audio = AudioOutput(plant.sample_rate, 480, not args.no_audio)
        print('Digital Soil: seed alive; ' + audio.status, flush=True)
        started = next_audio = next_step = next_telemetry = time.monotonic()
        while running and (args.duration is None or time.monotonic() - started < args.duration):
            now = time.monotonic()
            if now >= next_step:
                try:
                    plant.step()
                except (OSError, ValueError, SyntaxError) as exc:
                    plant.error = str(exc)
                next_step = now + 0.5
            if now >= next_audio:
                audio.submit(plant.render())
                next_audio += 480 / plant.sample_rate
                if now - next_audio > 0.12:
                    next_audio = now
            if now >= next_telemetry:
                telemetry.publish(plant.telemetry({'status': audio.status, 'underflows': audio.underflows}))
                next_telemetry = now + 0.2
            time.sleep(max(0.001, min(0.01, next_audio - time.monotonic())))
    finally:
        if audio:
            audio.close()
        if telemetry:
            telemetry.close()
        plant.close()
    return 0


# <soil:growth>

# </soil:growth>

if __name__ == '__main__':
    raise SystemExit(main())
