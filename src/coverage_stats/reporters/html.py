from __future__ import annotations

import html as _html
from pathlib import Path

from coverage_stats.store import LineData
from coverage_stats.reporters.report_data import (
    CoverageReport,
    FileReport,
    FolderNode,
    LineReport,
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
/* Index table cell colour levels: red (0) → green (9) */
td.lvl-0 { background: #c62828; color: #fff; }
td.lvl-1 { background: #d84315; color: #fff; }
td.lvl-2 { background: #e65100; color: #fff; }
td.lvl-3 { background: #ef6c00; color: #212121; }
td.lvl-4 { background: #f9a825; color: #212121; }
td.lvl-5 { background: #9e9d24; color: #fff; }
td.lvl-6 { background: #689f38; color: #fff; }
td.lvl-7 { background: #388e3c; color: #fff; }
td.lvl-8 { background: #2e7d32; color: #fff; }
td.lvl-9 { background: #1b5e20; color: #fff; }
/* Help button (? next to title) */
.help-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.4em;
    height: 1.4em;
    border-radius: 50%;
    border: 2px solid #1565c0;
    background: #fff;
    color: #1565c0;
    font-size: 0.6em;
    font-weight: bold;
    cursor: pointer;
    vertical-align: middle;
    margin-left: 0.4em;
    padding: 0;
    line-height: 1;
}
.help-btn:hover { background: #1565c0; color: #fff; }
/* Help modal overlay + dialog */
.help-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 100;
    align-items: center;
    justify-content: center;
}
.help-dialog {
    background: #fff;
    border-radius: 6px;
    padding: 1.5rem 2rem;
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
    font-family: sans-serif;
}
.help-dialog h2 { margin: 0 0 1rem; font-size: 1.1em; }
.help-close {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    background: none;
    border: none;
    font-size: 1.1em;
    cursor: pointer;
    color: #666;
    padding: 0.2em 0.4em;
    line-height: 1;
}
.help-close:hover { color: #000; }
.help-dl dt { font-weight: bold; margin-top: 0.75rem; color: #333; }
.help-dl dd { margin: 0.15rem 0 0 0; color: #555; font-size: 0.9em; }
"""


_JS = """
function openHelp(id) {
    document.getElementById(id).style.display = 'flex';
}
function closeHelp(id) {
    document.getElementById(id).style.display = 'none';
}

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
    var KEY = 'cov-stats-col-prefs';

    // Storage format: {col_id: bool} — only columns the user has explicitly toggled.
    // Columns absent from the object fall through to the Python-baked default.
    // Migration: old format was an array of hidden col ids.
    function loadExplicit() {
        try {
            var raw = localStorage.getItem(KEY);
            if (!raw) return {};
            var val = JSON.parse(raw);
            if (Array.isArray(val)) {
                // Migrate old hidden-set format
                var obj = {};
                val.forEach(function(col) { obj[col] = false; });
                return obj;
            }
            return val || {};
        } catch(e) { return {}; }
    }

    function saveExplicit(explicit) {
        try { localStorage.setItem(KEY, JSON.stringify(explicit)); } catch(e) {}
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
        var explicit = loadExplicit();
        explicit[col] = visible;
        saveExplicit(explicit);
        applyCol(col, visible, true);
    };

    document.addEventListener('DOMContentLoaded', function() {
        var explicit = loadExplicit();
        document.querySelectorAll('.col-controls input[type="checkbox"]').forEach(function(cb) {
            var col = cb.value;
            if (col in explicit) {
                // User has explicitly toggled this column — honour their choice
                applyCol(col, explicit[col], false);
                cb.checked = explicit[col];
            } else {
                // No saved preference — use Python-baked default (col-hidden class)
                var firstCell = document.querySelector('[data-col="' + col + '"]');
                var visible = firstCell ? !firstCell.classList.contains('col-hidden') : true;
                cb.checked = visible;
            }
        });
    });
})();
"""


class HtmlReporter:
    """The HTML reporter. Made for extensibility.

    To extend it, subclass it in your own project and run pytest like this:
        `pytest ... --coverage-stats-reporter my_module.MyCustomHtmlReporter`
    """
    JS = _JS
    CSS = _CSS
    EXTRA_JS = ""
    EXTRA_CSS = ""

    # Map col-id → visible (True = shown by default, False = hidden by default).
    # Override in a subclass to change initial column visibility.
    INDEX_COLUMNS: dict[str, bool] = {
        "stmts": True,
        "total-pct": True,
        "delib-pct": True,
        "incid-pct": True,
        "delib-covered": False,
        "incid-covered": False,
        "inc-asserts": False,
        "del-asserts": False,
        "inc-assert-density": False,
        "del-assert-density": False,
    }
    FILE_COLUMNS: dict[str, bool] = {
        "inc-exec": True,
        "del-exec": True,
        "inc-asserts": True,
        "del-asserts": True,
        "inc-tests": True,
        "del-tests": True,
    }

    # Human-readable labels for each column's checkbox. Override to rename.
    INDEX_COL_LABELS: dict[str, str] = {
        "stmts": "Stmts",
        "total-pct": "Total %",
        "delib-pct": "Deliberate %",
        "incid-pct": "Incidental %",
        "delib-covered": "Del. Covered",
        "incid-covered": "Inc. Covered",
        "inc-asserts": "Inc. Asserts",
        "del-asserts": "Del. Asserts",
        "inc-assert-density": "Inc. Assert Density",
        "del-assert-density": "Del. Assert Density",
    }
    FILE_COL_LABELS: dict[str, str] = {
        "inc-exec": "Inc. Executions",
        "del-exec": "Del. Executions",
        "inc-asserts": "Inc. Asserts",
        "del-asserts": "Del. Asserts",
        "inc-tests": "Inc. Tests",
        "del-tests": "Del. Tests",
    }

    # Descriptions shown as tooltips on checkbox labels and in the help popup.
    # Override in a subclass to customise the documentation.
    INDEX_COL_DESCS: dict[str, str] = {
        "stmts": (
            "Total number of statements + branches tracked in the file or folder."
        ),
        "total-pct": (
            "Percentage of statements + branches covered by any test (deliberate or "
            "incidental). Files with nothing to cover (e.g. empty __init__.py) show 100%."
        ),
        "delib-pct": (
            "Percentage of statements + branches covered by at least one test that "
            "explicitly declares coverage via @covers(...)."
        ),
        "incid-pct": (
            "Percentage of statements + branches covered incidentally \u2014 executed "
            "by tests, but not via a @covers declaration."
        ),
        "delib-covered": (
            "Raw count of statements + branches covered deliberately. "
            "Colored using the same level as the Deliberate % column."
        ),
        "incid-covered": (
            "Raw count of statements + branches covered incidentally. "
            "Colored using the same level as the Incidental % column."
        ),
        "inc-asserts": (
            "Total number of assert statements executed during incidental coverage "
            "of this file or folder."
        ),
        "del-asserts": (
            "Total number of assert statements executed during deliberate coverage "
            "of this file or folder."
        ),
        "inc-assert-density": (
            "Incidental assert count divided by total statements + branches. "
            "A higher value means more assertions are observing each line incidentally."
        ),
        "del-assert-density": (
            "Deliberate assert count divided by total statements + branches. "
            "A higher value means more targeted assertions are exercising each line."
        ),
    }
    FILE_COL_DESCS: dict[str, str] = {
        "inc-exec": "Number of times the line was executed by incidental tests.",
        "del-exec": (
            "Number of times the line was executed by deliberate tests "
            "(tests with a matching @covers declaration)."
        ),
        "inc-asserts": (
            "Number of assert statements executed in all of the tests that ran "
            "when the line was executed incidentally."
        ),
        "del-asserts": (
            "Number of assert statements executed in all of the tests that ran "
            "when the line was executed deliberately."
        ),
        "inc-tests": "Number of distinct incidental tests that executed this line.",
        "del-tests": "Number of distinct deliberate tests that executed this line.",
    }

    def __init__(self, precision: int = 1) -> None:
        self.precision = precision

    def _col_controls_html(
        self,
        columns: dict[str, bool],
        labels: dict[str, str],
        descs: dict[str, str] | None = None,
    ) -> str:
        """Render the column-visibility checkbox bar."""
        parts = ['<div class="col-controls"><span class="col-controls-label">Columns:</span>']
        for col, visible in columns.items():
            checked = " checked" if visible else ""
            label = _html.escape(labels.get(col, col))
            title_attr = ""
            if descs and col in descs:
                title_attr = f' title="{_html.escape(descs[col])}"'
            parts.append(
                f'<label{title_attr}><input type="checkbox" value="{col}"'
                f' onchange="toggleCol(\'{col}\', this.checked)"{checked}>'
                f' {label}</label>'
            )
        parts.append("</div>")
        return "".join(parts)

    def _help_popup_html(
        self,
        popup_id: str,
        columns: dict[str, bool],
        labels: dict[str, str],
        descs: dict[str, str],
    ) -> str:
        """Render the hidden help modal listing all columns and their descriptions."""
        items = []
        for col in columns:
            lbl = _html.escape(labels.get(col, col))
            desc = _html.escape(descs.get(col, ""))
            items.append(f"<dt>{lbl}</dt><dd>{desc}</dd>")
        dl = "".join(items)
        close_onclick = f"closeHelp('{popup_id}')"
        overlay_onclick = f"closeHelp('{popup_id}')"
        return (
            f'<div id="{popup_id}" class="help-overlay" onclick="{overlay_onclick}">'
            f'<div class="help-dialog" onclick="event.stopPropagation()">'
            f'<button class="help-close" onclick="{close_onclick}">&#x2715;</button>'
            f'<h2>Column Reference</h2>'
            f'<dl class="help-dl">{dl}</dl>'
            f'</div></div>'
        )

    @staticmethod
    def _c(col: str, columns: dict[str, bool]) -> str:
        """Return ' class="col-hidden"' when the column is configured as hidden."""
        return ' class="col-hidden"' if not columns.get(col, True) else ""

    @staticmethod
    def _color_level(pct: float) -> int:
        """Map a percentage [0, 100] to a colour level 0–9."""
        return min(9, int(pct / 10))

    @staticmethod
    def _bucket_level(value: float, max_value: float) -> int:
        """Map a value in [0, max_value] to a colour level 0–9."""
        if max_value <= 0:
            return 0
        return min(9, int(value / max_value * 10))

    def _collect_file_ranges(self, lines: list[LineReport]) -> dict[str, float]:
        """Find the max value per file-page column across all executable lines."""
        maxv: dict[str, float] = {
            "inc-exec": 0.0, "del-exec": 0.0,
            "inc-asserts": 0.0, "del-asserts": 0.0,
            "inc-tests": 0.0, "del-tests": 0.0,
        }
        for lr in lines:
            if not lr.executable:
                continue
            maxv["inc-exec"] = max(maxv["inc-exec"], lr.incidental_executions)
            maxv["del-exec"] = max(maxv["del-exec"], lr.deliberate_executions)
            maxv["inc-asserts"] = max(maxv["inc-asserts"], lr.incidental_asserts)
            maxv["del-asserts"] = max(maxv["del-asserts"], lr.deliberate_asserts)
            maxv["inc-tests"] = max(maxv["inc-tests"], lr.incidental_tests)
            maxv["del-tests"] = max(maxv["del-tests"], lr.deliberate_tests)
        return maxv

    def _collect_ranges(self, node: FolderNode) -> dict[str, float]:
        """DFS-collect max values for the range-bucketed index columns."""
        maxv: dict[str, float] = {
            "inc-asserts": 0.0, "del-asserts": 0.0,
            "inc-assert-density": 0.0, "del-assert-density": 0.0,
        }
        self._collect_ranges_rec(node, maxv)
        return maxv

    def _collect_ranges_rec(self, node: FolderNode, maxv: dict[str, float]) -> None:
        for sub in node.subfolders.values():
            row = sub.to_index_row()
            maxv["inc-asserts"] = max(maxv["inc-asserts"], row.incidental_asserts)
            maxv["del-asserts"] = max(maxv["del-asserts"], row.deliberate_asserts)
            maxv["inc-assert-density"] = max(maxv["inc-assert-density"], row.inc_assert_density)
            maxv["del-assert-density"] = max(maxv["del-assert-density"], row.del_assert_density)
            self._collect_ranges_rec(sub, maxv)
        for entry in node.files:
            row = entry.to_index_row()
            maxv["inc-asserts"] = max(maxv["inc-asserts"], row.incidental_asserts)
            maxv["del-asserts"] = max(maxv["del-asserts"], row.deliberate_asserts)
            maxv["inc-assert-density"] = max(maxv["inc-assert-density"], row.inc_assert_density)
            maxv["del-assert-density"] = max(maxv["del-assert-density"], row.del_assert_density)

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

        file_ranges = self._collect_file_ranges(file_report.lines)
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
            rows.append(self.render_line(
                lr.lineno, lr.source_text, ld, lr.executable,
                partial=lr.partial, _ranges=file_ranges,
            ))

        out_path.write_text(
            self.render_file_page(s.rel_path, stats_html, "".join(rows)), encoding="utf-8"
        )

    def _render_tree_rows(
        self, node: FolderNode, depth: int, parent_id: str,
        _ranges: dict[str, float] | None = None,
    ) -> list[str]:
        """DFS traversal: emit a folder row then its children (subfolders, then files)."""
        if _ranges is None:
            _ranges = self._collect_ranges(node)

        rows: list[str] = []
        parent_attr = f' data-parent="{parent_id}"' if parent_id else ""
        folder_indent = depth * 24 + 4
        file_indent = depth * 24 + 28
        fmt = f".{self.precision}f"
        idx = self.INDEX_COLUMNS

        def cell_cls(col: str, lvl: int | None = None) -> str:
            """Build class attribute for a data cell: col-hidden + optional colour level."""
            classes: list[str] = []
            if not idx.get(col, True):
                classes.append("col-hidden")
            if lvl is not None:
                classes.append(f"lvl-{lvl}")
            return f' class="{" ".join(classes)}"' if classes else ""

        for name in sorted(node.subfolders):
            sub = node.subfolders[name]
            fid = "f-" + sub.path.replace("/", "-").replace(".", "_")
            row = sub.to_index_row()
            tpct_lvl = self._color_level(row.total_pct)
            dpct_lvl = self._color_level(row.deliberate_pct)
            ipct_lvl = self._color_level(row.incidental_pct)
            rows.append(
                f'<tr id="{fid}" class="folder-row"{parent_attr}'
                f' onclick="toggleFolder(\'{fid}\')">'
                f'<td style="padding-left:{folder_indent}px">'
                f'<span class="toggle">&#x25bc;</span> {_html.escape(name)}/</td>'
                f'<td data-col="stmts"{cell_cls("stmts")}>{row.total_stmts}</td>'
                f'<td data-col="total-pct"{cell_cls("total-pct", tpct_lvl)}>{row.total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct"{cell_cls("delib-pct", dpct_lvl)}>{row.deliberate_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct"{cell_cls("incid-pct", ipct_lvl)}>{row.incidental_pct:{fmt}}%</td>'
                f'<td data-col="delib-covered"{cell_cls("delib-covered", dpct_lvl)}>{row.deliberate_covered}</td>'
                f'<td data-col="incid-covered"{cell_cls("incid-covered", ipct_lvl)}>{row.incidental_covered}</td>'
                f'<td data-col="inc-asserts"{cell_cls("inc-asserts", self._bucket_level(row.incidental_asserts, _ranges["inc-asserts"]))}>{row.incidental_asserts}</td>'
                f'<td data-col="del-asserts"{cell_cls("del-asserts", self._bucket_level(row.deliberate_asserts, _ranges["del-asserts"]))}>{row.deliberate_asserts}</td>'
                f'<td data-col="inc-assert-density"{cell_cls("inc-assert-density", self._bucket_level(row.inc_assert_density, _ranges["inc-assert-density"]))}>{row.inc_assert_density:{fmt}}</td>'
                f'<td data-col="del-assert-density"{cell_cls("del-assert-density", self._bucket_level(row.del_assert_density, _ranges["del-assert-density"]))}>{row.del_assert_density:{fmt}}</td>'
                f'</tr>'
            )
            rows.extend(self._render_tree_rows(sub, depth + 1, fid, _ranges))

        for entry in sorted(node.files, key=lambda f: f.rel_path):
            filename = entry.rel_path.split("/")[-1]
            file_html_name = entry.rel_path.replace("/", "__") + ".html"
            row = entry.to_index_row()
            tpct_lvl = self._color_level(row.total_pct)
            dpct_lvl = self._color_level(row.deliberate_pct)
            ipct_lvl = self._color_level(row.incidental_pct)
            rows.append(
                f'<tr{parent_attr}>'
                f'<td style="padding-left:{file_indent}px">'
                f'<a href="{_html.escape(file_html_name)}">{_html.escape(filename)}</a></td>'
                f'<td data-col="stmts"{cell_cls("stmts")}>{row.total_stmts}</td>'
                f'<td data-col="total-pct"{cell_cls("total-pct", tpct_lvl)}>{row.total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct"{cell_cls("delib-pct", dpct_lvl)}>{row.deliberate_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct"{cell_cls("incid-pct", ipct_lvl)}>{row.incidental_pct:{fmt}}%</td>'
                f'<td data-col="delib-covered"{cell_cls("delib-covered", dpct_lvl)}>{row.deliberate_covered}</td>'
                f'<td data-col="incid-covered"{cell_cls("incid-covered", ipct_lvl)}>{row.incidental_covered}</td>'
                f'<td data-col="inc-asserts"{cell_cls("inc-asserts", self._bucket_level(row.incidental_asserts, _ranges["inc-asserts"]))}>{row.incidental_asserts}</td>'
                f'<td data-col="del-asserts"{cell_cls("del-asserts", self._bucket_level(row.deliberate_asserts, _ranges["del-asserts"]))}>{row.deliberate_asserts}</td>'
                f'<td data-col="inc-assert-density"{cell_cls("inc-assert-density", self._bucket_level(row.inc_assert_density, _ranges["inc-assert-density"]))}>{row.inc_assert_density:{fmt}}</td>'
                f'<td data-col="del-assert-density"{cell_cls("del-assert-density", self._bucket_level(row.del_assert_density, _ranges["del-assert-density"]))}>{row.del_assert_density:{fmt}}</td>'
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
                    partial: bool = False, _ranges: dict[str, float] | None = None) -> str:
        escaped = _html.escape(source_text)
        branch_marker = '<td class="branch-warn" title="not all branches taken">⚑</td>' if partial else "<td></td>"
        fc = self.FILE_COLUMNS

        if not executable:
            c = self._c
            return (
                f'<tr>'
                f'<td>{lineno}</td>'
                f'{branch_marker}'
                f'<td><pre style="margin:0">{escaped}</pre></td>'
                f'<td data-col="inc-exec"{c("inc-exec", fc)}></td>'
                f'<td data-col="del-exec"{c("del-exec", fc)}></td>'
                f'<td data-col="inc-asserts"{c("inc-asserts", fc)}></td>'
                f'<td data-col="del-asserts"{c("del-asserts", fc)}></td>'
                f'<td data-col="inc-tests"{c("inc-tests", fc)}></td>'
                f'<td data-col="del-tests"{c("del-tests", fc)}></td>'
                f'</tr>'
            )

        if partial:
            css_class = "partial"
            ie = ld.incidental_executions if ld else 0
            de = ld.deliberate_executions if ld else 0
            ia = ld.incidental_asserts if ld else 0
            da = ld.deliberate_asserts if ld else 0
            it_ = ld.incidental_tests if ld else 0
            dt_ = ld.deliberate_tests if ld else 0
        elif ld is not None and ld.deliberate_executions > 0:
            css_class = "deliberate"
            ie, de, ia, da, it_, dt_ = (
                ld.incidental_executions, ld.deliberate_executions,
                ld.incidental_asserts, ld.deliberate_asserts,
                ld.incidental_tests, ld.deliberate_tests,
            )
        elif ld is not None and ld.incidental_executions > 0:
            css_class = "incidental"
            ie, de, ia, da, it_, dt_ = (
                ld.incidental_executions, ld.deliberate_executions,
                ld.incidental_asserts, ld.deliberate_asserts,
                ld.incidental_tests, ld.deliberate_tests,
            )
        else:
            css_class = "missed"
            ie = de = ia = da = it_ = dt_ = 0

        def cell(col: str, val: int) -> str:
            classes: list[str] = []
            if not fc.get(col, True):
                classes.append("col-hidden")
            if _ranges is not None:
                classes.append(f"lvl-{self._bucket_level(val, _ranges.get(col, 0.0))}")
            cls = f' class="{" ".join(classes)}"' if classes else ""
            return f'<td data-col="{col}"{cls}>{val}</td>'

        return (
            f'<tr class="{css_class}">'
            f'<td>{lineno}</td>'
            f'{branch_marker}'
            f'<td><pre style="margin:0">{escaped}</pre></td>'
            + cell("inc-exec", ie)
            + cell("del-exec", de)
            + cell("inc-asserts", ia)
            + cell("del-asserts", da)
            + cell("inc-tests", it_)
            + cell("del-tests", dt_)
            + '</tr>'
        )

    def render_index_page(self, rows_html: str) -> str:
        idx = self.INDEX_COLUMNS
        c = self._c
        col_controls = self._col_controls_html(idx, self.INDEX_COL_LABELS, self.INDEX_COL_DESCS)
        help_popup = self._help_popup_html(
            "index-help", idx, self.INDEX_COL_LABELS, self.INDEX_COL_DESCS
        )
        help_btn = '<button class="help-btn" onclick="openHelp(\'index-help\')">?</button>'
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
            f'<h1>Coverage Stats {help_btn}</h1>'
            f'{help_popup}'
            f'{col_controls}'
            f'<table>'
            f'<thead><tr>'
            f'<th>File</th>'
            f'<th data-col="stmts"{c("stmts", idx)}>Stmts</th>'
            f'<th data-col="total-pct"{c("total-pct", idx)}>Total %</th>'
            f'<th data-col="delib-pct"{c("delib-pct", idx)}>Deliberate %</th>'
            f'<th data-col="incid-pct"{c("incid-pct", idx)}>Incidental %</th>'
            f'<th data-col="delib-covered"{c("delib-covered", idx)}>Del. Covered</th>'
            f'<th data-col="incid-covered"{c("incid-covered", idx)}>Inc. Covered</th>'
            f'<th data-col="inc-asserts"{c("inc-asserts", idx)}>Inc. Asserts</th>'
            f'<th data-col="del-asserts"{c("del-asserts", idx)}>Del. Asserts</th>'
            f'<th data-col="inc-assert-density"{c("inc-assert-density", idx)}>Inc. Assert Density</th>'
            f'<th data-col="del-assert-density"{c("del-assert-density", idx)}>Del. Assert Density</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>'
            f'</body>'
            f'</html>'
        )

    def render_file_page(self, rel_path: str, stats_html: str, lines_html: str) -> str:
        escaped_path = _html.escape(rel_path)
        fc = self.FILE_COLUMNS
        c = self._c
        col_controls = self._col_controls_html(fc, self.FILE_COL_LABELS, self.FILE_COL_DESCS)
        help_popup = self._help_popup_html(
            "file-help", fc, self.FILE_COL_LABELS, self.FILE_COL_DESCS
        )
        help_btn = '<button class="help-btn" onclick="openHelp(\'file-help\')">?</button>'
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
            f'<h1>{escaped_path} {help_btn}</h1>'
            f'{help_popup}'
            f'<p><a href="index.html">Back to index</a></p>'
            f'{stats_html}'
            f'{col_controls}'
            f'<table>'
            f'<thead><tr>'
            f'<th>#</th><th></th><th>Source</th>'
            f'<th data-col="inc-exec"{c("inc-exec", fc)}>Incidental Executions</th>'
            f'<th data-col="del-exec"{c("del-exec", fc)}>Deliberate Executions</th>'
            f'<th data-col="inc-asserts"{c("inc-asserts", fc)}>Incidental Asserts</th>'
            f'<th data-col="del-asserts"{c("del-asserts", fc)}>Deliberate Asserts</th>'
            f'<th data-col="inc-tests"{c("inc-tests", fc)}>Incidental Tests</th>'
            f'<th data-col="del-tests"{c("del-tests", fc)}>Deliberate Tests</th>'
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
