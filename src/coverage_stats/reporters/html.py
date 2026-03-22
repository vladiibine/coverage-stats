from __future__ import annotations

import html as _html
from pathlib import Path

from coverage_stats.store import LineData
from coverage_stats.reporters.report_data import (
    CoverageReport,
    FileReport,
    FolderNode,
)

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
/* Column toggle controls */
.col-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.2rem;
    margin-bottom: 0.75rem;
    font-size: 0.85em;
    color: #555;
    align-items: center;
}
.col-controls .col-controls-label {
    font-weight: bold;
    color: #333;
}
.col-controls label {
    cursor: pointer;
    user-select: none;
    display: flex;
    align-items: center;
    gap: 0.3em;
}
.col-controls input[type="checkbox"] {
    cursor: pointer;
}
/* Column show/hide transition — fade only; width snaps cleanly */
th[data-col], td[data-col] {
    transition: opacity 0.2s ease;
}
th[data-col].col-hidden, td[data-col].col-hidden {
    display: none;
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

// Column visibility — persisted in localStorage
(function() {
    var KEY = 'cov-stats-hidden-cols';

    function hiddenSet() {
        try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); }
        catch(e) { return new Set(); }
    }

    function saveHidden(set) {
        try { localStorage.setItem(KEY, JSON.stringify(Array.from(set))); } catch(e) {}
    }

    function applyCol(col, visible, animate) {
        var cells = document.querySelectorAll('[data-col="' + col + '"]');
        if (visible) {
            cells.forEach(function(el) {
                el.style.opacity = '0';
                el.classList.remove('col-hidden');
                if (animate) {
                    requestAnimationFrame(function() {
                        requestAnimationFrame(function() { el.style.opacity = ''; });
                    });
                } else {
                    el.style.opacity = '';
                }
            });
        } else {
            if (animate) {
                cells.forEach(function(el) { el.style.opacity = '0'; });
                setTimeout(function() {
                    cells.forEach(function(el) {
                        el.classList.add('col-hidden');
                        el.style.opacity = '';
                    });
                }, 220);
            } else {
                cells.forEach(function(el) { el.classList.add('col-hidden'); });
            }
        }
    }

    window.toggleCol = function(col, visible) {
        var hidden = hiddenSet();
        if (visible) { hidden.delete(col); } else { hidden.add(col); }
        saveHidden(hidden);
        applyCol(col, visible, true);
    };

    document.addEventListener('DOMContentLoaded', function() {
        var hidden = hiddenSet();
        hidden.forEach(function(col) { applyCol(col, false, false); });
        document.querySelectorAll('.col-controls input[type="checkbox"]').forEach(function(cb) {
            if (hidden.has(cb.value)) cb.checked = false;
        });
    });
})();
"""


_INDEX_COL_CONTROLS = (
    '<div class="col-controls">'
    '<span class="col-controls-label">Columns:</span>'
    '<label><input type="checkbox" value="stmts" onchange="toggleCol(\'stmts\', this.checked)" checked> Stmts</label>'
    '<label><input type="checkbox" value="total-pct" onchange="toggleCol(\'total-pct\', this.checked)" checked> Total %</label>'
    '<label><input type="checkbox" value="delib-pct" onchange="toggleCol(\'delib-pct\', this.checked)" checked> Deliberate %</label>'
    '<label><input type="checkbox" value="incid-pct" onchange="toggleCol(\'incid-pct\', this.checked)" checked> Incidental %</label>'
    '</div>'
)

_FILE_COL_CONTROLS = (
    '<div class="col-controls">'
    '<span class="col-controls-label">Columns:</span>'
    '<label><input type="checkbox" value="inc-exec" onchange="toggleCol(\'inc-exec\', this.checked)" checked> Inc. Executions</label>'
    '<label><input type="checkbox" value="del-exec" onchange="toggleCol(\'del-exec\', this.checked)" checked> Del. Executions</label>'
    '<label><input type="checkbox" value="inc-asserts" onchange="toggleCol(\'inc-asserts\', this.checked)" checked> Inc. Asserts</label>'
    '<label><input type="checkbox" value="del-asserts" onchange="toggleCol(\'del-asserts\', this.checked)" checked> Del. Asserts</label>'
    '<label><input type="checkbox" value="inc-tests" onchange="toggleCol(\'inc-tests\', this.checked)" checked> Inc. Tests</label>'
    '<label><input type="checkbox" value="del-tests" onchange="toggleCol(\'del-tests\', this.checked)" checked> Del. Tests</label>'
    '</div>'
)


class HtmlReporter:
    """The HTML reporter. Made for extensibility.

    To extend it, subclass it in your own project and run pytest like this:
        `pytest ... --coverage-stats-reporter my_module.MyCustomHtmlReporter`
    """
    JS = _JS
    CSS = _CSS
    EXTRA_JS = ""
    EXTRA_CSS = ""
    INDEX_COL_CONTROLS = _INDEX_COL_CONTROLS
    FILE_COL_CONTROLS = _FILE_COL_CONTROLS

    def __init__(self, precision: int = 1) -> None:
        self.precision = precision

    def write(self, report: CoverageReport, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        for fr in report.files:
            file_html_name = fr.summary.rel_path.replace("/", "__") + ".html"
            self._write_file_page(fr, output_dir / file_html_name)

        rows_html = "".join(self._render_tree_rows(report.root, depth=0, parent_id=""))
        (output_dir / "index.html").write_text(
            self.render_index_page(rows_html), encoding="utf-8"
        )

    def _missed_ranges(self, missed: list[int]) -> str:
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

    def _write_file_page(self, file_report: FileReport, out_path: Path) -> None:
        s = file_report.summary
        stats_html = self.render_file_stats(
            s.total_stmts, s.total_covered, s.total_pct,
            s.deliberate_covered, s.deliberate_pct,
            s.incidental_covered, s.incidental_pct,
            s.partial_count,
        )

        rows = []
        for lr in file_report.lines:
            ld: LineData | None = None
            if lr.incidental_executions > 0 or lr.deliberate_executions > 0:
                ld = LineData(
                    incidental_executions=lr.incidental_executions,
                    deliberate_executions=lr.deliberate_executions,
                    incidental_asserts=lr.incidental_asserts,
                    deliberate_asserts=lr.deliberate_asserts,
                    incidental_tests=lr.incidental_tests,
                    deliberate_tests=lr.deliberate_tests,
                )
            rows.append(self.render_line(lr.lineno, lr.source_text, ld, lr.executable, partial=lr.partial))

        out_path.write_text(
            self.render_file_page(s.rel_path, stats_html, "".join(rows)), encoding="utf-8"
        )

    def _render_tree_rows(self, node: FolderNode, depth: int, parent_id: str) -> list[str]:
        """DFS traversal: emit a folder row then its children (subfolders, then files)."""
        rows: list[str] = []
        parent_attr = f' data-parent="{parent_id}"' if parent_id else ""
        folder_indent = depth * 24 + 4
        file_indent = depth * 24 + 28
        fmt = f".{self.precision}f"

        for name in sorted(node.subfolders):
            sub = node.subfolders[name]
            fid = "f-" + sub.path.replace("/", "-").replace(".", "_")
            total = sub.agg_total_stmts()
            total_cov = sub.agg_total_covered()
            arcs_total = sub.agg_arcs_total()
            arcs_covered = sub.agg_arcs_covered()
            delib = sub.agg_deliberate()
            incid = sub.agg_incidental()
            arcs_deliberate = sub.agg_arcs_deliberate()
            arcs_incidental = sub.agg_arcs_incidental()
            total_denom = total + arcs_total
            total_pct = (total_cov + arcs_covered) / total_denom * 100.0 if total_denom else 0.0
            delib_pct = (delib + arcs_deliberate) / total_denom * 100.0 if total_denom else 0.0
            incid_pct = (incid + arcs_incidental) / total_denom * 100.0 if total_denom else 0.0
            rows.append(
                f'<tr id="{fid}" class="folder-row"{parent_attr}'
                f' onclick="toggleFolder(\'{fid}\')">'
                f'<td style="padding-left:{folder_indent}px">'
                f'<span class="toggle">&#x25bc;</span> {_html.escape(name)}/</td>'
                f'<td data-col="stmts">{total}</td>'
                f'<td data-col="total-pct">{total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct">{delib_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct">{incid_pct:{fmt}}%</td>'
                f'</tr>'
            )
            rows.extend(self._render_tree_rows(sub, depth + 1, fid))

        for entry in sorted(node.files, key=lambda f: f.rel_path):
            filename = entry.rel_path.split("/")[-1]
            file_html_name = entry.rel_path.replace("/", "__") + ".html"
            total = entry.total_stmts
            total_denom = total + entry.arcs_total
            total_pct = (entry.total_covered + entry.arcs_covered) / total_denom * 100.0 if total_denom else 0.0
            delib_pct = (entry.deliberate_covered + entry.arcs_deliberate) / total_denom * 100.0 if total_denom else 0.0
            incid_pct = (entry.incidental_covered + entry.arcs_incidental) / total_denom * 100.0 if total_denom else 0.0
            rows.append(
                f'<tr{parent_attr}>'
                f'<td style="padding-left:{file_indent}px">'
                f'<a href="{_html.escape(file_html_name)}">{_html.escape(filename)}</a></td>'
                f'<td data-col="stmts">{total}</td>'
                f'<td data-col="total-pct">{total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct">{delib_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct">{incid_pct:{fmt}}%</td>'
                f'</tr>'
            )

        return rows

    def render_file_stats(self, total_stmts: int, covered: int, total_pct: float,
                          deliberate_cnt: int, deliberate_pct: float,
                          incidental_cnt: int, incidental_pct: float,
                          partial_cnt: int = 0) -> str:
        missed = total_stmts - covered
        fmt = f".{self.precision}f"
        partial_cell = (
            f'<div class="stat"><div class="stat-value" style="color:#e65100">{partial_cnt}</div>'
            f'<div class="stat-label">partial</div></div>'
        ) if partial_cnt else ""
        return (
            f'<div class="file-stats">'
            f'<div class="stat"><div class="stat-value">{total_stmts}</div><div class="stat-label">statements</div></div>'
            f'<div class="stat"><div class="stat-value">{missed}</div><div class="stat-label">missing</div></div>'
            f'<div class="stat"><div class="stat-value">{covered}</div><div class="stat-label">covered</div></div>'
            f'<div class="stat"><div class="stat-value">{total_pct:{fmt}}%</div><div class="stat-label">total %</div></div>'
            f'{partial_cell}'
            f'<div class="stat"><div class="stat-value">{deliberate_cnt}</div><div class="stat-label">deliberate</div></div>'
            f'<div class="stat"><div class="stat-value">{deliberate_pct:{fmt}}%</div><div class="stat-label">deliberate %</div></div>'
            f'<div class="stat"><div class="stat-value">{incidental_cnt}</div><div class="stat-label">incidental</div></div>'
            f'<div class="stat"><div class="stat-value">{incidental_pct:{fmt}}%</div><div class="stat-label">incidental %</div></div>'
            f'</div>'
        )

    def render_line(self, lineno: int, source_text: str, ld: LineData | None, executable: bool,
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
            f'<td data-col="inc-exec">{inc_exec}</td>'
            f'<td data-col="del-exec">{del_exec}</td>'
            f'<td data-col="inc-asserts">{inc_asserts}</td>'
            f'<td data-col="del-asserts">{del_asserts}</td>'
            f'<td data-col="inc-tests">{inc_tests}</td>'
            f'<td data-col="del-tests">{del_tests}</td>'
            f'</tr>'
        )

    def render_index_page(self, rows_html: str) -> str:
        return (
            f'<!DOCTYPE html>'
            f'<html lang="en">'
            f'<head>'
            f'<meta charset="utf-8">'
            f'<title>Coverage Stats</title>'
            f'<style>{self.CSS}</style>'
            f'<style>{self.EXTRA_CSS}</style>'
            f'<script>{self.JS}</script>'
            f'<script>{self.EXTRA_JS}</script>'
            f'</head>'
            f'<body>'
            f'<h1>Coverage Stats</h1>'
            f'{self.INDEX_COL_CONTROLS}'
            f'<table>'
            f'<thead><tr>'
            f'<th>File</th>'
            f'<th data-col="stmts">Stmts</th>'
            f'<th data-col="total-pct">Total %</th>'
            f'<th data-col="delib-pct">Deliberate %</th>'
            f'<th data-col="incid-pct">Incidental %</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>'
            f'</body>'
            f'</html>'
        )

    def render_file_page(self, rel_path: str, stats_html: str, lines_html: str) -> str:
        escaped_path = _html.escape(rel_path)
        return (
            f'<!DOCTYPE html>'
            f'<html lang="en">'
            f'<head>'
            f'<meta charset="utf-8">'
            f'<title>{escaped_path} — Coverage Stats</title>'
            f'<style>{self.CSS}</style>'
            f'<style>{self.EXTRA_CSS}</style>'
            f'<script>{self.JS}</script>'
            f'<script>{self.EXTRA_JS}</script>'
            f'</head>'
            f'<body>'
            f'<h1>{escaped_path}</h1>'
            f'<p><a href="index.html">Back to index</a></p>'
            f'{stats_html}'
            f'{self.FILE_COL_CONTROLS}'
            f'<table>'
            f'<thead><tr>'
            f'<th>#</th><th></th><th>Source</th>'
            f'<th data-col="inc-exec">Incidental Executions</th>'
            f'<th data-col="del-exec">Deliberate Executions</th>'
            f'<th data-col="inc-asserts">Incidental Asserts</th>'
            f'<th data-col="del-asserts">Deliberate Asserts</th>'
            f'<th data-col="inc-tests">Incidental Tests</th>'
            f'<th data-col="del-tests">Deliberate Tests</th>'
            f'</tr></thead>'
            f'<tbody>{lines_html}</tbody>'
            f'</table>'
            f'</body>'
            f'</html>'
        )


# ---------------------------------------------------------------------------
# Module-level shims — delegate to a default HtmlReporter() instance so that
# existing call sites (including tests) continue to work unchanged.
# ---------------------------------------------------------------------------

def write_html(report: CoverageReport, output_dir: Path, precision: int = 1) -> None:
    HtmlReporter(precision=precision).write(report, output_dir)


def render_line(lineno: int, source_text: str, ld: LineData | None, executable: bool,
                partial: bool = False) -> str:
    return HtmlReporter().render_line(lineno, source_text, ld, executable, partial)


def render_file_stats(total_stmts: int, covered: int, total_pct: float,
                      deliberate_cnt: int, deliberate_pct: float,
                      incidental_cnt: int, incidental_pct: float,
                      partial_cnt: int = 0, precision: int = 1) -> str:
    return HtmlReporter(precision=precision).render_file_stats(
        total_stmts, covered, total_pct,
        deliberate_cnt, deliberate_pct,
        incidental_cnt, incidental_pct,
        partial_cnt,
    )


def render_index_page(rows_html: str) -> str:
    return HtmlReporter().render_index_page(rows_html)


def render_file_page(rel_path: str, stats_html: str, lines_html: str) -> str:
    return HtmlReporter().render_file_page(rel_path, stats_html, lines_html)


def _render_tree_rows(node: FolderNode, depth: int, parent_id: str, precision: int = 1) -> list[str]:
    return HtmlReporter(precision=precision)._render_tree_rows(node, depth, parent_id)
