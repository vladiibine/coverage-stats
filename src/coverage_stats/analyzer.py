"""
Analyzer: merges .coverage data + .coverage-stats-meta.json into per-line stats.

Output structure per file:
    {
        "path": "/abs/path/to/file.py",
        "lines": {
            "10": {"direct": 3, "incidental": 7, "total": 10},
            "11": {"direct": 0, "incidental": 2, "total": 2},
            ...
        }
    }
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# AST-based scope mapper
# ---------------------------------------------------------------------------

@dataclass
class ScopeMapper:
    """Maps line numbers in a Python source file to their enclosing qualified scope."""

    _line_to_scopes: dict[int, list[str]] = field(default_factory=dict)

    @classmethod
    def from_source(cls, source: str, module_name: str = "") -> "ScopeMapper":
        mapper = cls()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return mapper
        mapper._walk(tree, prefix=module_name, start=1, end=float("inf"))  # type: ignore[arg-type]
        return mapper

    def _walk(
        self,
        node: ast.AST,
        prefix: str,
        start: int,
        end: float,
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                child_start = child.lineno
                child_end = getattr(child, "end_lineno", child_start)
                # Register every line in this node's body range.
                for lineno in range(child_start, child_end + 1):
                    self._line_to_scopes.setdefault(lineno, [])
                    self._line_to_scopes[lineno].append(qualname)
                self._walk(child, qualname, child_start, child_end)
            else:
                self._walk(child, prefix, start, end)

    def scopes_for_line(self, lineno: int) -> list[str]:
        """Return all enclosing scopes (innermost last) for a given line."""
        return self._line_to_scopes.get(lineno, [])


# ---------------------------------------------------------------------------
# Target matching
# ---------------------------------------------------------------------------

def _matches(covered_targets: list[str], scopes: list[str], module_name: str) -> bool:
    """
    Return True if any covered target matches the line's scopes.

    Matching rules (all prefix-based to handle nested classes/methods):
    - "mymodule"                 → matches any line in mymodule
    - "mymodule.MyClass"         → matches any line in MyClass or its methods
    - "mymodule.MyClass.method"  → matches lines inside that specific method
    - Partial qualnames (without module) are also tried.
    """
    candidates = set()
    candidates.add(module_name)  # bare module always a candidate scope
    for scope in scopes:
        candidates.add(scope)
        # Also add each prefix segment so "mymodule.MyClass" matches a target of "MyClass"
        parts = scope.split(".")
        for i in range(1, len(parts) + 1):
            candidates.add(".".join(parts[i:]))  # strip leading segments

    for target in covered_targets:
        for candidate in candidates:
            if candidate == target or candidate.startswith(target + "."):
                return True
            if target == candidate or target.startswith(candidate + "."):
                return True
    return False


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

@dataclass
class LineStats:
    direct: int = 0
    incidental: int = 0

    @property
    def total(self) -> int:
        return self.direct + self.incidental


@dataclass
class FileStats:
    path: str
    lines: dict[int, LineStats] = field(default_factory=dict)
    source_lines: list[str] = field(default_factory=list)


def analyze(
    coverage_data_path: str | Path = ".coverage",
    meta_path: str | Path = ".coverage-stats-meta.json",
) -> list[FileStats]:
    """
    Load coverage data and metadata, return per-file per-line stats.
    """
    import coverage as coverage_module

    coverage_data_path = Path(coverage_data_path)
    meta_path = Path(meta_path)

    # Load coverage data.
    data = coverage_module.CoverageData(basename=str(coverage_data_path))
    data.read()

    # Load covers metadata: {test_node_id: [covered_qualnames]}
    covers_meta: dict[str, list[str]] = {}
    if meta_path.exists():
        covers_meta = json.loads(meta_path.read_text())

    results: list[FileStats] = []

    for filepath in data.measured_files():
        abs_path = Path(filepath)
        if not abs_path.exists():
            continue

        source = abs_path.read_text(encoding="utf-8", errors="replace")
        source_lines = source.splitlines()

        # Derive module name from path (best-effort).
        module_name = _path_to_module(abs_path)

        scope_mapper = ScopeMapper.from_source(source, module_name)

        # contexts_by_lineno: {lineno: set_of_context_strings}
        # Each context string is a test node ID (set by our pytest plugin).
        contexts_by_lineno: dict[int, set[str]] = data.contexts_by_lineno(filepath)  # type: ignore[attr-defined]

        file_stats = FileStats(path=filepath, source_lines=source_lines)

        for lineno, contexts in contexts_by_lineno.items():
            stats = LineStats()
            scopes = scope_mapper.scopes_for_line(lineno)

            for ctx in contexts:
                # Skip the empty/default context.
                if not ctx or ctx == "":
                    stats.incidental += 1
                    continue

                # pytest-cov appends "|run", "|setup", "|teardown" to node IDs.
                # Strip the phase suffix to get the bare test node ID.
                node_id = ctx.split("|")[0] if "|" in ctx else ctx

                covered_targets = covers_meta.get(node_id, [])

                if covered_targets and _matches(covered_targets, scopes, module_name):
                    stats.direct += 1
                else:
                    stats.incidental += 1

            file_stats.lines[lineno] = stats

        results.append(file_stats)

    return results


def _path_to_module(path: Path) -> str:
    """Best-effort conversion of a file path to a dotted module name."""
    parts = list(path.with_suffix("").parts)
    # Walk backwards until we stop finding __init__.py siblings.
    module_parts: list[str] = []
    current = path.parent
    for part in reversed(parts):
        if part in ("", "/"):
            break
        module_parts.insert(0, part)
        if not (current / "__init__.py").exists() and current != path.parent:
            break
        current = current.parent
    return ".".join(module_parts) if module_parts else path.stem
