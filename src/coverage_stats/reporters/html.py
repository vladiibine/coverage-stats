from __future__ import annotations

import ast
import html as _html
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from pathlib import Path
import pytest

from coverage_stats.executable_lines import get_executable_lines
from coverage_stats.store import LineData, SessionStore

_CSS = """
body {
    font-family: monospace;
    margin: 1rem 2rem;
}
table {
    border-collapse: collapse;
    width: 100%;
}
th, td {
    border: 1px solid #ccc;
    padding: 0.25rem 0.5rem;
    text-align: left;
}
th {
    background: #f0f0f0;
    position: sticky;
    top: 0;
    z-index: 1;
}
tr.deliberate {
    background: #c8e6c9;
}
tr.incidental {
    background: #fff9c4;
}
tr.missed {
    background: #ffcdd2;
}
tr.partial {
    background: #ffe0b2;
}
td.branch-warn {
    color: #e65100;
    font-weight: bold;
    white-space: nowrap;
}
tr.folder-row {
    background: #e8e8e8;
    cursor: pointer;
    user-select: none;
}
tr.folder-row:hover {
    background: #d8d8d8;
}
tr.folder-row td:first-child {
    font-weight: bold;
}
.toggle {
    display: inline-block;
    width: 1em;
    text-align: center;
    font-style: normal;
}
a {
    color: #1565c0;
}
.file-stats {
    display: flex;
    gap: 2rem;
    align-items: baseline;
    background: #f5f5f5;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 0.6rem 1rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
}
.file-stats .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.file-stats .stat-value {
    font-size: 1.4em;
    font-weight: bold;
}
.file-stats .stat-label {
    font-size: 0.8em;
    color: #666;
}
.file-stats .missed-ranges {
    flex: 1;
    min-width: 200px;
}
.file-stats .missed-ranges .stat-label {
    margin-bottom: 0.2em;
}
.file-stats .missed-ranges .stat-value {
    font-size: 0.9em;
    font-weight: normal;
    color: #c62828;
    word-break: break-all;
}
"""


_JS = """
function toggleFolder(id) {
    var row = document.getElementById(id);
    var toggle = row.querySelector('.toggle');
    var opening = toggle.textContent === '\u25b6';
    toggle.textContent = opening ? '\u25bc' : '\u25b6';
    var children = document.querySelectorAll('[data-parent="' + id + '"]');
    children.forEach(function(child) {
        child.style.display = opening ? '' : 'none';
        if (!opening) {
            var cid = child.id;
            if (cid) {
                var ct = child.querySelector('.toggle');
                if (ct && ct.textContent === '\u25bc') {
                    ct.textContent = '\u25b6';
                    hideDescendants(cid);
                }
            }
        }
    });
}
function hideDescendants(id) {
    document.querySelectorAll('[data-parent="' + id + '"]').forEach(function(row) {
        row.style.display = 'none';
        if (row.id) hideDescendants(row.id);
    });
}
"""


@dataclass
class _FileEntry:
    rel_path: str
    file_html_name: str
    total_stmts: int
    deliberate_covered: int
    incidental_covered: int


@dataclass
class _FolderNode:
    path: str  # e.g. "src/payments/billing", "" for the virtual root
    subfolders: dict[str, "_FolderNode"] = dc_field(default_factory=dict)
    files: list[_FileEntry] = dc_field(default_factory=list)

    def agg_total_stmts(self) -> int:
        return sum(f.total_stmts for f in self.files) + sum(
            s.agg_total_stmts() for s in self.subfolders.values()
        )

    def agg_deliberate(self) -> int:
        return sum(f.deliberate_covered for f in self.files) + sum(
            s.agg_deliberate() for s in self.subfolders.values()
        )

    def agg_incidental(self) -> int:
        return sum(f.incidental_covered for f in self.files) + sum(
            s.agg_incidental() for s in self.subfolders.values()
        )


def _build_file_tree(entries: list[_FileEntry]) -> _FolderNode:
    root = _FolderNode(path="")
    for entry in entries:
        parts = entry.rel_path.split("/")
        node = root
        for part in parts[:-1]:
            if part not in node.subfolders:
                parent_path = f"{node.path}/{part}" if node.path else part
                node.subfolders[part] = _FolderNode(path=parent_path)
            node = node.subfolders[part]
        node.files.append(entry)
    return root


def _render_tree_rows(node: _FolderNode, depth: int, parent_id: str) -> list[str]:
    """DFS traversal: emit a folder row then its children (subfolders, then files)."""
    rows: list[str] = []
    parent_attr = f' data-parent="{parent_id}"' if parent_id else ""
    folder_indent = depth * 24 + 4
    file_indent = depth * 24 + 28

    for name in sorted(node.subfolders):
        sub = node.subfolders[name]
        fid = "f-" + sub.path.replace("/", "-").replace(".", "_")
        total = sub.agg_total_stmts()
        delib = sub.agg_deliberate()
        incid = sub.agg_incidental()
        delib_pct = delib / total * 100.0 if total else 0.0
        incid_pct = incid / total * 100.0 if total else 0.0
        rows.append(
            f'<tr id="{fid}" class="folder-row"{parent_attr}'
            f' onclick="toggleFolder(\'{fid}\')">'
            f'<td style="padding-left:{folder_indent}px">'
            f'<span class="toggle">&#x25bc;</span> {_html.escape(name)}/</td>'
            f'<td>{total}</td>'
            f'<td>{delib_pct:.1f}%</td>'
            f'<td>{incid_pct:.1f}%</td>'
            f'</tr>'
        )
        rows.extend(_render_tree_rows(sub, depth + 1, fid))

    for entry in sorted(node.files, key=lambda f: f.rel_path):
        filename = entry.rel_path.split("/")[-1]
        total = entry.total_stmts
        delib_pct = entry.deliberate_covered / total * 100.0 if total else 0.0
        incid_pct = entry.incidental_covered / total * 100.0 if total else 0.0
        rows.append(
            f'<tr{parent_attr}>'
            f'<td style="padding-left:{file_indent}px">'
            f'<a href="{_html.escape(entry.file_html_name)}">{_html.escape(filename)}</a></td>'
            f'<td>{total}</td>'
            f'<td>{delib_pct:.1f}%</td>'
            f'<td>{incid_pct:.1f}%</td>'
            f'</tr>'
        )

    return rows


def _missed_ranges(missed: list[int]) -> str:
    """Convert a sorted list of line numbers into a compact range string, e.g. '5-8, 12, 20-22'."""
    if not missed:
        return ""
    ranges = []
    start = end = missed[0]
    for n in missed[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(str(start) if start == end else f"{start}-{end}")
            start = end = n
    ranges.append(str(start) if start == end else f"{start}-{end}")
    return ", ".join(ranges)


def _get_partial_branches(path: str, lines: dict[int, LineData]) -> set[int]:
    """Return line numbers of executed if/while-statements where not all branches were taken.

    For each ``if`` or ``while`` node whose line was executed:
    - *true branch not taken*: the first line of the body was never executed.
    - *false branch not taken*: for nodes with an else/elif clause, the first line of
      the else was never executed; otherwise, the condition line ran more times than the
      body's first line (i.e. the condition was never False).

    For ``while`` loops specifically, ``cond_count == body_count`` means the condition
    was always True and the loop never exited normally (it left via exception, return,
    or break), so the false branch is considered not taken — matching coverage.py behaviour.
    """
    def _count(lineno: int) -> int:
        ld = lines.get(lineno)
        return (ld.incidental_executions + ld.deliberate_executions) if ld else 0

    try:
        source = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return set()

    result: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.If, ast.While, ast.For)):
            continue
        if_count = _count(node.lineno)
        if if_count == 0:
            continue
        body_count = _count(node.body[0].lineno)
        true_taken = body_count > 0
        if node.orelse:
            false_taken = _count(node.orelse[0].lineno) > 0
        else:
            false_taken = if_count > body_count
        if not true_taken or not false_taken:
            result.add(node.lineno)
    return result


def render_file_stats(total_stmts: int, covered: int,
                      deliberate_cnt: int, deliberate_pct: float, incidental_cnt: int, incidental_pct: float,
                      partial_cnt: int = 0) -> str:
    missed = total_stmts - covered
    partial_cell = (
        f'<div class="stat"><div class="stat-value" style="color:#e65100">{partial_cnt}</div>'
        f'<div class="stat-label">partial</div></div>'
    ) if partial_cnt else ""
    return (
        f'<div class="file-stats">'
        f'<div class="stat"><div class="stat-value">{total_stmts}</div><div class="stat-label">statements</div></div>'
        f'<div class="stat"><div class="stat-value">{missed}</div><div class="stat-label">missing</div></div>'
        f'<div class="stat"><div class="stat-value">{covered}</div><div class="stat-label">covered</div></div>'
        f'{partial_cell}'
        f'<div class="stat"><div class="stat-value">{deliberate_cnt}</div><div class="stat-label">deliberate</div></div>'
        f'<div class="stat"><div class="stat-value">{deliberate_pct:.1f}%</div><div class="stat-label">deliberate %</div></div>'
        f'<div class="stat"><div class="stat-value">{incidental_cnt}</div><div class="stat-label">incidental</div></div>'
        f'<div class="stat"><div class="stat-value">{incidental_pct:.1f}%</div><div class="stat-label">incidental %</div></div>'
        f'</div>'
    )


def render_line(lineno: int, source_text: str, ld: LineData | None, executable: bool,
                partial: bool = False) -> str:
    if not executable:
        css_class = ""
        inc_exec = del_exec = inc_asserts = del_asserts = inc_tests = del_tests = ""
    elif partial:
        css_class = "partial"
        inc_exec = str(ld.incidental_executions) if ld else "0"
        del_exec = str(ld.deliberate_executions) if ld else "0"
        inc_asserts = str(ld.incidental_asserts) if ld else "0"
        del_asserts = str(ld.deliberate_asserts) if ld else "0"
        inc_tests = str(ld.incidental_tests) if ld else "0"
        del_tests = str(ld.deliberate_tests) if ld else "0"
    elif ld is not None and ld.deliberate_executions > 0:
        css_class = "deliberate"
        inc_exec = str(ld.incidental_executions)
        del_exec = str(ld.deliberate_executions)
        inc_asserts = str(ld.incidental_asserts)
        del_asserts = str(ld.deliberate_asserts)
        inc_tests = str(ld.incidental_tests)
        del_tests = str(ld.deliberate_tests)
    elif ld is not None and ld.incidental_executions > 0:
        css_class = "incidental"
        inc_exec = str(ld.incidental_executions)
        del_exec = str(ld.deliberate_executions)
        inc_asserts = str(ld.incidental_asserts)
        del_asserts = str(ld.deliberate_asserts)
        inc_tests = str(ld.incidental_tests)
        del_tests = str(ld.deliberate_tests)
    else:
        css_class = "missed"
        inc_exec = del_exec = inc_asserts = del_asserts = inc_tests = del_tests = "0"
    escaped = _html.escape(source_text)
    branch_marker = '<td class="branch-warn" title="not all branches taken">⚑</td>' if partial else "<td></td>"
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<tr{class_attr}>'
        f'<td>{lineno}</td>'
        f'{branch_marker}'
        f'<td><pre style="margin:0">{escaped}</pre></td>'
        f'<td>{inc_exec}</td>'
        f'<td>{del_exec}</td>'
        f'<td>{inc_asserts}</td>'
        f'<td>{del_asserts}</td>'
        f'<td>{inc_tests}</td>'
        f'<td>{del_tests}</td>'
        f'</tr>'
    )


def render_index_page(rows_html: str) -> str:
    return (
        f'<!DOCTYPE html>'
        f'<html lang="en">'
        f'<head>'
        f'<meta charset="utf-8">'
        f'<title>Coverage Stats</title>'
        f'<style>{_CSS}</style>'
        f'<script>{_JS}</script>'
        f'</head>'
        f'<body>'
        f'<h1>Coverage Stats</h1>'
        f'<table>'
        f'<thead><tr>'
        f'<th>File</th><th>Stmts</th><th>Deliberate %</th><th>Incidental %</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</body>'
        f'</html>'
    )


def render_file_page(rel_path: str, stats_html: str, lines_html: str) -> str:
    escaped_path = _html.escape(rel_path)
    return (
        f'<!DOCTYPE html>'
        f'<html lang="en">'
        f'<head>'
        f'<meta charset="utf-8">'
        f'<title>{escaped_path} — Coverage Stats</title>'
        f'<style>{_CSS}</style>'
        f'</head>'
        f'<body>'
        f'<h1>{escaped_path}</h1>'
        f'<p><a href="index.html">Back to index</a></p>'
        f'{stats_html}'
        f'<table>'
        f'<thead><tr>'
        f'<th>#</th><th></th><th>Source</th>'
        f'<th>Incidental Executions</th><th>Deliberate Executions</th>'
        f'<th>Incidental Asserts</th><th>Deliberate Asserts</th>'
        f'<th>Incidental Tests</th><th>Deliberate Tests</th>'
        f'</tr></thead>'
        f'<tbody>{lines_html}</tbody>'
        f'</table>'
        f'</body>'
        f'</html>'
    )


def _group_by_rel_path(store: SessionStore, config: pytest.Config) -> dict[str, dict[int, LineData]]:
    files: dict[str, dict[int, LineData]] = defaultdict(dict)
    for (abs_path, lineno), ld in store._data.items():
        try:
            rel = Path(abs_path).relative_to(config.rootpath).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        files[rel][lineno] = ld
    return files



def _write_file_page(rel_path: str, lines: dict[int, LineData], abs_path: str,
                     executable: set[int], out_path: Path) -> None:
    try:
        source_lines = Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines()
        source_map = {i + 1: line for i, line in enumerate(source_lines)}
        all_linenos: list[int] = list(range(1, len(source_lines) + 1))
    except Exception:
        source_map = {}
        all_linenos = sorted(lines.keys())

    total_stmts = len(executable)
    covered_stmts = sum(
        1 for ln in executable
        if ln in lines and (lines[ln].deliberate_executions > 0 or lines[ln].incidental_executions > 0)
    )
    deliberate_covered = sum(1 for ln in executable if ln in lines and lines[ln].deliberate_executions > 0)
    deliberate_pct = deliberate_covered / total_stmts * 100.0 if total_stmts else 0.0
    incidental_covered = sum(1 for ln in executable if ln in lines and lines[ln].incidental_executions > 0)
    incidental_pct = incidental_covered / total_stmts * 100.0 if total_stmts else 0.0
    partial_branches = _get_partial_branches(abs_path, lines)
    partial_cnt = len(partial_branches & executable)

    stats_html = render_file_stats(total_stmts, covered_stmts, deliberate_covered, deliberate_pct, incidental_covered, incidental_pct, partial_cnt)

    rows = []
    for lineno in all_linenos:
        ld = lines.get(lineno)
        source_text = source_map.get(lineno, "")
        rows.append(render_line(lineno, source_text, ld, lineno in executable, partial=lineno in partial_branches))

    out_path.write_text(render_file_page(rel_path, stats_html, "".join(rows)), encoding="utf-8")


def write_html(store: SessionStore, config: pytest.Config, output_dir: Path) -> None:
    files = _group_by_rel_path(store, config)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build a mapping from rel_path -> abs_path for source reading
    abs_path_map: dict[str, str] = {}
    for (abs_path, _lineno) in store._data.keys():
        try:
            rel = Path(abs_path).relative_to(config.rootpath).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        abs_path_map[rel] = abs_path

    file_entries: list[_FileEntry] = []
    for rel_path, lines in files.items():
        file_html_name = rel_path.replace("/", "__") + ".html"
        abs_path = abs_path_map.get(rel_path, rel_path)
        executable = get_executable_lines(abs_path)
        total_stmts = len(executable) if executable else len(lines)
        deliberate_covered = sum(
            1 for ln in executable if ln in lines and lines[ln].deliberate_executions > 0
        )
        incidental_covered = sum(
            1 for ln in executable if ln in lines and lines[ln].incidental_executions > 0
        )
        _write_file_page(rel_path, lines, abs_path, executable, output_dir / file_html_name)
        file_entries.append(_FileEntry(
            rel_path=rel_path,
            file_html_name=file_html_name,
            total_stmts=total_stmts,
            deliberate_covered=deliberate_covered,
            incidental_covered=incidental_covered,
        ))

    tree = _build_file_tree(file_entries)
    rows_html = "".join(_render_tree_rows(tree, depth=0, parent_id=""))
    (output_dir / "index.html").write_text(
        render_index_page(rows_html), encoding="utf-8"
    )
