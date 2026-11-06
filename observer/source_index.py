"""Read actual files and index function spans without importing plant code."""
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Span:
    id: str
    path: str
    start: int
    end: int


class SourceIndex:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}
        self.spans = {}
        self.error = ''
        self._cache = {}

    def refresh(self):
        files, spans, cache = {}, {}, {}
        self.error = ''
        try:
            paths = sorted(self.root.rglob('*.py'))
            if len(paths) > 64:
                raise ValueError('source file limit exceeded')
            total = 0
            for path in paths:
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    continue
                rel = path.relative_to(self.root).as_posix()
                st = path.stat()
                total += st.st_size
                if total > 524288:
                    raise ValueError('source size limit exceeded')
                signature = (st.st_ino, st.st_mtime_ns, st.st_size)
                previous = self._cache.get(rel)
                if previous and previous[0] == signature:
                    text, entries = previous[1:]
                else:
                    text = path.read_text(encoding='utf-8')
                    entries = []
                    for n in ast.parse(text).body:
                        if isinstance(n, ast.FunctionDef) and n.name.startswith('tissue_'):
                            identifier = n.name.removeprefix('tissue_')
                            if len(identifier) == 12 and all(c in '0123456789abcdef' for c in identifier):
                                entries.append(Span(identifier, rel, n.lineno, n.end_lineno))
                files[rel] = text
                spans.update({s.id: s for s in entries})
                cache[rel] = (signature, text, entries)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            self.error = str(exc)
        self.files, self.spans, self._cache = files, spans, cache

    def ordered(self):
        return sorted(self.spans.values(), key=lambda s: (s.path, s.start))
