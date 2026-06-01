# Business Process Modeling Assignments

This repo contains the source files, exported evidence, and compiled review PDFs for the BPM assignments.

## Folder Structure

- `LECS/` -- lecture PDFs used for BPMN, Petri nets, process analysis, and process mining concepts.
- `assignment.txt` -- original assignment brief.
- `data/` -- structured event log for Assignment 2.
- `tools/` -- Python generators/automation.
- `output/` -- generated BPMN, Petri-net, process-mining, and PERT evidence files.
- `screenshots/` -- SVG diagram exports and the terminal PNG evidence.
- `reports/` -- LaTeX report sources, shared style, generated SVG cache PDFs, and compiled reports.

## Current State

- Assignment 1 includes both BPMN 2.0 and Petri-net approaches, with BPMN collaboration pools, internal e-commerce lanes, straight dashed message flows, data artifacts, corrected split/join behavior, explicit send/receive status tasks, normal Petri transitions, and delayed-goods loops.
- Assignment 2 includes the Alpha algorithm explanation, exact computations, a timed PERT/event-network with critical path, and automation evidence.
- Diagram evidence is exported as SVG, then rendered with Chrome into `reports/svg-cache/*.pdf` so LaTeX does not need TikZ, Inkscape, or shell escape.
- Wide diagrams are placed on dedicated landscape pages with no visible caption, header, footer, or other report content.
- The compiled review PDFs are:
  - `reports/assignment1_report.pdf`
  - `reports/assignment2_report.pdf`
- The submission ZIP is `BPM_submission.zip`, built from the `submition/` review folder.

## Rebuild Commands

From the repo root:

```bash
python3 tools/generate_assignment1_bpmn.py
python3 tools/render_assignment1_svgs.py
python3 tools/process_mining_alpha.py --input data/event_log.csv --output-dir output
cp output/assignment2_pert.svg screenshots/assignment2/pert_chart.svg
python3 tools/convert_svg_exports.py
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/assignment1_report.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/assignment1_report.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/assignment2_report.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports reports/assignment2_report.tex
rm -f reports/*.aux reports/*.log reports/*.out reports/*.toc reports/*.lof reports/*.lot reports/*.fls reports/*.fdb_latexmk reports/*.synctex.gz
rm -rf tools/__pycache__
```

Use `screenshots/README.md` when replacing or re-exporting any diagram images.
