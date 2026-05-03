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


TIME_FMT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class Event:
    event_id: str
    case_id: str
    timestamp: datetime
    activity: str
    resource: str


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
    for case_id, events in sorted(cases.items(), key=lambda item: int(item[0])):
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
        for case_id, events in sorted(cases.items(), key=lambda item: int(item[0])):
            for e in events:
                writer.writerow([case_id, e.timestamp.strftime(TIME_FMT), e.activity, e.resource])


def write_mermaid(causality: set[tuple[str, str]], starts: set[str], ends: set[str], out: Path):
    lines = ["flowchart LR", "    Start((Start))", "    End((End))"]
    for activity in sorted({x for edge in causality for x in edge} | starts | ends):
        lines.append(f'    {activity_id(activity)}["{SHORT.get(activity, activity)}"]')
    for start in sorted(starts):
        lines.append(f"    Start --> {activity_id(start)}")
    for a, b in sorted(causality):
        lines.append(f"    {activity_id(a)} --> {activity_id(b)}")
    for end in sorted(ends):
        lines.append(f"    {activity_id(end)} --> End")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_dot(causality: set[tuple[str, str]], starts: set[str], ends: set[str], out: Path):
    lines = ["digraph alpha_net {", "  rankdir=LR;", '  node [shape=box, style="rounded"];']
    lines.append('  start [label="Start", shape=circle];')
    lines.append('  end [label="End", shape=doublecircle];')
    for activity in sorted({x for edge in causality for x in edge} | starts | ends):
        lines.append(f'  "{activity}" [label="{SHORT.get(activity, activity)}"];')
    for start in sorted(starts):
        lines.append(f'  start -> "{start}";')
    for a, b in sorted(causality):
        lines.append(f'  "{a}" -> "{b}";')
    for end in sorted(ends):
        lines.append(f'  "{end}" -> end;')
    lines.append("}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    lines: list[str] = []
    lines.append(r"\section{Generated Alpha-Algorithm Evidence}")
    lines.append(r"\subsection{Traces}")
    lines.append(r"\begin{longtable}{p{0.08\linewidth}p{0.80\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"Case & Trace \\")
    lines.append(r"\midrule")
    for case_id, _start, _end, _duration, trace in durations:
        lines.append(
            f"{tex_escape(case_id)} & "
            + r" $\rightarrow$ ".join(tex_escape(SHORT.get(activity, activity)) for activity in trace)
            + r" \\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{longtable}")

    lines.append(r"\subsection{Direct Succession and Causality}")
    lines.append(r"\begin{longtable}{p{0.30\linewidth}p{0.30\linewidth}r p{0.18\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"From & To & Count & Alpha relation \\")
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
    lines.append(r"\end{longtable}")

    lines.append(r"\subsection{Alpha Sets}")
    lines.append(r"\begin{itemize}")
    tasks = {event.activity for events in cases.values() for event in events}
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
    lines.append(r"\begin{longtable}{p{0.45\linewidth}p{0.45\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"Input activity set $A$ & Output activity set $B$ \\")
    lines.append(r"\midrule")
    for left, right in places:
        lines.append(f"${format_set(left)}$ & ${format_set(right)}$ \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{longtable}")

    lines.append(r"\subsection{Timing Metrics}")
    lines.append(r"\begin{longtable}{p{0.10\linewidth}p{0.22\linewidth}p{0.22\linewidth}p{0.18\linewidth}}")
    lines.append(r"\toprule")
    lines.append(r"Case & Start & End & Cycle time \\")
    lines.append(r"\midrule")
    for case_id, start, end, duration, _trace in durations:
        days = duration.total_seconds() / 86400
        lines.append(
            f"{tex_escape(case_id)} & {start.strftime(TIME_FMT)} & {end.strftime(TIME_FMT)} & {days:.2f} days \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{longtable}")

    lines.append(r"\begin{longtable}{p{0.32\linewidth}p{0.32\linewidth}r r}")
    lines.append(r"\toprule")
    lines.append(r"From & To & Occurrences & Average hours \\")
    lines.append(r"\midrule")
    for (a, b), values in sorted(waits.items(), key=lambda item: -sum(item[1]) / len(item[1])):
        avg = sum(values) / len(values)
        lines.append(
            f"{tex_escape(SHORT.get(a, a))} & {tex_escape(SHORT.get(b, b))} & {len(values)} & {avg:.2f} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{longtable}")

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
    avg_days = sum(d.total_seconds() / 86400 for *_rest, d, _trace in durations) / len(durations)
    lines = [
        "Alpha Algorithm Summary",
        f"Cases: {len(cases)}",
        f"Activities: {len({e.activity for events in cases.values() for e in events})}",
        f"Direct succession pairs: {len(follows)}",
        f"Causal pairs: {len(causality)}",
        f"Parallel ordered pairs: {len(parallel)}",
        f"Choice ordered pairs: {len(choice)}",
        f"Maximal Alpha places: {len(places)}",
        f"Average cycle time: {avg_days:.2f} days",
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

    write_sorted_log(cases, args.output_dir / "event_log_sorted.csv")
    write_mermaid(causality, starts, ends, args.output_dir / "assignment2_pert.mmd")
    write_dot(causality, starts, ends, args.output_dir / "assignment2_alpha_net.dot")
    write_alpha_tex(cases, follows, causality, parallel, choice, places, args.output_dir / "assignment2_generated_tables.tex")
    write_summary(cases, follows, causality, parallel, choice, places, args.output_dir / "assignment2_summary.txt")
    print(f"Wrote process mining outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
