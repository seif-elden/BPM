#!/usr/bin/env python3
"""Alpha-algorithm and PERT helper for the Assignment 2 event log.

The script is intentionally dependency-free so it can be rerun on any CSV with
the columns: case_id, timestamp, activity, resource.
"""

from __future__ import annotations

import argparse
import csv
import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median


TIME_FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Event:
    event_id: str
    case_id: str
    timestamp: datetime
    activity: str
    resource: str


@dataclass(frozen=True)
class PertEdge:
    source: str
    target: str
    optimistic: float
    most_likely: float
    pessimistic: float
    expected: float


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
    return {case_id: sorted(events, key=lambda e: e.timestamp) for case_id, events in cases.items()}


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


def alpha_places(tasks: set[str], causality: set[tuple[str, str]], choice: set[tuple[str, str]]):
    """Return the maximal (A, B) Alpha-algorithm pairs."""
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
    return sorted(maximal, key=lambda p: (sorted(p[0]), sorted(p[1])))


def case_metrics(cases: dict[str, list[Event]]):
    durations = []
    for case_id, events in sorted(cases.items(), key=lambda item: case_sort_key(item[0])):
        start = events[0].timestamp
        end = events[-1].timestamp
        durations.append((case_id, start, end, end - start, [e.activity for e in events]))
    return durations


def edge_durations(cases: dict[str, list[Event]]):
    waits: dict[tuple[str, str], list[float]] = defaultdict(list)
    for events in cases.values():
        for left, right in zip(events, events[1:]):
            hours = (right.timestamp - left.timestamp).total_seconds() / 3600
            waits[(left.activity, right.activity)].append(hours)
    return waits


def activity_id(activity: str) -> str:
    words = "".join(ch if ch.isalnum() else "_" for ch in SHORT.get(activity, activity))
    return words.strip("_")


def pert_edge_stats(causality: set[tuple[str, str]], waits: dict[tuple[str, str], list[float]]) -> dict[tuple[str, str], PertEdge]:
    stats: dict[tuple[str, str], PertEdge] = {}
    for a, b in sorted(causality):
        values = sorted(waits[(a, b)])
        optimistic = min(values)
        most_likely = median(values)
        pessimistic = max(values)
        expected = (optimistic + 4 * most_likely + pessimistic) / 6
        stats[(a, b)] = PertEdge(a, b, optimistic, most_likely, pessimistic, expected)
    return stats


def critical_path_analysis(
    causality: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
    edge_stats: dict[tuple[str, str], PertEdge],
):
    start_node = "__START__"
    end_node = "__END__"
    nodes = {start_node, end_node} | starts | ends | {activity for edge in causality for activity in edge}
    weighted_edges: list[tuple[str, str, float]] = []
    weighted_edges.extend((start_node, start, 0.0) for start in starts)
    weighted_edges.extend((edge.source, edge.target, edge.expected) for edge in edge_stats.values())
    weighted_edges.extend((end, end_node, 0.0) for end in ends)

    incoming: dict[str, set[str]] = {node: set() for node in nodes}
    outgoing: dict[str, list[tuple[str, float]]] = {node: [] for node in nodes}
    for source, target, duration in weighted_edges:
        incoming[target].add(source)
        outgoing[source].append((target, duration))

    ready = sorted(node for node in nodes if not incoming[node])
    topo: list[str] = []
    incoming_copy = {node: set(values) for node, values in incoming.items()}
    while ready:
        node = ready.pop(0)
        topo.append(node)
        for target, _duration in outgoing[node]:
            incoming_copy[target].discard(node)
            if not incoming_copy[target]:
                ready.append(target)
                ready.sort()
    if len(topo) != len(nodes):
        raise ValueError("PERT critical-path calculation requires an acyclic dependency graph.")

    earliest = {node: float("-inf") for node in nodes}
    previous: dict[str, str] = {}
    earliest[start_node] = 0.0
    for node in topo:
        for target, duration in outgoing[node]:
            candidate = earliest[node] + duration
            if candidate > earliest[target]:
                earliest[target] = candidate
                previous[target] = node

    project_duration = earliest[end_node]
    latest = {node: float("inf") for node in nodes}
    latest[end_node] = project_duration
    for node in reversed(topo):
        for target, duration in outgoing[node]:
            latest[node] = min(latest[node], latest[target] - duration)

    slack: dict[tuple[str, str], float] = {}
    critical_edges: set[tuple[str, str]] = set()
    for source, target, duration in weighted_edges:
        value = latest[target] - earliest[source] - duration
        slack[(source, target)] = value
        if abs(value) < 0.01:
            critical_edges.add((source, target))

    path: list[str] = []
    node = end_node
    while node in previous:
        path.append(node)
        node = previous[node]
    path.append(start_node)
    path.reverse()
    visible_path = [node for node in path if node not in {start_node, end_node}]
    return earliest, latest, slack, critical_edges, visible_path, project_duration


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


def format_set(items: set[str] | frozenset[str]) -> str:
    return r"\{" + ", ".join(tex_escape(SHORT.get(item, item)) for item in sorted(items)) + r"\}"


def write_sorted_log(cases: dict[str, list[Event]], out: Path):
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "timestamp", "activity", "resource"])
        for case_id, events in sorted(cases.items(), key=lambda item: case_sort_key(item[0])):
            for e in events:
                writer.writerow([case_id, e.timestamp.strftime(TIME_FMT), e.activity, e.resource])


def write_mermaid(
    causality: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
    waits: dict[tuple[str, str], list[float]],
    out: Path,
):
    edge_stats = pert_edge_stats(causality, waits)
    earliest, latest, _slack, critical_edges, _path, project_duration = critical_path_analysis(
        causality, starts, ends, edge_stats
    )
    lines = [
        "flowchart LR",
        f'    Start((Start<br/>0.00h))',
        f'    End((End<br/>{project_duration:.2f}h))',
    ]
    for activity in sorted({x for edge in causality for x in edge} | starts | ends):
        lines.append(
            f'    {activity_id(activity)}["{SHORT.get(activity, activity)}<br/>ES {earliest[activity]:.2f}h | LS {latest[activity]:.2f}h"]'
        )
    link_index = 0
    critical_link_indexes: list[int] = []
    for start in sorted(starts):
        lines.append(f"    Start -->|0.00h| {activity_id(start)}")
        if ("__START__", start) in critical_edges:
            critical_link_indexes.append(link_index)
        link_index += 1
    for a, b in sorted(causality):
        edge = edge_stats[(a, b)]
        lines.append(f"    {activity_id(a)} -->|E={edge.expected:.2f}h| {activity_id(b)}")
        if (a, b) in critical_edges:
            critical_link_indexes.append(link_index)
        link_index += 1
    for end in sorted(ends):
        lines.append(f"    {activity_id(end)} -->|0.00h| End")
        if (end, "__END__") in critical_edges:
            critical_link_indexes.append(link_index)
        link_index += 1
    critical_nodes = sorted(
        activity_id(activity)
        for activity in ({x for edge in causality for x in edge} | starts | ends)
        if abs(earliest[activity] - latest[activity]) < 0.01
    )
    lines.append("    classDef critical fill:#fff7ed,stroke:#c2410c,stroke-width:3px;")
    if critical_nodes:
        lines.append("    class " + ",".join(critical_nodes) + " critical;")
    for index in critical_link_indexes:
        lines.append(f"    linkStyle {index} stroke:#c2410c,stroke-width:4px;")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_dot(
    causality: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
    waits: dict[tuple[str, str], list[float]],
    out: Path,
):
    edge_stats = pert_edge_stats(causality, waits)
    earliest, latest, _slack, critical_edges, _path, project_duration = critical_path_analysis(
        causality, starts, ends, edge_stats
    )
    lines = ["digraph alpha_net {", "  rankdir=LR;", '  node [shape=box, style="rounded"];']
    lines.append('  start [label="Start\\n0.00h", shape=circle];')
    lines.append(f'  end [label="End\\n{project_duration:.2f}h", shape=doublecircle];')
    for activity in sorted({x for edge in causality for x in edge} | starts | ends):
        color = ' color="#c2410c" penwidth=3' if abs(earliest[activity] - latest[activity]) < 0.01 else ""
        lines.append(
            f'  "{activity}" [label="{SHORT.get(activity, activity)}\\nES {earliest[activity]:.2f}h | LS {latest[activity]:.2f}h"{color}];'
        )
    for start in sorted(starts):
        color = ' color="#c2410c" penwidth=3' if ("__START__", start) in critical_edges else ""
        lines.append(f'  start -> "{start}" [label="0.00h"{color}];')
    for a, b in sorted(causality):
        edge = edge_stats[(a, b)]
        color = ' color="#c2410c" penwidth=3' if (a, b) in critical_edges else ""
        lines.append(f'  "{a}" -> "{b}" [label="E={edge.expected:.2f}h"{color}];')
    for end in sorted(ends):
        color = ' color="#c2410c" penwidth=3' if (end, "__END__") in critical_edges else ""
        lines.append(f'  "{end}" -> end [label="0.00h"{color}];')
    lines.append("}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


PERT_POSITIONS = {
    "__START__": (70, 260),
    "Check stock availability": (240, 260),
    "Check materials availability": (470, 125),
    "Retrieve product from warehouse": (470, 395),
    "Request raw materials": (720, 125),
    "Obtain raw materials": (970, 125),
    "Manufacture product": (1210, 125),
    "Confirm order": (1440, 260),
    "Emit invoice": (1680, 125),
    "Get shipping address": (1680, 395),
    "Receive payment": (1930, 125),
    "Ship product": (1930, 395),
    "Archive order": (2170, 260),
    "__END__": (2350, 260),
}


def svg_lines(text: str, width: int = 18) -> list[str]:
    return [text[index : index + width] for index in range(0, len(text), width)] or [text]


def write_svg_text(lines: list[str], x: float, y: float, size: int = 13, anchor: str = "middle", weight: str = "400") -> str:
    attrs = f'x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}"'
    if len(lines) == 1:
        return f"<text {attrs}>{tex_escape_svg(lines[0])}</text>"
    out = [f"<text {attrs}>"]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size + 2
        out.append(f'<tspan x="{x:.1f}" dy="{dy}">{tex_escape_svg(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def tex_escape_svg(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_pert_node(activity: str, x: float, y: float, earliest: dict[str, float], latest: dict[str, float]) -> str:
    if activity == "__START__":
        label = ["Start", "0.00h"]
        return "\n".join(
            [
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="45" fill="#fff" stroke="#20242a" stroke-width="2"/>',
                write_svg_text(label, x, y - 4, 13, weight="700"),
            ]
        )
    if activity == "__END__":
        label = ["End", f"{earliest[activity]:.2f}h"]
        return "\n".join(
            [
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="45" fill="#fff" stroke="#20242a" stroke-width="4"/>',
                write_svg_text(label, x, y - 4, 13, weight="700"),
            ]
        )
    critical = abs(earliest[activity] - latest[activity]) < 0.01
    stroke = "#c2410c" if critical else "#20242a"
    stroke_width = 3 if critical else 2
    label = svg_lines(SHORT.get(activity, activity), 18)
    label.append(f"ES {earliest[activity]:.1f}h")
    label.append(f"LS {latest[activity]:.1f}h")
    return "\n".join(
        [
            f'<rect x="{x-82:.1f}" y="{y-43:.1f}" width="164" height="86" rx="7" ry="7" fill="#fff" stroke="{stroke}" stroke-width="{stroke_width}"/>',
            write_svg_text(label, x, y - 22, 12, weight="700" if critical else "400"),
        ]
    )


def render_pert_edge(source: str, target: str, duration: float, critical: bool) -> str:
    sx, sy = PERT_POSITIONS[source]
    tx, ty = PERT_POSITIONS[target]
    start_x = sx + (45 if source in {"__START__", "__END__"} else 82)
    end_x = tx - (45 if target in {"__START__", "__END__"} else 82)
    mid_x = (start_x + end_x) / 2
    stroke = "#c2410c" if critical else "#20242a"
    stroke_width = 4 if critical else 2
    label_y = (sy + ty) / 2 - 8
    points = f"{start_x:.1f},{sy:.1f} {mid_x:.1f},{sy:.1f} {mid_x:.1f},{ty:.1f} {end_x:.1f},{ty:.1f}"
    return "\n".join(
        [
            f'<polyline points="{points}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#arrow)"/>',
            f'<text x="{mid_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="12" fill="{stroke}">E={duration:.2f}h</text>',
        ]
    )


def write_pert_svg(
    causality: set[tuple[str, str]],
    starts: set[str],
    ends: set[str],
    waits: dict[tuple[str, str], list[float]],
    out: Path,
):
    edge_stats = pert_edge_stats(causality, waits)
    earliest, latest, _slack, critical_edges, path, project_duration = critical_path_analysis(
        causality, starts, ends, edge_stats
    )
    width = 2440
    height = 520
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}</style>',
        write_svg_text(["PERT/Event Network with Expected Durations and Critical Path"], width / 2, 28, 18, weight="700"),
        write_svg_text([f"Critical path: {' -> '.join(SHORT.get(item, item) for item in path)} | Expected duration {project_duration:.2f} hours"], width / 2, 52, 13),
    ]
    for start in sorted(starts):
        parts.append(render_pert_edge("__START__", start, 0.0, ("__START__", start) in critical_edges))
    for a, b in sorted(causality):
        parts.append(render_pert_edge(a, b, edge_stats[(a, b)].expected, (a, b) in critical_edges))
    for end in sorted(ends):
        parts.append(render_pert_edge(end, "__END__", 0.0, (end, "__END__") in critical_edges))
    for activity in ["__START__"] + sorted({x for edge in causality for x in edge} | starts | ends) + ["__END__"]:
        x, y = PERT_POSITIONS[activity]
        parts.append(render_pert_node(activity, x, y, earliest, latest))
    parts.append("</svg>")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_alpha_tex(
    cases: dict[str, list[Event]],
    follows: Counter[tuple[str, str]],
    causality: set[tuple[str, str]],
    parallel: set[tuple[str, str]],
    choice: set[tuple[str, str]],
    places: list[tuple[frozenset[str], frozenset[str]]],
    out: Path,
):
    starts = {events[0].activity for events in cases.values()}
    ends = {events[-1].activity for events in cases.values()}
    durations = case_metrics(cases)
    waits = edge_durations(cases)
    tasks = {event.activity for events in cases.values() for event in events}
    event_count = sum(len(events) for events in cases.values())
    avg_days = sum(duration.total_seconds() / 86400 for *_rest, duration, _trace in durations) / len(durations)
    edge_stats = pert_edge_stats(causality, waits)
    earliest, latest, slack, critical_edges, critical_path, project_hours = critical_path_analysis(
        causality, starts, ends, edge_stats
    )

    lines: list[str] = []
    lines.append(r"\section{Generated Alpha-Algorithm Evidence}")
    lines.append(r"\subsection{Traces}")
    lines.append(r"\begin{ReportLongTable}{C{0.08\linewidth}L{0.84\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Case} & \textbf{Trace} \\")
    lines.append(r"\midrule")
    for case_id, _start, _end, _duration, trace in durations:
        lines.append(
            f"{tex_escape(case_id)} & "
            + r" $\rightarrow$ ".join(tex_escape(SHORT.get(activity, activity)) for activity in trace)
            + r" \\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Exact Computation Totals}")
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
    lines.append(f"Maximal Alpha places $Y_W$ & {len(places)} \\\\")
    lines.append(f"Average cycle time & {avg_days:.2f} days \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")
    lines.append(
        r"Choice is counted as an ordered Alpha relation: $x \# y$ and $y \# x$ are both included when two activities never directly follow one another. Thus 100 ordered choice relations correspond to 50 unordered activity pairs."
    )

    lines.append(r"\subsection{Direct Succession and Causality}")
    lines.append(r"\begin{ReportLongTable}{L{0.31\linewidth}L{0.31\linewidth}r L{0.16\linewidth}}")
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
        lines.append(
            f"{tex_escape(SHORT.get(a, a))} & {tex_escape(SHORT.get(b, b))} & {count} & {rel} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Alpha Sets}")
    lines.append(r"\begin{itemize}")
    lines.append(
        r"\item $T_W$ activities: "
        + ", ".join(tex_escape(SHORT.get(activity, activity)) for activity in sorted(tasks))
    )
    lines.append(r"\item $T_I$ start activities: " + ", ".join(tex_escape(SHORT.get(activity, activity)) for activity in sorted(starts)))
    lines.append(r"\item $T_O$ end activities: " + ", ".join(tex_escape(SHORT.get(activity, activity)) for activity in sorted(ends)))
    parallel_unique = {tuple(sorted(pair)) for pair in parallel}
    lines.append(
        r"\item Parallel pairs: "
        + (", ".join(rf"({tex_escape(SHORT[a])}, {tex_escape(SHORT[b])})" for a, b in sorted(parallel_unique)) or "none")
    )
    lines.append(
        r"\item Main exclusive choices: available stock path versus manufacturing path; raw materials already available versus raw materials requested and obtained."
    )
    lines.append(r"\end{itemize}")

    lines.append(r"\subsection{Maximal Alpha Places}")
    lines.append(r"\begin{ReportLongTable}{L{0.45\linewidth}L{0.45\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Input activity set $A$} & \textbf{Output activity set $B$} \\")
    lines.append(r"\midrule")
    for left, right in places:
        lines.append(f"{format_set(left)} & {format_set(right)} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{Timing Metrics}")
    lines.append(r"\begin{ReportLongTable}{C{0.09\linewidth}L{0.26\linewidth}L{0.26\linewidth}L{0.18\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{Case} & \textbf{Start} & \textbf{End} & \textbf{Cycle time} \\")
    lines.append(r"\midrule")
    for case_id, start, end, duration, _trace in durations:
        days = duration.total_seconds() / 86400
        lines.append(
            f"{tex_escape(case_id)} & {start.strftime(TIME_FMT)} & {end.strftime(TIME_FMT)} & {days:.2f} days \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\begin{ReportLongTable}{L{0.29\linewidth}L{0.29\linewidth}C{0.14\linewidth}C{0.16\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{From} & \textbf{To} & \textbf{Occurrences} & \textbf{Average hours} \\")
    lines.append(r"\midrule")
    for (a, b), values in sorted(waits.items(), key=lambda item: -sum(item[1]) / len(item[1])):
        avg = sum(values) / len(values)
        lines.append(
            f"{tex_escape(SHORT.get(a, a))} & {tex_escape(SHORT.get(b, b))} & {len(values)} & {avg:.2f} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    lines.append(r"\subsection{PERT Timing and Critical Path}")
    lines.append(
        "The PERT/event-network timing is edge-weighted from observed elapsed hours between directly successive activities. "
        r"For each causal dependency, $O$ is the minimum observed duration, $M$ is the median duration, $P$ is the maximum duration, and $E=(O+4M+P)/6$."
    )
    lines.append(
        "The computed critical path is: "
        + r" $\rightarrow$ ".join(tex_escape(SHORT.get(activity, activity)) for activity in critical_path)
        + f". Expected path duration: {project_hours:.2f} hours."
    )
    lines.append(r"\begin{ReportLongTable}{L{0.21\linewidth}L{0.21\linewidth}C{0.07\linewidth}C{0.07\linewidth}C{0.07\linewidth}C{0.07\linewidth}C{0.07\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"\rowcolor{BPMTableHead}\textbf{From} & \textbf{To} & \textbf{O h} & \textbf{M h} & \textbf{P h} & \textbf{E h} & \textbf{Slack} \\")
    lines.append(r"\midrule")
    for (a, b), edge in sorted(edge_stats.items(), key=lambda item: (item[0][0], item[0][1])):
        critical_marker = r"\textbf{0.00}" if (a, b) in critical_edges else f"{slack[(a, b)]:.2f}"
        lines.append(
            f"{tex_escape(SHORT.get(a, a))} & {tex_escape(SHORT.get(b, b))} & "
            f"{edge.optimistic:.2f} & {edge.most_likely:.2f} & {edge.pessimistic:.2f} & {edge.expected:.2f} & {critical_marker} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{ReportLongTable}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(
    cases: dict[str, list[Event]],
    follows: Counter[tuple[str, str]],
    causality: set[tuple[str, str]],
    parallel: set[tuple[str, str]],
    choice: set[tuple[str, str]],
    places: list[tuple[frozenset[str], frozenset[str]]],
    out: Path,
):
    durations = case_metrics(cases)
    waits = edge_durations(cases)
    starts = {events[0].activity for events in cases.values()}
    ends = {events[-1].activity for events in cases.values()}
    edge_stats = pert_edge_stats(causality, waits)
    _earliest, _latest, _slack, _critical_edges, critical_path, project_hours = critical_path_analysis(
        causality, starts, ends, edge_stats
    )
    event_count = sum(len(events) for events in cases.values())
    avg_days = sum(d.total_seconds() / 86400 for *_rest, d, _trace in durations) / len(durations)
    lines = [
        "Alpha Algorithm Summary",
        f"Cases: {len(cases)}",
        f"Events: {event_count}",
        f"Activities: {len({e.activity for events in cases.values() for e in events})}",
        f"Direct succession pairs: {len(follows)}",
        f"Causal pairs: {len(causality)}",
        f"Parallel ordered pairs: {len(parallel)}",
        f"Parallel unordered pairs: {len(parallel) // 2}",
        f"Choice ordered pairs: {len(choice)}",
        f"Maximal Alpha places: {len(places)}",
        f"Average cycle time: {avg_days:.2f} days",
        f"PERT critical path expected duration: {project_hours:.2f} hours",
        "PERT critical path: " + " -> ".join(critical_path),
        "",
        "Causal relations:",
    ]
    lines.extend(f"- {a} -> {b}" for a, b in sorted(causality))
    lines.append("")
    lines.append("Maximal places:")
    lines.extend(
        f"- {{{', '.join(sorted(left))}}} -> {{{', '.join(sorted(right))}}}" for left, right in places
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
    places = alpha_places(tasks, causality, choice)
    starts = {events[0].activity for events in cases.values()}
    ends = {events[-1].activity for events in cases.values()}
    waits = edge_durations(cases)

    write_sorted_log(cases, args.output_dir / "event_log_sorted.csv")
    write_mermaid(causality, starts, ends, waits, args.output_dir / "assignment2_pert.mmd")
    write_dot(causality, starts, ends, waits, args.output_dir / "assignment2_alpha_net.dot")
    write_pert_svg(causality, starts, ends, waits, args.output_dir / "assignment2_pert.svg")
    write_alpha_tex(cases, follows, causality, parallel, choice, places, args.output_dir / "assignment2_generated_tables.tex")
    write_summary(cases, follows, causality, parallel, choice, places, args.output_dir / "assignment2_summary.txt")
    print(f"Wrote process mining outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
