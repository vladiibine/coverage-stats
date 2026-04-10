from __future__ import annotations

import html as _html
from pathlib import Path

from coverage_stats.store import LineData
from coverage_stats.reporters.models import FileReport, LineReport
from coverage_stats.reporters.html_report_helpers.mixins import HtmlReporterMixin


class FilePageReporter(HtmlReporterMixin):
    """Renders individual file coverage pages."""

    # Map col-id → visible (True = shown by default, False = hidden by default).
    # Override in a subclass to change initial column visibility.
    FILE_COLUMNS: dict[str, bool] = {
        "inc-exec": True,
        "del-exec": True,
        "inc-asserts": True,
        "del-asserts": True,
        "inc-tests": True,
        "del-tests": True,
        "inc-test-ids": False,
        "del-test-ids": False,
    }

    # Human-readable labels for each column's checkbox. Override to rename.
    FILE_COL_LABELS: dict[str, str] = {
        "inc-exec": "Inc. Executions",
        "del-exec": "Del. Executions",
        "inc-asserts": "Inc. Asserts",
        "del-asserts": "Del. Asserts",
        "inc-tests": "# Inc. Tests",
        "del-tests": "# Del. Tests",
        "inc-test-ids": "Inc. Test IDs",
        "del-test-ids": "Del. Test IDs",
    }

    # Descriptions shown as tooltips on checkbox labels and in the help popup.
    # Override in a subclass to customise the documentation.
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
        "inc-test-ids": (
            "Node IDs of all incidental tests that executed this line. "
            "Empty only when --coverage-stats-no-track-test-ids is set."
        ),
        "del-test-ids": (
            "Node IDs of all deliberate tests that executed this line. "
            "Empty only when --coverage-stats-no-track-test-ids is set."
        ),
    }

    def _render_test_ids_cell(
        self, col: str, val: int, test_ids: set[str] | frozenset[str],
        _ranges: dict[str, float] | None,
    ) -> str:
        """Render a test-count cell with an optional expandable list of test node IDs.

        When *test_ids* is non-empty (i.e. --coverage-stats-no-track-test-ids is not set),
        the count is wrapped in a <details> element so the user can expand it to see
        the full list of test node IDs.  When empty, just the integer count is shown.
        """
        classes: list[str] = []
        fc = self.FILE_COLUMNS
        if not fc.get(col, True):
            classes.append("col-hidden")
        if _ranges is not None:
            classes.append(f"lvl-{self._bucket_level(val, _ranges.get(col, 0.0))}")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        if test_ids:
            items = "".join(
                f'<li>{_html.escape(tid)}</li>' for tid in sorted(test_ids)
            )
            content = (
                f'<details>'
                f'<summary>{val}</summary>'
                f'<ul class="test-id-list">{items}</ul>'
                f'</details>'
            )
        else:
            content = str(val)
        return f'<td data-col="{col}"{cls}>{content}</td>'

    def _render_test_id_list_cell(self, col: str, test_ids: set[str] | frozenset[str]) -> str:
        """Render a dedicated test-ID list cell (inc-test-ids / del-test-ids columns).

        Unlike _render_test_ids_cell, no <details> wrapper is used — the column
        exists solely to display the IDs, so the list is shown directly.
        The cell is empty when IDs are not tracked.
        """
        classes: list[str] = []
        fc = self.FILE_COLUMNS
        if not fc.get(col, True):
            classes.append("col-hidden")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        if test_ids:
            items = "".join(f'<li>{_html.escape(tid)}</li>' for tid in sorted(test_ids))
            content = f'<ul class="test-id-list">{items}</ul>'
        else:
            content = ""
        return f'<td data-col="{col}"{cls}>{content}</td>'

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
                f'<td data-col="inc-test-ids"{c("inc-test-ids", fc)}></td>'
                f'<td data-col="del-test-ids"{c("del-test-ids", fc)}></td>'
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

        iids: set[str] = ld.incidental_test_ids if ld is not None else set()
        dids: set[str] = ld.deliberate_test_ids if ld is not None else set()

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
            + self._render_test_ids_cell("inc-tests", it_, iids, _ranges)
            + self._render_test_ids_cell("del-tests", dt_, dids, _ranges)
            + self._render_test_id_list_cell("inc-test-ids", iids)
            + self._render_test_id_list_cell("del-test-ids", dids)
            + '</tr>'
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
            f'<th data-col="inc-tests"{c("inc-tests", fc)}># Incidental Tests</th>'
            f'<th data-col="del-tests"{c("del-tests", fc)}># Deliberate Tests</th>'
            f'<th data-col="inc-test-ids"{c("inc-test-ids", fc)}>Incidental Test IDs</th>'
            f'<th data-col="del-test-ids"{c("del-test-ids", fc)}>Deliberate Test IDs</th>'
            f'</tr></thead>'
            f'<tbody>{lines_html}</tbody>'
            f'</table>'
            f'</body>'
            f'</html>'
        )

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
                    incidental_test_ids=set(lr.incidental_test_ids),
                    deliberate_test_ids=set(lr.deliberate_test_ids),
                )
            rows.append(self.render_line(
                lr.lineno, lr.source_text, ld, lr.executable,
                partial=lr.partial, _ranges=file_ranges,
            ))

        out_path.write_text(
            self.render_file_page(s.rel_path, stats_html, "".join(rows)), encoding="utf-8"
        )
