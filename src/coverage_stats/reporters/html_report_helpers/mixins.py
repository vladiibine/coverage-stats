from __future__ import annotations

import html as _html
from importlib.resources import files as _res_files


def _load_asset(filename: str) -> str:
    return _res_files(__package__).joinpath(filename).read_text(encoding="utf-8")


class HtmlReporterMixin:
    """Shared assets and utility methods inherited by both page reporter classes."""

    CSS: str = _load_asset("style.css")
    JS: str = _load_asset("script.js")
    EXTRA_CSS: str = ""
    EXTRA_JS: str = ""

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
