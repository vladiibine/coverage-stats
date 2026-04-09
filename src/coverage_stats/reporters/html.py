from __future__ import annotations

from pathlib import Path

from coverage_stats.store import LineData
from coverage_stats.reporters.models import CoverageReport, FolderNode
from coverage_stats.reporters.html_report_helpers.file_reporter import FilePageReporter
from coverage_stats.reporters.html_report_helpers.index_reporter import IndexPageReporter


class HtmlReporter:
    """The HTML reporter. Made for extensibility.

    To extend it, subclass it in your own project and run pytest like this:
        `pytest ... --coverage-stats-reporter my_module.MyCustomHtmlReporter`

    To customise only one page type, subclass the relevant reporter and override
    the corresponding factory method:

        class MyIndexReporter(IndexPageReporter):
            INDEX_COLUMNS = {**IndexPageReporter.INDEX_COLUMNS, "inc-asserts": True}

        class MyReporter(HtmlReporter):
            def get_index_reporter(self):
                return MyIndexReporter(precision=self.precision)
    """

    def __init__(self, precision: int = 1) -> None:
        self.precision = precision

    # ------------------------------------------------------------------
    # Factory methods — override to inject custom sub-reporter classes.
    # ------------------------------------------------------------------

    def get_index_reporter(self) -> IndexPageReporter:
        """Return the reporter instance used to render the index page."""
        r = IndexPageReporter(precision=self.precision)
        return r

    def get_file_reporter(self) -> FilePageReporter:
        """Return the reporter instance used to render individual file pages."""
        r = FilePageReporter(precision=self.precision)
        return r

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def write(self, report: CoverageReport, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_reporter = self.get_file_reporter()
        index_reporter = self.get_index_reporter()

        for fr in report.files:
            file_html_name = fr.summary.rel_path.replace("/", "__") + ".html"
            file_reporter._write_file_page(fr, output_dir / file_html_name)

        rows_html = "".join(index_reporter._render_tree_rows(report.root, depth=0, parent_id=""))
        (output_dir / "index.html").write_text(
            index_reporter.render_index_page(rows_html), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Delegation methods — preserve backward-compatible call surface so
    # that existing code calling these on an HtmlReporter instance works.
    # ------------------------------------------------------------------

    def render_index_page(self, rows_html: str) -> str:
        return self.get_index_reporter().render_index_page(rows_html)

    def render_file_page(self, rel_path: str, stats_html: str, lines_html: str) -> str:
        return self.get_file_reporter().render_file_page(rel_path, stats_html, lines_html)

    def render_file_stats(self, total_stmts: int, covered: int, total_pct: float,
                          deliberate_cnt: int, deliberate_pct: float,
                          incidental_cnt: int, incidental_pct: float,
                          partial_cnt: int = 0) -> str:
        return self.get_file_reporter().render_file_stats(
            total_stmts, covered, total_pct,
            deliberate_cnt, deliberate_pct,
            incidental_cnt, incidental_pct,
            partial_cnt,
        )

    def render_line(self, lineno: int, source_text: str, ld: LineData | None,
                    executable: bool, partial: bool = False,
                    _ranges: dict[str, float] | None = None) -> str:
        return self.get_file_reporter().render_line(
            lineno, source_text, ld, executable, partial, _ranges
        )

    def _render_tree_rows(
        self, node: FolderNode, depth: int, parent_id: str,
        _ranges: dict[str, float] | None = None,
    ) -> list[str]:
        return self.get_index_reporter()._render_tree_rows(node, depth, parent_id, _ranges)

    def _write_file_page(self, file_report: object, out_path: Path) -> None:
        return self.get_file_reporter()._write_file_page(file_report, out_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Module-level shims — delegate to default instances so that existing call
# sites (including tests) continue to work unchanged.
# ---------------------------------------------------------------------------

def write_html(report: CoverageReport, output_dir: Path, precision: int = 1) -> None:
    HtmlReporter(precision=precision).write(report, output_dir)


def render_line(lineno: int, source_text: str, ld: LineData | None, executable: bool,
                partial: bool = False) -> str:
    return FilePageReporter().render_line(lineno, source_text, ld, executable, partial)


def render_file_stats(total_stmts: int, covered: int, total_pct: float,
                      deliberate_cnt: int, deliberate_pct: float,
                      incidental_cnt: int, incidental_pct: float,
                      partial_cnt: int = 0, precision: int = 1) -> str:
    return FilePageReporter(precision=precision).render_file_stats(
        total_stmts, covered, total_pct,
        deliberate_cnt, deliberate_pct,
        incidental_cnt, incidental_pct,
        partial_cnt,
    )


def render_index_page(rows_html: str) -> str:
    return IndexPageReporter().render_index_page(rows_html)


def render_file_page(rel_path: str, stats_html: str, lines_html: str) -> str:
    return FilePageReporter().render_file_page(rel_path, stats_html, lines_html)


def _render_tree_rows(node: FolderNode, depth: int, parent_id: str, precision: int = 1) -> list[str]:
    return IndexPageReporter(precision=precision)._render_tree_rows(node, depth, parent_id)
