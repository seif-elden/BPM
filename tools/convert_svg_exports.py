#!/usr/bin/env python3
"""Render exported SVG diagrams into LaTeX-ready PDF cache files.

The report sources keep SVG as the original evidence format.  This script uses
Chrome's SVG renderer to create PDF cache files because generic converters can
drop BPMN arrow markers or Mermaid foreignObject text.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Diagram:
    source: Path
    output: Path


DIAGRAMS = (
    Diagram(
        ROOT / "screenshots/assignment1/as_is_bpmn.svg",
        ROOT / "reports/svg-cache/as_is_bpmn.pdf",
    ),
    Diagram(
        ROOT / "screenshots/assignment1/to_be_bpmn.svg",
        ROOT / "reports/svg-cache/to_be_bpmn.pdf",
    ),
    Diagram(
        ROOT / "screenshots/assignment1/as_is_petri_net.svg",
        ROOT / "reports/svg-cache/as_is_petri_net.pdf",
    ),
    Diagram(
        ROOT / "screenshots/assignment1/to_be_petri_net.svg",
        ROOT / "reports/svg-cache/to_be_petri_net.pdf",
    ),
    Diagram(
        ROOT / "screenshots/assignment2/pert_chart.svg",
        ROOT / "reports/svg-cache/pert_chart.pdf",
    ),
)


def find_chrome(explicit_path: str | None) -> str:
    candidates = [
        explicit_path,
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    raise SystemExit("Chrome/Chromium was not found on PATH.")


def extract_svg(svg_text: str) -> str:
    start = svg_text.find("<svg")
    end = svg_text.rfind("</svg>")
    if start == -1 or end == -1:
        raise ValueError("No complete <svg>...</svg> element found.")
    return svg_text[start : end + len("</svg>")]


def viewbox_size(svg: str) -> tuple[float, float]:
    viewbox = re.search(r'viewBox="([^"]+)"', svg)
    if viewbox:
        values = [float(value) for value in re.split(r"[\s,]+", viewbox.group(1).strip())]
        if len(values) == 4 and values[2] > 0 and values[3] > 0:
            return values[2], values[3]

    width = re.search(r'width="([0-9.]+)', svg)
    height = re.search(r'height="([0-9.]+)', svg)
    if width and height:
        return float(width.group(1)), float(height.group(1))

    raise ValueError("SVG is missing a usable viewBox or numeric width/height.")


def html_wrapper(svg: str, width: float, height: float) -> str:
    aspect_ratio = width / height
    page_width_in = 18.0
    page_height_in = page_width_in / aspect_ratio
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{
      size: {page_width_in:.4f}in {page_height_in:.4f}in;
      margin: 0;
    }}
    html,
    body {{
      width: {page_width_in:.4f}in;
      height: {page_height_in:.4f}in;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: #ffffff;
    }}
    svg {{
      display: block !important;
      width: 100% !important;
      height: 100% !important;
      max-width: none !important;
      background: #ffffff !important;
    }}
  </style>
</head>
<body>
{svg}
</body>
</html>
"""


def render_diagram(chrome: str, diagram: Diagram, tmpdir: Path) -> None:
    if not diagram.source.exists():
        raise FileNotFoundError(diagram.source)

    svg = extract_svg(diagram.source.read_text(encoding="utf-8", errors="ignore"))
    width, height = viewbox_size(svg)
    html_path = tmpdir / f"{diagram.output.stem}.html"
    html_path.write_text(html_wrapper(svg, width, height), encoding="utf-8")

    diagram.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={diagram.output}",
            html_path.as_uri(),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome", help="Path to Chrome/Chromium binary.")
    args = parser.parse_args()

    chrome = find_chrome(args.chrome)
    with tempfile.TemporaryDirectory(prefix="bpm-svg-cache-") as tmp:
        tmpdir = Path(tmp)
        for diagram in DIAGRAMS:
            render_diagram(chrome, diagram, tmpdir)
            print(f"rendered {diagram.output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
