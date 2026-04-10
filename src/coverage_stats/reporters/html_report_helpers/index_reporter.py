from __future__ import annotations

import html as _html

from coverage_stats.reporters.models import FolderNode, IndexRowData
from coverage_stats.reporters.html_report_helpers.mixins import HtmlReporterMixin


class IndexPageReporter(HtmlReporterMixin):
    """Renders the folder-tree index page."""

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
            "No color is applied \u2014 raw counts are not comparable across files of different sizes."
        ),
        "incid-covered": (
            "Raw count of statements + branches covered incidentally. "
            "No color is applied \u2014 raw counts are not comparable across files of different sizes."
        ),
        "inc-asserts": (
            "Total number of assert statements executed during incidental coverage "
            "of this file or folder. "
            "No color is applied \u2014 larger files will naturally accumulate higher counts "
            "regardless of test quality."
        ),
        "del-asserts": (
            "Total number of assert statements executed during deliberate coverage "
            "of this file or folder. "
            "No color is applied \u2014 larger files will naturally accumulate higher counts "
            "regardless of test quality."
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

    def _sort_data_attrs(self, row: IndexRowData, name: str) -> str:
        """Build data-sort-* attribute string for an index table row."""
        fmt = f".{self.precision}f"
        return (
            f' data-sort-name="{_html.escape(name)}"'
            f' data-sort-stmts="{row.total_stmts}"'
            f' data-sort-total-pct="{row.total_pct:{fmt}}"'
            f' data-sort-delib-pct="{row.deliberate_pct:{fmt}}"'
            f' data-sort-incid-pct="{row.incidental_pct:{fmt}}"'
            f' data-sort-delib-covered="{row.deliberate_covered}"'
            f' data-sort-incid-covered="{row.incidental_covered}"'
            f' data-sort-inc-asserts="{row.incidental_asserts}"'
            f' data-sort-del-asserts="{row.deliberate_asserts}"'
            f' data-sort-inc-assert-density="{row.inc_assert_density:{fmt}}"'
            f' data-sort-del-assert-density="{row.del_assert_density:{fmt}}"'
        )

    @staticmethod
    def _th_sort_cls(col: str, columns: dict[str, bool]) -> str:
        """Return class attribute for a sortable index <th>: always includes 'sortable'."""
        classes = "sortable" if columns.get(col, True) else "sortable col-hidden"
        return f' class="{classes}"'

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

    def _render_tree_rows(
        self, node: FolderNode, depth: int, parent_id: str,
        _ranges: dict[str, float] | None = None,
        _idx: list[int] | None = None,
    ) -> list[str]:
        """DFS traversal: emit a folder row then its children (subfolders, then files)."""
        if _ranges is None:
            _ranges = self._collect_ranges(node)
        if _idx is None:
            _idx = [0]

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
            sort_attrs = self._sort_data_attrs(row, name)
            orig_idx = _idx[0]
            _idx[0] += 1
            rows.append(
                f'<tr id="{fid}" class="folder-row"{parent_attr}'
                f' data-original-index="{orig_idx}"{sort_attrs}'
                f' onclick="toggleFolder(\'{fid}\')">'
                f'<td style="padding-left:{folder_indent}px">'
                f'<span class="toggle">&#x25bc;</span> {_html.escape(name)}/</td>'
                f'<td data-col="stmts"{cell_cls("stmts")}>{row.total_stmts}</td>'
                f'<td data-col="total-pct"{cell_cls("total-pct", tpct_lvl)}>{row.total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct"{cell_cls("delib-pct", dpct_lvl)}>{row.deliberate_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct"{cell_cls("incid-pct", ipct_lvl)}>{row.incidental_pct:{fmt}}%</td>'
                f'<td data-col="delib-covered"{cell_cls("delib-covered")}>{row.deliberate_covered}</td>'
                f'<td data-col="incid-covered"{cell_cls("incid-covered")}>{row.incidental_covered}</td>'
                f'<td data-col="inc-asserts"{cell_cls("inc-asserts")}>{row.incidental_asserts}</td>'
                f'<td data-col="del-asserts"{cell_cls("del-asserts")}>{row.deliberate_asserts}</td>'
                f'<td data-col="inc-assert-density"{cell_cls("inc-assert-density", self._bucket_level(row.inc_assert_density, _ranges["inc-assert-density"]))}>{row.inc_assert_density:{fmt}}</td>'
                f'<td data-col="del-assert-density"{cell_cls("del-assert-density", self._bucket_level(row.del_assert_density, _ranges["del-assert-density"]))}>{row.del_assert_density:{fmt}}</td>'
                f'</tr>'
            )
            rows.extend(self._render_tree_rows(sub, depth + 1, fid, _ranges, _idx))

        for entry in sorted(node.files, key=lambda f: f.rel_path):
            filename = entry.rel_path.split("/")[-1]
            file_html_name = entry.rel_path.replace("/", "__") + ".html"
            row = entry.to_index_row()
            tpct_lvl = self._color_level(row.total_pct)
            dpct_lvl = self._color_level(row.deliberate_pct)
            ipct_lvl = self._color_level(row.incidental_pct)
            sort_attrs = self._sort_data_attrs(row, filename)
            orig_idx = _idx[0]
            _idx[0] += 1
            rows.append(
                f'<tr{parent_attr} data-original-index="{orig_idx}"{sort_attrs}>'
                f'<td style="padding-left:{file_indent}px">'
                f'<a href="{_html.escape(file_html_name)}">{_html.escape(filename)}</a></td>'
                f'<td data-col="stmts"{cell_cls("stmts")}>{row.total_stmts}</td>'
                f'<td data-col="total-pct"{cell_cls("total-pct", tpct_lvl)}>{row.total_pct:{fmt}}%</td>'
                f'<td data-col="delib-pct"{cell_cls("delib-pct", dpct_lvl)}>{row.deliberate_pct:{fmt}}%</td>'
                f'<td data-col="incid-pct"{cell_cls("incid-pct", ipct_lvl)}>{row.incidental_pct:{fmt}}%</td>'
                f'<td data-col="delib-covered"{cell_cls("delib-covered")}>{row.deliberate_covered}</td>'
                f'<td data-col="incid-covered"{cell_cls("incid-covered")}>{row.incidental_covered}</td>'
                f'<td data-col="inc-asserts"{cell_cls("inc-asserts")}>{row.incidental_asserts}</td>'
                f'<td data-col="del-asserts"{cell_cls("del-asserts")}>{row.deliberate_asserts}</td>'
                f'<td data-col="inc-assert-density"{cell_cls("inc-assert-density", self._bucket_level(row.inc_assert_density, _ranges["inc-assert-density"]))}>{row.inc_assert_density:{fmt}}</td>'
                f'<td data-col="del-assert-density"{cell_cls("del-assert-density", self._bucket_level(row.del_assert_density, _ranges["del-assert-density"]))}>{row.del_assert_density:{fmt}}</td>'
                f'</tr>'
            )

        return rows

    def render_index_page(self, rows_html: str) -> str:
        idx = self.INDEX_COLUMNS
        sc = self._th_sort_cls
        col_controls = self._col_controls_html(idx, self.INDEX_COL_LABELS, self.INDEX_COL_DESCS)
        help_popup = self._help_popup_html(
            "index-help", idx, self.INDEX_COL_LABELS, self.INDEX_COL_DESCS
        )
        help_btn = '<button class="help-btn" onclick="openHelp(\'index-help\')">?</button>'
        onclick = 'onclick="tableSorter.handleClick(this)"'
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
            f'<table id="coverage-table">'
            f'<thead><tr>'
            f'<th class="sortable" data-col="name" {onclick}>File</th>'
            f'<th data-col="stmts"{sc("stmts", idx)} {onclick}>Stmts</th>'
            f'<th data-col="total-pct"{sc("total-pct", idx)} {onclick}>Total %</th>'
            f'<th data-col="delib-pct"{sc("delib-pct", idx)} {onclick}>Deliberate %</th>'
            f'<th data-col="incid-pct"{sc("incid-pct", idx)} {onclick}>Incidental %</th>'
            f'<th data-col="delib-covered"{sc("delib-covered", idx)} {onclick}>Del. Covered</th>'
            f'<th data-col="incid-covered"{sc("incid-covered", idx)} {onclick}>Inc. Covered</th>'
            f'<th data-col="inc-asserts"{sc("inc-asserts", idx)} {onclick}>Inc. Asserts</th>'
            f'<th data-col="del-asserts"{sc("del-asserts", idx)} {onclick}>Del. Asserts</th>'
            f'<th data-col="inc-assert-density"{sc("inc-assert-density", idx)} {onclick}>Inc. Assert Density</th>'
            f'<th data-col="del-assert-density"{sc("del-assert-density", idx)} {onclick}>Del. Assert Density</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>'
            f'</body>'
            f'</html>'
        )
