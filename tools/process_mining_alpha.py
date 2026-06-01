#!/usr/bin/env python3
"""Alpha-algorithm Petri-net mining helper for Assignment 2.

The script is dependency-free and can be rerun on any CSV with the columns:
case_id, timestamp, activity, resource. It implements the lecture workflow:

1. Get process instances.
2. Project each instance into directly-following activity pairs.
3. Aggregate the projected relations.
4. Derive Alpha relations and maximal places.
5. Map the result onto a Petri net.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TIME_FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Event:
    event_id: str
    case_id: str
    timestamp: datetime
    activity: str
    resource: str


@dataclass(frozen=True)
class PetriPlace:
    place_id: str
    label: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class PetriNet:
    places: list[PetriPlace]
    transitions: list[str]
    arcs: list[tuple[str, str]]
    initial_place: str
    final_places: set[str]


SHORT = {
    "Check stock availability": "Check stock",
    "Retrieve product from warehouse": "Retrieve item",
    "Check materials availability": "Check materials",
    "Request raw materials": "Request materials",
    "Obtain raw materials": "Obtain materials",
    "Manufacture product": "Manufacture",
    "Confirm order": "Confirm order",
    "Get shipping address": "Get address",
    "Emit invoice": "Emit invoice",
    "Receive payment": "Receive payment",
    "Ship product": "Ship product",
    "Archive order": "Archive order",
}


TRANSITION_COLUMNS = {
    "Check stock availability": 1,
    "Retrieve product from warehouse": 2,
    "Check materials availability": 2,
    "Request raw materials": 3,
    "Obtain raw materials": 4,
    "Manufacture product": 5,
    "Confirm order": 6,
    "Get shipping address": 7,
    "Emit invoice": 7,
    "Receive payment": 8,
    "Ship product": 8,
    "Archive order": 9,
}

TRANSITION_ROWS = {
    "Check stock availability": 2,
    "Retrieve product from warehouse": 1,
    "Check materials availability": 3,
    "Request raw materials": 3,
    "Obtain raw materials": 3,
    "Manufacture product": 3,
    "Confirm order": 2,
    "Get shipping address": 3,
    "Emit invoice": 1,
    "Receive payment": 1,
    "Ship product": 3,
    "Archive order": 2,
}


def case_sort_key(case_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(case_id))
    except ValueError:
        return (1, case_id)


def read_log(path: Path) -> dict[str, list[Event]]:
    cases: dict[str, list[Event]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"case_id", "timestamp", "activity", "resource"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required CSV columns: {sorted(missing)}")
        for row in reader:
            event = Event(
                event_id=row.get("event_id", ""),
                case_id=row["case_id"],
                timestamp=datetime.strptime(row["timestamp"], TIME_FMT),
                activity=row["activity"],
                resource=row["resource"],
            )
            cases[event.case_id].append(event)
    return {
        case_id: sorted(events, key=lambda event: event.timestamp)
        for case_id, events in cases.items()
    }


def pairs_directly_follow(cases: dict[str, list[Event]]) -> Counter[tuple[str, str]]:
    follows: Counter[tuple[str, str]] = Counter()
    for events in cases.values():
        for left, right in zip(events, events[1:]):
            follows[(left.activity, right.activity)] += 1
    return follows


def relation_sets(tasks: set[str], follows: Counter[tuple[str, str]]):
    causality: set[tuple[str, str]] = set()
    parallel: set[tuple[str, str]] = set()
    choice: set[tuple[str, str]] = set()
    for a, b in itertools.permutations(tasks, 2):
        ab = follows[(a, b)] > 0
        ba = follows[(b, a)] > 0
        if ab and not ba:
            causality.add((a, b))
        elif ab and ba:
            parallel.add((a, b))
        elif not ab and not ba:
            choice.add((a, b))
    return causality, parallel, choice


def non_empty_subsets(items: list[str]):
    for size in range(1, len(items) + 1):
        yield from itertools.combinations(items, size)


def alpha_places(
    tasks: set[str],
    causality: set[tuple[str, str]],
    choice: set[tuple[str, str]],
) -> list[tuple[frozenset[str], frozenset[str]]]:
    """Return maximal Alpha-algorithm pairs (A, B)."""
    task_list = sorted(tasks)
    candidates: list[tuple[frozenset[str], frozenset[str]]] = []
    for left in non_empty_subsets(task_list):
        left_set = frozenset(left)
        for right in non_empty_subsets(task_list):
            right_set = frozenset(right)
            if any((a, b) not in causality for a in left_set for b in right_set):
                continue
            if any((a, b) not in choice for a, b in itertools.permutations(left_set, 2)):
                continue
            if any((a, b) not in choice for a, b in itertools.permutations(right_set, 2)):
                continue
            candidates.append((left_set, right_set))

    maximal: list[tuple[frozenset[str], frozenset[str]]] = []
    for candidate in candidates:
        a, b = candidate
        is_subsumed = False
        for other_a, other_b in candidates:
            if candidate == (other_a, other_b):
                continue
            if a <= other_a and b <= other_b:
                is_subsumed = True
                break
        if not is_subsumed:
            maximal.append(candidate)
    return sorted(maximal, key=lambda pair: (sorted(pair[0]), sorted(pair[1])))


def build_petri_net(
    tasks: set[str],
    starts: set[str],
    ends: set[str],
    places: list[tuple[frozenset[str], frozenset[str]]],
) -> PetriNet:
    transitions = sorted(tasks, key=lambda activity: (TRANSITION_COLUMNS.get(activity, 99), SHORT.get(activity, activity)))
    petri_places = [
        PetriPlace("p_start", "Start", tuple(), tuple(sorted(starts))),
    ]
    arcs: list[tuple[str, str]] = []
    for start in sorted(starts):
        arcs.append(("p_start", transition_id(start)))

    for index, (left, right) in enumerate(places, start=1):
        place_id = f"p_{index:02d}"
        label = f"p{index}"
        inputs = tuple(sorted(left))
        outputs = tuple(sorted(right))
        petri_places.append(PetriPlace(place_id, label, inputs, outputs))
        for activity in inputs:
            arcs.append((transition_id(activity), place_id))
        for activity in outputs:
            arcs.append((place_id, transition_id(activity)))

    petri_places.append(PetriPlace("p_end", "End", tuple(sorted(ends)), tuple()))
    for end in sorted(ends):
        arcs.append((transition_id(end), "p_end"))

    return PetriNet(
        places=petri_places,
        transitions=transitions,
        arcs=arcs,
        initial_place="p_start",
        final_places={"p_end"},
    )


def case_metrics(cases: dict[str, list[Event]]):
    durations = []
    for case_id, events in sorted(cases.items(), key=lambda item: case_sort_key(item[0])):
        start = events[0].timestamp
        end = events[-1].timestamp
        trace = [event.activity for event in events]
        durations.append((case_id, start, end, end - start, trace))
    return durations


def edge_durations(cases: dict[str, list[Event]]):
    waits: dict[tuple[str, str], list[float]] = defaultdict(list)
    for events in cases.values():
        for left, right in zip(events, events[1:]):
            hours = (right.timestamp - left.timestamp).total_seconds() / 3600
            waits[(left.activity, right.activity)].append(hours)
    return waits


def transition_id(activity: str) -> str:
    value = "".join(ch if ch.isalnum() else "_" for ch in SHORT.get(activity, activity)).strip("_")
    return f"t_{value}"


def safe_dot_id(identifier: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in identifier).strip("_")


def tex_escape(text: object) -> str:
    raw = str(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in raw)


def svg_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def short(activity: str) -> str:
    return SHORT.get(activity, activity)


def format_activity_set(items: set[str] | frozenset[str] | tuple[str, ...]) -> str:
    if not items:
        return r"$\emptyset$"
    return r"\{" + ", ".join(tex_escape(short(item)) for item in sorted(items)) + r"\}"


def format_pair_list(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return "none"
    return "; ".join(f"{short(a)} > {short(b)}" for a, b in pairs)


def write_sorted_log(cases: dict[str, list[Event]], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "timestamp", "activity", "resource"])
        for case_id, events in sorted(cases.items(), key=lambda item: case_sort_key(item[0])):
            for event in events:
                writer.writerow(
                    [case_id, event.timestamp.strftime(TIME_FMT), event.activity, event.resource]
                )


def write_petri_dot(net: PetriNet, out: Path) -> None:
    lines = [
        "digraph assignment2_petri_net {",
        "  rankdir=LR;",
        '  graph [label="Assignment 2 Alpha-Mined Petri Net", labelloc=t, fontsize=18];',
        '  node [fontname="Arial"];',
    ]
    for place in net.places:
        shape = "doublecircle" if place.place_id in net.final_places else "circle"
        stroke = " penwidth=3" if place.place_id in {net.initial_place, *net.final_places} else ""
        lines.append(
            f'  {safe_dot_id(place.place_id)} [shape={shape}, label="{place.label}", width=0.75{stroke}];'
        )
    for activity in net.transitions:
        lines.append(
            f'  {safe_dot_id(transition_id(activity))} [shape=box, style="rounded", label="{short(activity)}"];'
        )
    for source, target in net.arcs:
        lines.append(f"  {safe_dot_id(source)} -> {safe_dot_id(target)};")
    lines.append("}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_pnml_name(parent: ET.Element, text: str) -> None:
    name = ET.SubElement(parent, "name")
    child = ET.SubElement(name, "text")
    child.text = text


def write_petri_pnml(net: PetriNet, out: Path) -> None:
    pnml = ET.Element("pnml")
    net_el = ET.SubElement(
        pnml,
        "net",
        {"id": "assignment2_alpha_mined_petri_net", "type": "http://www.pnml.org/version-2009/grammar/ptnet"},
    )
    add_pnml_name(net_el, "Assignment 2 Alpha-Mined Petri Net")
    page = ET.SubElement(net_el, "page", {"id": "page_1"})

    for place in net.places:
        place_el = ET.SubElement(page, "place", {"id": place.place_id})
        add_pnml_name(place_el, place.label)
        if place.place_id == net.initial_place:
            marking = ET.SubElement(place_el, "initialMarking")
            text = ET.SubElement(marking, "text")
            text.text = "1"

    for activity in net.transitions:
        transition = ET.SubElement(page, "transition", {"id": transition_id(activity)})
        add_pnml_name(transition, short(activity))

    for index, (source, target) in enumerate(net.arcs, start=1):
        ET.SubElement(page, "arc", {"id": f"a_{index:03d}", "source": source, "target": target})

    tree = ET.ElementTree(pnml)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)


def transition_position(activity: str) -> tuple[float, float]:
    return 110 + TRANSITION_COLUMNS.get(activity, 99) * 230, 120 + TRANSITION_ROWS.get(activity, 2) * 130


def place_position(place: PetriPlace, transition_positions: dict[str, tuple[float, float]]) -> tuple[float, float]:
    if place.place_id == "p_start":
        first_targets = [transition_positions[transition_id(activity)] for activity in place.outputs]
        y = sum(y for _x, y in first_targets) / len(first_targets)
        return first_targets[0][0] - 145, y
    if place.place_id == "p_end":
        first_sources = [transition_positions[transition_id(activity)] for activity in place.inputs]
        y = sum(y for _x, y in first_sources) / len(first_sources)
        return first_sources[0][0] + 145, y

    points = [transition_positions[transition_id(activity)] for activity in place.inputs + place.outputs]
    min_x = min(x for x, _y in points)
    max_x = max(x for x, _y in points)
    avg_y = sum(y for _x, y in points) / len(points)
    return (min_x + max_x) / 2, avg_y


def separate_overlapping_places(
    place_positions: dict[str, tuple[float, float]],
    spacing: float = 70.0,
) -> dict[str, tuple[float, float]]:
    grouped: dict[tuple[float, float], list[str]] = defaultdict(list)
    for place_id, position in place_positions.items():
        grouped[(round(position[0], 1), round(position[1], 1))].append(place_id)

    separated = dict(place_positions)
    for place_ids in grouped.values():
        if len(place_ids) == 1:
            continue
        place_ids.sort()
        midpoint = (len(place_ids) - 1) / 2
        for index, place_id in enumerate(place_ids):
            x, y = separated[place_id]
            separated[place_id] = (x, y + (index - midpoint) * spacing)
    return separated


def boundary_point(
    center: tuple[float, float],
    size: tuple[float, float],
    toward: tuple[float, float],
) -> tuple[float, float]:
    cx, cy = center
    width, height = size
    dx = toward[0] - cx
    dy = toward[1] - cy
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return center
    scale = min(
        (width / 2) / abs(dx) if abs(dx) > 0.01 else float("inf"),
        (height / 2) / abs(dy) if abs(dy) > 0.01 else float("inf"),
    )
    return cx + dx * scale, cy + dy * scale


def svg_text(
    lines: list[str],
    x: float,
    y: float,
    size: int = 13,
    anchor: str = "middle",
    weight: str = "400",
) -> str:
    attrs = f'x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}"'
    if len(lines) == 1:
        return f"<text {attrs}>{svg_escape(lines[0])}</text>"
    out = [f"<text {attrs}>"]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size + 3
        out.append(f'<tspan x="{x:.1f}" dy="{dy}">{svg_escape(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def wrap_label(text: str, width: int = 15) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def write_petri_svg(net: PetriNet, out: Path) -> None:
    transition_positions = {
        transition_id(activity): transition_position(activity) for activity in net.transitions
    }
    place_positions = {
        place.place_id: place_position(place, transition_positions) for place in net.places
    }
    place_positions = separate_overlapping_places(place_positions)
    positions = {**transition_positions, **place_positions}
    width = int(max(x for x, _y in positions.values()) + 150)
    height = int(max(y for _x, y in positions.values()) + 150)
    place_ids = {place.place_id for place in net.places}

    def node_size(node_id: str) -> tuple[float, float]:
        return (54, 54) if node_id in place_ids else (112, 44)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.arc{stroke:#20242a;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}.place{fill:#fff;stroke:#20242a;stroke-width:1.8}.transition{fill:#f8fafc;stroke:#20242a;stroke-width:1.8}",
        "</style>",
        svg_text(["Assignment 2 Alpha-Mined Petri Net"], width / 2, 30, 18, weight="700"),
    ]

    for source, target in net.arcs:
        source_center = positions[source]
        target_center = positions[target]
        start = boundary_point(source_center, node_size(source), target_center)
        end = boundary_point(target_center, node_size(target), source_center)
        if abs(start[1] - end[1]) < 2 or abs(start[0] - end[0]) < 2:
            points = [start, end]
        else:
            mid_x = (start[0] + end[0]) / 2
            points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
        value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline class="arc" points="{value}" fill="none" marker-end="url(#arrow)"/>')

    place_lookup = {place.place_id: place for place in net.places}
    for place_id, (x, y) in place_positions.items():
        stroke_width = 3 if place_id in {net.initial_place, *net.final_places} else 1.8
        parts.append(f'<circle class="place" cx="{x:.1f}" cy="{y:.1f}" r="27" stroke-width="{stroke_width}"/>')
        parts.append(svg_text([place_lookup[place_id].label], x, y + 5, 12, weight="700"))

    for activity in net.transitions:
        transition = transition_id(activity)
        x, y = transition_positions[transition]
        parts.append(
            f'<rect class="transition" x="{x-56:.1f}" y="{y-22:.1f}" width="112" height="44" rx="5" ry="5"/>'
        )
        lines = wrap_label(short(activity), 14)
        parts.append(svg_text(lines, x, y + 4 - (len(lines) - 1) * 7, 10))

    parts.append("</svg>")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_alpha_tex(
    cases: dict[str, list[Event]],
    follows: Counter[tuple[str, str]],
    causality: set[tuple[str, str]],
    parallel: set[tuple[str, str]],
    choice: set[tuple[str, str]],
    alpha_place_pairs: list[tuple[frozenset[str], frozenset[str]]],
    net: PetriNet,
    out: Path,
) -> None:
    starts = {events[0].activity for events in cases.values()}
    ends = {events[-1].activity for events in cases.values()}
    durations = case_metrics(cases)
    waits = edge_durations(cases)
    tasks = {event.activity for events in cases.values() for event in events}
    event_count = sum(len(events) for events in cases.values())
    avg_days = sum(duration.total_seconds() / 86400 for *_rest, duration, _trace in durations) / len(durations)

    lines: list[str] = []
    lines.append(r"\section{Generated Petri-Net Conversion Evidence}")

    lines.append(r"\subsection{Step 1: Get Process Instances}")
    lines.append(
        "The event log is grouped by case ID and sorted by timestamp. Each case becomes one ordered process instance."
    )
    lines.append(r"\begin{ReportLongTable}{C{0.08\linewidth}L{0.84\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Case} & \textbf{Process instance trace} \\")
    lines.append(r"\midrule")
    for case_id, _start, _end, _duration, trace in durations:
        lines.append(
            f"{tex_escape(case_id)} & "
            + r" $\rightarrow$ ".join(tex_escape(short(activity)) for activity in trace)
            + r" \\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Step 2: Project Each Instance}")
    lines.append(
        "Each instance is projected to the directly-following activity pairs observed inside that single trace."
    )
    lines.append(r"\begin{ReportLongTable}{C{0.08\linewidth}L{0.84\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Case} & \textbf{Projected direct-succession pairs} \\")
    lines.append(r"\midrule")
    for case_id, events in sorted(cases.items(), key=lambda item: case_sort_key(item[0])):
        pairs = [(left.activity, right.activity) for left, right in zip(events, events[1:])]
        lines.append(f"{tex_escape(case_id)} & {tex_escape(format_pair_list(pairs))} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Step 3: Aggregate Projected Relations}")
    lines.append(
        "The projected pairs are aggregated across all instances. The relation column is then derived using the Alpha definitions."
    )
    lines.append(r"\begin{ReportLongTable}{L{0.29\linewidth}L{0.29\linewidth}r L{0.18\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{From} & \textbf{To} & \textbf{Count} & \textbf{Alpha relation} \\")
    lines.append(r"\midrule")
    for (a, b), count in sorted(follows.items(), key=lambda item: (item[0][0], item[0][1])):
        if (a, b) in causality:
            rel = r"$\rightarrow$"
        elif (a, b) in parallel:
            rel = r"$\parallel$"
        else:
            rel = r"$>$"
        lines.append(f"{tex_escape(short(a))} & {tex_escape(short(b))} & {count} & {rel} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Step 4: Build Alpha Relations and Places}")
    lines.append(r"\begin{ReportLongTable}{L{0.64\linewidth}r}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Computed item} & \textbf{Value} \\")
    lines.append(r"\midrule")
    lines.append(f"Cases in the log & {len(cases)} \\\\")
    lines.append(f"Events in the log & {event_count} \\\\")
    lines.append(f"Activities in $T_W$ & {len(tasks)} \\\\")
    lines.append(f"Start activities in $T_I$ & {len(starts)} \\\\")
    lines.append(f"End activities in $T_O$ & {len(ends)} \\\\")
    lines.append(f"Observed direct-succession pairs $>$ & {len(follows)} \\\\")
    lines.append(f"Causal pairs $\\rightarrow$ & {len(causality)} \\\\")
    lines.append(f"Parallel ordered pairs $\\parallel$ & {len(parallel)} \\\\")
    lines.append(f"Parallel unordered pairs & {len(parallel) // 2} \\\\")
    lines.append(f"Choice ordered pairs $\\#$ & {len(choice)} \\\\")
    lines.append(f"Maximal Alpha places $Y_W$ & {len(alpha_place_pairs)} \\\\")
    lines.append(f"Average cycle time & {avg_days:.2f} days \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")
    lines.append(
        r"Choice is counted as an ordered Alpha relation: $x \# y$ and $y \# x$ are both included when two activities never directly follow one another."
    )

    lines.append(r"\begin{itemize}")
    lines.append(
        r"\item $T_W$ activities: "
        + ", ".join(tex_escape(short(activity)) for activity in sorted(tasks))
    )
    lines.append(
        r"\item $T_I$ start activities: "
        + ", ".join(tex_escape(short(activity)) for activity in sorted(starts))
    )
    lines.append(
        r"\item $T_O$ end activities: "
        + ", ".join(tex_escape(short(activity)) for activity in sorted(ends))
    )
    parallel_unique = {tuple(sorted(pair)) for pair in parallel}
    lines.append(
        r"\item Parallel pairs: "
        + (", ".join(rf"({tex_escape(short(a))}, {tex_escape(short(b))})" for a, b in sorted(parallel_unique)) or "none")
    )
    lines.append(r"\end{itemize}")

    lines.append(r"\begin{ReportLongTable}{L{0.45\linewidth}L{0.45\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Input activity set $A$} & \textbf{Output activity set $B$} \\")
    lines.append(r"\midrule")
    for left, right in alpha_place_pairs:
        lines.append(f"{format_activity_set(left)} & {format_activity_set(right)} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Step 5: Map Onto Petri Net}")
    lines.append(
        "Each activity becomes a transition. The source place feeds the start transition. Each maximal Alpha pair becomes a place between its input and output transitions. The sink place receives the end transition."
    )
    lines.append(r"\begin{ReportLongTable}{L{0.12\linewidth}L{0.38\linewidth}L{0.38\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Place} & \textbf{Input transitions} & \textbf{Output transitions} \\")
    lines.append(r"\midrule")
    for place in net.places:
        lines.append(
            f"{tex_escape(place.label)} & {format_activity_set(place.inputs)} & {format_activity_set(place.outputs)} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")
    lines.append(r"\begin{ReportTable}{L{0.35\linewidth}r}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Petri-net element} & \textbf{Count} \\")
    lines.append(r"\midrule")
    lines.append(f"Places, including source and sink & {len(net.places)} \\\\")
    lines.append(f"Transitions & {len(net.transitions)} \\\\")
    lines.append(f"Arcs & {len(net.arcs)} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportTable}")

    lines.append(r"\subsection{Timing Metrics for Interpretation}")
    lines.append(r"\begin{ReportLongTable}{C{0.09\linewidth}L{0.26\linewidth}L{0.26\linewidth}L{0.18\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Case} & \textbf{Start} & \textbf{End} & \textbf{Cycle time} \\")
    lines.append(r"\midrule")
    for case_id, start, end, duration, _trace in durations:
        days = duration.total_seconds() / 86400
        lines.append(f"{tex_escape(case_id)} & {start.strftime(TIME_FMT)} & {end.strftime(TIME_FMT)} & {days:.2f} days \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\begin{ReportLongTable}{L{0.29\linewidth}L{0.29\linewidth}C{0.14\linewidth}C{0.16\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{From} & \textbf{To} & \textbf{Occurrences} & \textbf{Average hours} \\")
    lines.append(r"\midrule")
    for (a, b), values in sorted(waits.items(), key=lambda item: -sum(item[1]) / len(item[1])):
        avg = sum(values) / len(values)
        lines.append(f"{tex_escape(short(a))} & {tex_escape(short(b))} & {len(values)} & {avg:.2f} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(
    cases: dict[str, list[Event]],
    follows: Counter[tuple[str, str]],
    causality: set[tuple[str, str]],
    parallel: set[tuple[str, str]],
    choice: set[tuple[str, str]],
    alpha_place_pairs: list[tuple[frozenset[str], frozenset[str]]],
    net: PetriNet,
    out: Path,
) -> None:
    durations = case_metrics(cases)
    event_count = sum(len(events) for events in cases.values())
    avg_days = sum(duration.total_seconds() / 86400 for *_rest, duration, _trace in durations) / len(durations)
    lines = [
        "Alpha Algorithm Petri-Net Summary",
        f"Cases: {len(cases)}",
        f"Events: {event_count}",
        f"Activities/transitions: {len(net.transitions)}",
        f"Direct succession pairs: {len(follows)}",
        f"Causal pairs: {len(causality)}",
        f"Parallel ordered pairs: {len(parallel)}",
        f"Parallel unordered pairs: {len(parallel) // 2}",
        f"Choice ordered pairs: {len(choice)}",
        f"Maximal Alpha places: {len(alpha_place_pairs)}",
        f"Petri-net places including source/sink: {len(net.places)}",
        f"Petri-net arcs: {len(net.arcs)}",
        f"Average cycle time: {avg_days:.2f} days",
        "",
        "Causal relations:",
    ]
    lines.extend(f"- {a} -> {b}" for a, b in sorted(causality))
    lines.append("")
    lines.append("Petri places:")
    for place in net.places:
        lines.append(
            f"- {place.label}: {{{', '.join(short(item) for item in place.inputs)}}} -> "
            f"{{{', '.join(short(item) for item in place.outputs)}}}"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/event_log.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = read_log(args.input)
    tasks = {event.activity for events in cases.values() for event in events}
    follows = pairs_directly_follow(cases)
    causality, parallel, choice = relation_sets(tasks, follows)
    alpha_place_pairs = alpha_places(tasks, causality, choice)
    starts = {events[0].activity for events in cases.values()}
    ends = {events[-1].activity for events in cases.values()}
    net = build_petri_net(tasks, starts, ends, alpha_place_pairs)

    write_sorted_log(cases, args.output_dir / "event_log_sorted.csv")
    write_petri_dot(net, args.output_dir / "assignment2_petri_net.dot")
    write_petri_pnml(net, args.output_dir / "assignment2_petri_net.pnml")
    write_petri_svg(net, args.output_dir / "assignment2_petri_net.svg")
    write_alpha_tex(cases, follows, causality, parallel, choice, alpha_place_pairs, net, args.output_dir / "assignment2_generated_tables.tex")
    write_summary(cases, follows, causality, parallel, choice, alpha_place_pairs, net, args.output_dir / "assignment2_summary.txt")
    print(f"Wrote process mining Petri-net outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
