"""
HTML reporter: generates an enhanced coverage report from FileStats.

Each line shows:
  - The source line
  - Total execution count
  - Direct hits  (from @covers tests)
  - Incidental hits (from other tests)

Color legend:
  - Green   : line has direct hits
  - Yellow  : line has only incidental hits
  - Red     : executable line, zero hits
  - Default : non-executable (not in coverage data)
"""
from __future__ import annotations

import html
import os
from pathlib import Path

from coverage_stats.analyzer import FileStats

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", monospace; font-size: 13px; background: #f8f9fa; color: #212529; }
h1 { padding: 20px 24px 8px; font-size: 20px; font-weight: 600; }
.summary { padding: 0 24px 16px; color: #6c757d; font-size: 12px; }
.legend { display: flex; gap: 16px; padding: 0 24px 20px; font-size: 12px; }
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 2px; border: 1px solid rgba(0,0,0,.12); }
.files { padding: 0 24px 40px; }
.file-block { background: #fff; border: 1px solid #dee2e6; border-radius: 6px; margin-bottom: 24px; overflow: hidden; }
.file-header { background: #e9ecef; padding: 10px 16px; font-weight: 600; font-size: 13px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }
.file-header:hover { background: #dee2e6; }
.file-meta { font-size: 11px; color: #6c757d; font-weight: normal; display: flex; gap: 14px; }
table { width: 100%; border-collapse: collapse; font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }
tr.covered-direct   { background: #d4edda; }
tr.covered-incident { background: #fff3cd; }
tr.not-covered      { background: #f8d7da; }
tr.not-executable   { background: #fff; }
td { padding: 1px 4px; vertical-align: top; white-space: pre; }
td.lineno { color: #adb5bd; text-align: right; min-width: 40px; user-select: none; border-right: 1px solid #dee2e6; padding-right: 8px; }
td.counts { min-width: 130px; text-align: right; border-right: 1px solid #dee2e6; padding-right: 8px; font-size: 11px; color: #495057; }
td.counts span { display: inline-block; min-width: 30px; }
td.source { padding-left: 12px; }
.count-direct   { color: #155724; font-weight: 600; }
.count-incident { color: #856404; }
.count-zero     { color: #721c24; }
.count-label    { color: #adb5bd; font-size: 10px; }
.collapsed tbody { display: none; }
"""

_JS = """
document.querySelectorAll('.file-header').forEach(h => {
  h.addEventListener('click', () => {
    h.closest('.file-block').classList.toggle('collapsed');
  });
});
"""


def _row_class(direct: int, incidental: int, executable: bool) -> str:
    if not executable:
        return "not-executable"
    if direct > 0:
        return "covered-direct"
    if incidental > 0:
        return "covered-incident"
    return "not-covered"


def _counts_cell(direct: int, incidental: int, executable: bool) -> str:
    if not executable:
        return '<td class="counts"></td>'
    parts = []
    d_cls = "count-direct" if direct > 0 else "count-zero"
    i_cls = "count-incident" if incidental > 0 else "count-zero"
    parts.append(f'<span class="{d_cls}" title="direct hits">{direct}</span>')
    parts.append('<span class="count-label">d</span>')
    parts.append(f'<span class="{i_cls}" title="incidental hits">&nbsp;{incidental}</span>')
    parts.append('<span class="count-label">i</span>')
    return f'<td class="counts">{"".join(parts)}</td>'


def _file_block(file_stats: FileStats) -> str:
    lines = file_stats.source_lines
    lineno_map = file_stats.lines

    total_executable = len(lineno_map)
    total_direct = sum(1 for s in lineno_map.values() if s.direct > 0)
    total_incidental = sum(1 for s in lineno_map.values() if s.direct == 0 and s.incidental > 0)
    total_missed = sum(1 for s in lineno_map.values() if s.total == 0)

    short_path = file_stats.path
    # Try to make path relative to cwd.
    try:
        short_path = str(Path(file_stats.path).relative_to(Path.cwd()))
    except ValueError:
        pass

    meta_html = (
        f'<span title="lines with direct @covers hits">{total_direct} direct</span>'
        f'<span title="lines with only incidental hits">{total_incidental} incidental</span>'
        f'<span title="executable lines with zero hits">{total_missed} missed</span>'
        f'<span>{total_executable} executable</span>'
    )

    rows: list[str] = []
    for i, source_line in enumerate(lines, start=1):
        stats = lineno_map.get(i)
        executable = stats is not None
        direct = stats.direct if stats else 0
        incidental = stats.incidental if stats else 0

        row_cls = _row_class(direct, incidental, executable)
        counts_td = _counts_cell(direct, incidental, executable)
        source_html = html.escape(source_line.rstrip("\n"))

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td class="lineno">{i}</td>'
            f'{counts_td}'
            f'<td class="source">{source_html}</td>'
            f"</tr>"
        )

    return f"""
<div class="file-block">
  <div class="file-header">
    <span>{html.escape(short_path)}</span>
    <span class="file-meta">{meta_html}</span>
  </div>
  <table><tbody>{"".join(rows)}</tbody></table>
</div>"""


def generate_html(
    file_stats_list: list[FileStats],
    output_dir: str | Path = "htmlcov_stats",
    title: str = "Coverage Stats",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(file_stats_list)
    total_direct = sum(
        sum(1 for s in fs.lines.values() if s.direct > 0) for fs in file_stats_list
    )
    total_lines = sum(len(fs.lines) for fs in file_stats_list)

    file_blocks = "".join(_file_block(fs) for fs in sorted(file_stats_list, key=lambda f: f.path))

    legend = """
<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#d4edda"></div> Direct coverage (@covers)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#fff3cd"></div> Incidental coverage</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#f8d7da"></div> Not covered</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#fff; border:1px solid #dee2e6"></div> Non-executable</div>
</div>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="summary">
    {total_files} file{"s" if total_files != 1 else ""} &nbsp;|&nbsp;
    {total_lines} executable lines &nbsp;|&nbsp;
    {total_direct} lines with direct coverage
  </p>
  {legend}
  <div class="files">{file_blocks}</div>
  <script>{_JS}</script>
</body>
</html>"""

    out_path = output_dir / "index.html"
    out_path.write_text(html_content, encoding="utf-8")
    return out_path
