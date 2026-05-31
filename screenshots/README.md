# Screenshot / Export Instructions

Save exports with the exact filenames below. Model diagrams must be exported as **SVG** so zoom quality stays sharp in the final PDF. The terminal automation evidence stays **PNG** because it is a screenshot.

## Assignment 1

The current Assignment 1 SVG evidence can be regenerated from the checked-in BPMN/Petri sources:

```bash
python3 tools/generate_assignment1_bpmn.py
python3 tools/render_assignment1_svgs.py
```

For manual online-tool exports, use these filenames:

1. Open <https://demo.bpmn.io/>.
2. Import `output/assignment1_epurchase_as_is.bpmn`.
3. Export SVG from the tool menu.
4. Save it as `screenshots/assignment1/as_is_bpmn.svg`.
5. Repeat with `output/assignment1_epurchase_to_be.bpmn` and save as `screenshots/assignment1/to_be_bpmn.svg`.
6. Open <https://dreampuf.github.io/GraphvizOnline/> or diagrams.net.
7. Paste/import `output/assignment1_epurchase_as_is_petri.dot`, export SVG, and save as `screenshots/assignment1/as_is_petri_net.svg`.
8. Repeat with `output/assignment1_epurchase_to_be_petri.dot` and save as `screenshots/assignment1/to_be_petri_net.svg`.

## Assignment 2

1. Run this command from the repo root:

   ```bash
   python3 tools/process_mining_alpha.py --input data/event_log.csv --output-dir output
   ```

2. Copy the generated timed PERT SVG into the screenshot folder:

   ```bash
   cp output/assignment2_pert.svg screenshots/assignment2/pert_chart.svg
   ```

3. Screenshot the terminal showing the command and successful output, plus generated files if visible.
4. Save it as `screenshots/assignment2/automation_run.png`.

The Mermaid source `output/assignment2_pert.mmd` can also be opened in <https://mermaid.live/> if a manual online export is needed.

## After Replacing SVGs

Regenerate the report cache:

```bash
python3 tools/convert_svg_exports.py
```

Then compile the reports from the repo root. The reports include `reports/svg-cache/*.pdf`, which are generated from the SVGs by Chrome so the final PDFs do not depend on Inkscape or LaTeX shell escape.

In the final PDFs, wide SVG diagrams are placed on clean landscape pages with no report header, footer, visible caption, or extra text on the same page.
