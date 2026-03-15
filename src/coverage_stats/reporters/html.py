from __future__ import annotations

import html as _html
from collections import defaultdict
from pathlib import Path
import pytest

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
}
tr.deliberate {
    background: #c8e6c9;
}
tr.incidental {
    background: #fff9c4;
}
details {
    margin-bottom: 1rem;
}
summary {
    cursor: pointer;
    font-weight: bold;
    padding: 0.25rem 0.5rem;
    background: #e8e8e8;
}
a {
    color: #1565c0;
}
"""


def render_line(lineno: int, source_text: str, ld: LineData) -> str:
    if ld.deliberate_executions > 0:
        css_class = "deliberate"
    elif ld.incidental_executions > 0:
        css_class = "incidental"
    else:
        css_class = ""
    escaped = _html.escape(source_text)
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<tr{class_attr}>'
        f'<td>{lineno}</td>'
        f'<td><pre style="margin:0">{escaped}</pre></td>'
        f'<td>{ld.incidental_executions}</td>'
        f'<td>{ld.deliberate_executions}</td>'
        f'<td>{ld.incidental_asserts}</td>'
        f'<td>{ld.deliberate_asserts}</td>'
        f'</tr>'
    )


def render_file_row(rel_path: str, lines: dict[int, LineData], file_html_name: str, total_source_lines: int) -> str:
    total_lines = total_source_lines
    deliberate_covered = sum(1 for ld in lines.values() if ld.deliberate_executions > 0)
    incidental_covered = sum(1 for ld in lines.values() if ld.incidental_executions > 0)
    deliberate_pct = deliberate_covered / total_lines * 100.0 if total_lines else 0.0
    incidental_pct = incidental_covered / total_lines * 100.0 if total_lines else 0.0
    escaped_path = _html.escape(rel_path)
    escaped_name = _html.escape(file_html_name)
    return (
        f'<tr>'
        f'<td><a href="{escaped_name}">{escaped_path}</a></td>'
        f'<td>{total_lines}</td>'
        f'<td>{deliberate_pct:.1f}%</td>'
        f'<td>{incidental_pct:.1f}%</td>'
        f'</tr>'
    )


def render_folder_section(folder_name: str, file_rows_html: str) -> str:
    escaped_folder = _html.escape(folder_name)
    return (
        f'<details open>'
        f'<summary>{escaped_folder}</summary>'
        f'<table>'
        f'<thead><tr>'
        f'<th>File</th><th>Lines</th><th>Deliberate %</th><th>Incidental %</th>'
        f'</tr></thead>'
        f'<tbody>{file_rows_html}</tbody>'
        f'</table>'
        f'</details>'
    )


def render_index_page(folder_sections_html: str) -> str:
    return (
        f'<!DOCTYPE html>'
        f'<html lang="en">'
        f'<head>'
        f'<meta charset="utf-8">'
        f'<title>Coverage Stats</title>'
        f'<style>{_CSS}</style>'
        f'</head>'
        f'<body>'
        f'<h1>Coverage Stats</h1>'
        f'{folder_sections_html}'
        f'</body>'
        f'</html>'
    )


def render_file_page(rel_path: str, lines_html: str) -> str:
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
        f'<table>'
        f'<thead><tr>'
        f'<th>#</th><th>Source</th>'
        f'<th>Incidental Executions</th><th>Deliberate Executions</th>'
        f'<th>Incidental Asserts</th><th>Deliberate Asserts</th>'
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


def _group_by_folder(files: dict[str, dict[int, LineData]]) -> dict[str, dict[str, dict[int, LineData]]]:
    folders: dict[str, dict[str, dict[int, LineData]]] = defaultdict(dict)
    for rel_path, lines in files.items():
        folder = str(Path(rel_path).parent)
        folders[folder][rel_path] = lines
    return folders


def _write_file_page(rel_path: str, lines: dict[int, LineData], abs_path: str, out_path: Path) -> None:
    try:
        source_lines = Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines()
        source_map = {i + 1: line for i, line in enumerate(source_lines)}
        all_linenos: list[int] = list(range(1, len(source_lines) + 1))
    except Exception:
        source_map = {}
        all_linenos = sorted(lines.keys())

    rows = []
    for lineno in all_linenos:
        ld = lines.get(lineno, LineData())
        source_text = source_map.get(lineno, "")
        rows.append(render_line(lineno, source_text, ld))

    out_path.write_text(render_file_page(rel_path, "".join(rows)), encoding="utf-8")


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

    folder_sections = []
    for folder, folder_files in sorted(_group_by_folder(files).items()):
        file_rows = []
        for rel_path, lines in sorted(folder_files.items()):
            file_html_name = rel_path.replace("/", "__") + ".html"
            abs_path = abs_path_map.get(rel_path, rel_path)
            try:
                total_source_lines = len(Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                total_source_lines = len(lines)
            _write_file_page(rel_path, lines, abs_path, output_dir / file_html_name)
            file_rows.append(render_file_row(rel_path, lines, file_html_name, total_source_lines))
        folder_sections.append(render_folder_section(folder, "".join(file_rows)))

    (output_dir / "index.html").write_text(
        render_index_page("".join(folder_sections)), encoding="utf-8"
    )
