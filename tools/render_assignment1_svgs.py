#!/usr/bin/env python3
"""Render Assignment 1 BPMN and Petri-net visuals as SVG evidence files."""

from __future__ import annotations

from html import escape
from pathlib import Path
from textwrap import wrap

from generate_assignment1_bpmn import (
    DataArtifact,
    DataAssociation,
    Flow,
    Node,
    PetriNet,
    artifact_size,
    as_is_artifacts,
    as_is_model,
    as_is_petri_net,
    display_y,
    node_size,
    participant_for_lane,
    to_be_artifacts,
    to_be_model,
    to_be_petri_net,
)


ROOT = Path(__file__).resolve().parents[1]
LANES = [
    "Customer",
    "Marketplace system",
    "Customer support",
    "Payment service",
    "Warehouse",
    "Courier",
]

PARTICIPANTS = [
    "Customer",
    "E-Commerce Operations",
    "Payment Service",
    "Warehouse/Fulfillment",
    "Courier/Shipment",
]

PARTICIPANT_BANDS = {
    "Customer": (18, 140),
    "E-Commerce Operations": (155, 575),
    "Payment Service": (610, 790),
    "Warehouse/Fulfillment": (825, 1010),
    "Courier/Shipment": (1045, 1250),
}

ECOM_LANE_BANDS = {
    "Marketplace system": (155, 400),
    "Customer support": (405, 575),
}


def svg_text(lines: list[str], x: float, y: float, size: int = 13, anchor: str = "middle", weight: str = "400") -> str:
    attrs = f'x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}"'
    if len(lines) == 1:
        return f'<text {attrs}>{escape(lines[0])}</text>'
    out = [f'<text {attrs}>']
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size + 2
        out.append(f'<tspan x="{x:.1f}" dy="{dy}">{escape(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def label_lines(text: str, width: int = 16) -> list[str]:
    return wrap(text, width=width) or [text]


def draw_gateway(node: Node, x: float, y: float, w: int, h: int) -> str:
    cx = x + w / 2
    cy = y + h / 2
    icon = "X"
    if node.kind == "parallelGateway":
        icon = "+"
    elif node.kind == "eventBasedGateway":
        icon = "E"
    label_y = y - 8 if node.kind == "exclusiveGateway" else y + h + 18
    return "\n".join(
        [
            f'<polygon points="{cx:.1f},{y:.1f} {x+w:.1f},{cy:.1f} {cx:.1f},{y+h:.1f} {x:.1f},{cy:.1f}" '
            'fill="#fff" stroke="#20242a" stroke-width="2"/>',
            svg_text([icon], cx, cy + 5, 18, weight="700"),
            svg_text(label_lines(node.name, 18), cx, label_y, 12),
        ]
    )


def draw_event(node: Node, x: float, y: float, w: int, h: int) -> str:
    cx = x + w / 2
    cy = y + h / 2
    stroke_width = 4 if node.kind == "endEvent" else 2
    parts = [
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{w/2:.1f}" fill="#fff" stroke="#20242a" stroke-width="{stroke_width}"/>'
    ]
    if node.kind == "intermediateCatchEvent":
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{w/2-5:.1f}" fill="none" stroke="#20242a" stroke-width="1.5"/>')
        if node.event_definition == "timer":
            parts.extend(
                [
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="none" stroke="#20242a" stroke-width="1.4"/>',
                    f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" y2="{cy-6:.1f}" stroke="#20242a" stroke-width="1.4"/>',
                    f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx+5:.1f}" y2="{cy+3:.1f}" stroke="#20242a" stroke-width="1.4"/>',
                ]
            )
        elif node.event_definition == "message":
            parts.extend(
                [
                    f'<rect x="{cx-10:.1f}" y="{cy-7:.1f}" width="20" height="14" fill="none" stroke="#20242a" stroke-width="1.3"/>',
                    f'<path d="M {cx-10:.1f} {cy-7:.1f} L {cx:.1f} {cy+1:.1f} L {cx+10:.1f} {cy-7:.1f}" fill="none" stroke="#20242a" stroke-width="1.3"/>',
                ]
            )
    parts.append(svg_text(label_lines(node.name, 18), cx, y + h + 18, 12))
    return "\n".join(parts)


def draw_task(node: Node, x: float, y: float, w: int, h: int) -> str:
    cx = x + w / 2
    cy = y + h / 2 - 5
    lines = label_lines(node.name, 17)
    text_y = cy - ((len(lines) - 1) * 7) + 4
    return "\n".join(
        [
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="8" ry="8" fill="#fff" stroke="#20242a" stroke-width="2"/>',
            svg_text(lines, cx, text_y, 13),
        ]
    )


def route_points(source: Node, target: Node, shift_x: int, max_y: float) -> list[tuple[float, float]]:
    sw, sh = node_size(source.kind)
    _tw, th = node_size(target.kind)
    source_y = display_y(source)
    target_y = display_y(target)
    if source.kind == "exclusiveGateway" and target_y > source_y + 35:
        sx = source.x + shift_x + sw / 2
        sy = source_y + sh
        tx = target.x + shift_x
        ty = target_y + th / 2
        mid_y = (sy + ty) / 2
        return [(sx, sy), (sx, mid_y), (tx, mid_y), (tx, ty)]

    sx = source.x + shift_x + sw
    sy = source_y + sh / 2
    tx = target.x + shift_x
    ty = target_y + th / 2
    if tx >= sx:
        mid = (sx + tx) / 2
        return [(sx, sy), (mid, sy), (mid, ty), (tx, ty)]

    source_participant = participant_for_lane(source.lane)
    target_participant = participant_for_lane(target.lane)
    if source_participant == target_participant == "E-Commerce Operations":
        # Route complaint/SLA loops locally inside the e-commerce pool. The
        # older generic loop went below every external pool, which made the
        # return flow look unrelated to complaint handling.
        local_y = ECOM_LANE_BANDS["Marketplace system"][1] + 2
        right_x = sx + 45
        left_x = tx - 55
        return [(sx, sy), (right_x, sy), (right_x, local_y), (left_x, local_y), (left_x, ty), (tx, ty)]

    loop_y = max_y + 45
    return [(sx, sy), (sx + 60, sy), (sx + 60, loop_y), (tx - 60, loop_y), (tx - 60, ty), (tx, ty)]


def route_message_points(source: Node, target: Node, shift_x: int) -> list[tuple[float, float]]:
    sw, sh = node_size(source.kind)
    tw, th = node_size(target.kind)
    source_center = (source.x + shift_x + sw / 2, display_y(source) + sh / 2)
    target_center = (target.x + shift_x + tw / 2, display_y(target) + th / 2)
    return [
        boundary_point(source_center, (sw, sh), target_center),
        boundary_point(target_center, (tw, th), source_center),
    ]

def polyline(points: list[tuple[float, float]], css_class: str = "flow") -> str:
    value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline class="{css_class}" points="{value}" fill="none" marker-end="url(#arrow)"/>'


def boundary_point(
    center: tuple[float, float],
    size: tuple[int, int],
    toward: tuple[float, float],
) -> tuple[float, float]:
    cx, cy = center
    width, height = size
    dx = toward[0] - cx
    dy = toward[1] - cy
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return center

    half_w = width / 2
    half_h = height / 2
    scale = min(
        half_w / abs(dx) if abs(dx) > 0.01 else float("inf"),
        half_h / abs(dy) if abs(dy) > 0.01 else float("inf"),
    )
    return cx + dx * scale, cy + dy * scale


def label_box(text: str, x: float, y: float, css_class: str) -> str:
    width = max(38, min(190, len(text) * 7.0 + 12))
    return "\n".join(
        [
            f'<rect class="label-bg" x="{x - width / 2:.1f}" y="{y - 15:.1f}" width="{width:.1f}" height="18" rx="2" ry="2"/>',
            f'<text class="{css_class}" x="{x:.1f}" y="{y:.1f}" text-anchor="middle">{escape(text)}</text>',
        ]
    )


def flow_label_position(
    points: list[tuple[float, float]],
    source: Node,
    target: Node,
    is_message: bool,
) -> tuple[float, float]:
    if not is_message and source.kind == "exclusiveGateway":
        source_y = display_y(source)
        target_y = display_y(target)
        if target_y > source_y + 35:
            return points[0][0] + 34, points[0][1] + 18
        return points[0][0] + 30, points[0][1] - 8

    if is_message and len(points) >= 4:
        source_participant = participant_for_lane(source.lane)
        target_participant = participant_for_lane(target.lane)
        if source_participant == "E-Commerce Operations" and target_participant != source_participant:
            x = points[1][0] + 18
            y = (points[1][1] + points[2][1]) / 2
            return x, y - 6
        if target_participant == "E-Commerce Operations" and source_participant != target_participant:
            x = (points[0][0] + points[1][0]) / 2
            return x, points[0][1] - 8

    segments = list(zip(points, points[1:]))
    horizontal = [
        (abs(a[0] - b[0]), a, b)
        for a, b in segments
        if abs(a[1] - b[1]) < 1 and abs(a[0] - b[0]) > 8
    ]
    if horizontal:
        _length, a, b = max(horizontal, key=lambda item: item[0])
        return (a[0] + b[0]) / 2, a[1] - 8
    mid = points[len(points) // 2]
    return mid[0], mid[1] - 8


def item_center(item: Node | DataArtifact, shift_x: int) -> tuple[float, float]:
    if isinstance(item, Node):
        w, h = node_size(item.kind)
    else:
        w, h = artifact_size(item.kind)
    return item.x + shift_x + w / 2, display_y(item) + h / 2


def draw_data_object(artifact: DataArtifact, x: float, y: float, w: int, h: int) -> str:
    fold = 12
    label = label_lines(artifact.name, 14)
    text_y = y + h / 2 - ((len(label) - 1) * 6) + 3
    return "\n".join(
        [
            f'<path d="M {x:.1f} {y:.1f} H {x+w-fold:.1f} L {x+w:.1f} {y+fold:.1f} V {y+h:.1f} H {x:.1f} Z" fill="#fffef6" stroke="#20242a" stroke-width="1.8"/>',
            f'<path d="M {x+w-fold:.1f} {y:.1f} V {y+fold:.1f} H {x+w:.1f}" fill="none" stroke="#20242a" stroke-width="1.4"/>',
            svg_text(label, x + w / 2, text_y, 10),
        ]
    )


def draw_data_store(artifact: DataArtifact, x: float, y: float, w: int, h: int) -> str:
    label = label_lines(artifact.name, 14)
    text_y = y + h / 2 - ((len(label) - 1) * 6) + 5
    rx = w / 2
    top = y + 9
    bottom = y + h - 9
    return "\n".join(
        [
            f'<path d="M {x:.1f} {top:.1f} C {x:.1f} {y:.1f}, {x+w:.1f} {y:.1f}, {x+w:.1f} {top:.1f} V {bottom:.1f} C {x+w:.1f} {y+h:.1f}, {x:.1f} {y+h:.1f}, {x:.1f} {bottom:.1f} Z" fill="#f0fdfa" stroke="#20242a" stroke-width="1.8"/>',
            f'<ellipse cx="{x+rx:.1f}" cy="{top:.1f}" rx="{rx:.1f}" ry="9" fill="none" stroke="#20242a" stroke-width="1.4"/>',
            svg_text(label, x + w / 2, text_y, 10),
        ]
    )


def draw_artifact(artifact: DataArtifact, shift_x: int) -> str:
    w, h = artifact_size(artifact.kind)
    x = artifact.x + shift_x
    y = display_y(artifact)
    if artifact.kind == "dataStoreReference":
        return draw_data_store(artifact, x, y, w, h)
    return draw_data_object(artifact, x, y, w, h)


def route_association(source: Node | DataArtifact, target: Node | DataArtifact, shift_x: int) -> list[tuple[float, float]]:
    if isinstance(source, Node):
        sw, sh = node_size(source.kind)
    else:
        sw, sh = artifact_size(source.kind)
    if isinstance(target, Node):
        tw, th = node_size(target.kind)
    else:
        tw, th = artifact_size(target.kind)

    sx = source.x + shift_x + sw / 2
    sy = display_y(source) + sh / 2
    tx = target.x + shift_x + tw / 2
    ty = display_y(target) + th / 2

    # Keep data associations short and close to the connected object. When the
    # item is above/below its task, route vertically; otherwise use one elbow.
    if abs(sx - tx) < 90:
        return [(sx, sy), (tx, ty)]
    mid_x = sx + (30 if tx > sx else -30)
    return [(sx, sy), (mid_x, sy), (mid_x, ty), (tx, ty)]


def visible_associations(associations: list[DataAssociation]) -> list[DataAssociation]:
    # Keep the diagram readable by showing only short local data associations.
    # Longer update relationships remain in the BPMN XML where tools can inspect
    # them, while the SVG evidence avoids crossing data-object lines.
    hidden_pairs = {
        ("Reserve_Item", "Data_Stock_Record"),
        ("Authorize_Payment", "Data_Payment_Record"),
        ("Data_Shipment_Record", "Delivery_Confirmed"),
        ("Escalate_Courier", "Data_Complaint_Case"),
        ("Receive_Payment", "Data_Payment_Authorization"),
        ("Data_Tracking_Record", "Delivery_Confirmed"),
        ("Notify_Customer", "Data_Complaint_Case"),
        ("Expedite_Courier", "Data_Complaint_Case"),
    }
    return [
        association
        for association in associations
        if (association.source, association.target) not in hidden_pairs
    ]

def render_bpmn_svg(
    nodes: list[Node],
    flows: list[Flow],
    artifacts: list[DataArtifact],
    associations: list[DataAssociation],
    title: str,
    out: Path,
    pool_name: str = "unused",
) -> None:
    shift_x = 230
    node_participant = {node.id: participant_for_lane(node.lane) for node in nodes}
    artifact_participant = {artifact.id: participant_for_lane(artifact.lane) for artifact in artifacts}
    element_participant = {**node_participant, **artifact_participant}
    visible_participants = [
        participant
        for participant in PARTICIPANTS
        if participant in element_participant.values()
    ]
    max_x = max(
        [node.x + shift_x + node_size(node.kind)[0] for node in nodes]
        + [artifact.x + shift_x + artifact_size(artifact.kind)[0] for artifact in artifacts]
    ) + 120
    bottom_band = max(PARTICIPANT_BANDS[participant][1] for participant in visible_participants)
    route_base_y = bottom_band + 35
    loop_bottom = route_base_y + 45
    height = loop_bottom + 55

    lookup: dict[str, Node | DataArtifact] = {node.id: node for node in nodes}
    lookup.update({artifact.id: artifact for artifact in artifacts})
    node_lookup = {node.id: node for node in nodes}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{max_x:.0f}" height="{height:.0f}" viewBox="0 0 {max_x:.0f} {height:.0f}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        '<marker id="msgArrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        '<marker id="assocArrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L7,3 z" fill="#64748b"/>',
        "</marker>",
        "</defs>",
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.flow{stroke:#20242a;stroke-width:2.1;stroke-linejoin:round;stroke-linecap:round}.message-flow{stroke:#20242a;stroke-width:1.9;stroke-dasharray:10 6;stroke-linejoin:round;stroke-linecap:round}.assoc{stroke:#64748b;stroke-width:1.5;stroke-dasharray:5 4;stroke-linejoin:round;stroke-linecap:round}.pool-label{fill:#334155;font-weight:700}.lane-label{fill:#0f766e;font-weight:700}.pool{fill:#ffffff;stroke:#334155;stroke-width:2.1}.pool-alt{fill:#f8fafc;stroke:#334155;stroke-width:2.1}.lane{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1.2}.lane-alt{fill:#ffffff;stroke:#cbd5e1;stroke-width:1.2}.flow-label{fill:#596579;font-size:12px}.message-label{fill:#20242a;font-size:12px}.artifact-label{fill:#475569;font-size:11px}.label-bg{fill:#fff;opacity:.94}",
        "</style>",
        f'<rect x="0" y="0" width="{max_x:.1f}" height="{height:.1f}" fill="#fff"/>',
    ]

    for index, participant in enumerate(visible_participants):
        top, bottom = PARTICIPANT_BANDS[participant]
        pool_class = "pool" if index % 2 == 0 else "pool-alt"
        parts.append(f'<rect class="{pool_class}" x="16" y="{top:.1f}" width="{max_x-32:.1f}" height="{bottom-top:.1f}"/>')
        cy = (top + bottom) / 2
        parts.append(f'<text class="pool-label" x="36" y="{cy:.1f}" text-anchor="middle" font-size="14" transform="rotate(-90 36 {cy:.1f})">{escape(participant)}</text>')
        if participant == "E-Commerce Operations":
            for lane_index, (lane, (lane_top, lane_bottom)) in enumerate(ECOM_LANE_BANDS.items()):
                lane_class = "lane" if lane_index % 2 == 0 else "lane-alt"
                parts.append(f'<rect class="{lane_class}" x="58" y="{lane_top:.1f}" width="{max_x-74:.1f}" height="{lane_bottom-lane_top:.1f}"/>')
                parts.append(svg_text(label_lines(lane, 15), 130, (lane_top + lane_bottom) / 2 - 4, 13, weight="700"))

    for association in visible_associations(associations):
        if element_participant.get(association.source) != element_participant.get(association.target):
            continue
        points = route_association(lookup[association.source], lookup[association.target], shift_x)
        marker = ' marker-end="url(#assocArrow)"' if association.direction == "One" else ""
        value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline class="assoc" points="{value}" fill="none"{marker}/>' )

    for flow in flows:
        if node_participant[flow.source] == node_participant[flow.target]:
            points = route_points(node_lookup[flow.source], node_lookup[flow.target], shift_x, route_base_y)
            parts.append(polyline(points))
            label_class = "flow-label"
        else:
            points = route_message_points(node_lookup[flow.source], node_lookup[flow.target], shift_x)
            value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            parts.append(f'<polyline class="message-flow" points="{value}" fill="none" marker-end="url(#msgArrow)"/>')
            label_class = "message-label"
        if flow.name:
            label_x, label_y = flow_label_position(
                points,
                node_lookup[flow.source],
                node_lookup[flow.target],
                label_class == "message-label",
            )
            parts.append(label_box(flow.name, label_x, label_y, label_class))

    for artifact in artifacts:
        parts.append(draw_artifact(artifact, shift_x))

    for node in nodes:
        w, h = node_size(node.kind)
        x = node.x + shift_x
        y = display_y(node)
        if node.kind.endswith("Gateway"):
            parts.append(draw_gateway(node, x, y, w, h))
        elif node.kind.endswith("Event"):
            parts.append(draw_event(node, x, y, w, h))
        else:
            parts.append(draw_task(node, x, y, w, h))

    parts.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")

def shape_center(shape_id: str, positions: dict[str, tuple[float, float]]) -> tuple[float, float]:
    return positions[shape_id]


def petri_boundary_point(
    shape_id: str,
    center: tuple[float, float],
    toward: tuple[float, float],
    place_ids: set[str],
) -> tuple[float, float]:
    cx, cy = center
    dx = toward[0] - cx
    dy = toward[1] - cy
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return center

    if shape_id in place_ids:
        if abs(dx) >= abs(dy):
            return cx + (27 if dx > 0 else -27), cy
        return cx, cy + (27 if dy > 0 else -27)

    half_w = 48
    half_h = 20
    if abs(dx) >= abs(dy):
        return cx + (half_w if dx > 0 else -half_w), cy
    return cx, cy + (half_h if dy > 0 else -half_h)


def collapse_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    collapsed: list[tuple[float, float]] = []
    for point in points:
        if not collapsed or abs(collapsed[-1][0] - point[0]) > 0.1 or abs(collapsed[-1][1] - point[1]) > 0.1:
            collapsed.append(point)
    return collapsed


def petri_arc_points(
    source: str,
    target: str,
    positions: dict[str, tuple[float, float]],
    place_ids: set[str],
) -> list[tuple[float, float]]:
    sx, sy = shape_center(source, positions)
    tx, ty = shape_center(target, positions)
    if tx >= sx:
        mid_x = (sx + tx) / 2
        points = [(sx, sy), (mid_x, sy), (mid_x, ty), (tx, ty)]
    else:
        loop_y = max(sy, ty) + 70
        points = [(sx, sy), (sx + 60, sy), (sx + 60, loop_y), (tx - 60, loop_y), (tx - 60, ty), (tx, ty)]

    points = collapse_points(points)
    if len(points) > 1:
        points[0] = petri_boundary_point(source, points[0], points[1], place_ids)
        points[-1] = petri_boundary_point(target, points[-1], points[-2], place_ids)
    return collapse_points(points)


def render_petri_svg(net: PetriNet, positions: dict[str, tuple[float, float]], title: str, out: Path) -> None:
    width = max(x for x, _y in positions.values()) + 130
    height = max(y for _x, y in positions.values()) + 95
    place_labels = dict(net.places)
    transition_labels = dict(net.transitions)
    place_ids = set(place_labels)
    sink_places = place_ids - {source for source, _target in net.arcs}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        "</defs>",
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.arc{stroke:#20242a;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}.place{fill:#fff;stroke:#20242a;stroke-width:1.8}.transition{fill:#f8fafc;stroke:#20242a;stroke-width:1.8}",
        "</style>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        svg_text([title], width / 2, 28, 18, weight="700"),
    ]

    for source, target in net.arcs:
        parts.append(polyline(petri_arc_points(source, target, positions, place_ids), "arc"))

    for place_id, label in net.places:
        x, y = positions[place_id]
        stroke = 3 if place_id in {net.initial_place, *sink_places} else 1.8
        parts.append(f'<circle class="place" cx="{x:.1f}" cy="{y:.1f}" r="27" stroke-width="{stroke}"/>')
        parts.append(svg_text(label_lines(label, 14), x, y + 47, 11))

    for transition_id, label in net.transitions:
        x, y = positions[transition_id]
        parts.append(f'<rect class="transition" x="{x-48:.1f}" y="{y-20:.1f}" width="96" height="40" rx="5" ry="5"/>')
        parts.append(svg_text(label_lines(label, 13), x, y + 4 - (len(label_lines(label, 13)) - 1) * 6, 10))

    parts.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


AS_IS_PETRI_POSITIONS = {
    "p_start": (70, 190), "t_capture_order": (170, 190), "p_captured": (280, 190), "t_check_stock": (390, 190),
    "p_stock_decision": (500, 190), "t_stock_no": (610, 95), "p_reject_ready": (720, 95), "t_reject_order": (830, 95),
    "p_rejected": (950, 95), "t_stock_yes": (610, 285), "p_stock_available": (720, 285), "t_reserve_item": (830, 285), "p_address_decision": (950, 285),
    "t_address_yes": (1060, 230), "t_address_no": (1060, 350), "p_address_missing": (1170, 350),
    "t_request_address": (1280, 350), "p_ready_to_prepare": (1390, 285), "t_prepare_split": (1500, 285),
    "p_payment_ready": (1610, 190), "t_authorize_payment": (1730, 190), "p_payment_authorized": (1850, 190),
    "t_emit_invoice": (1970, 190), "p_invoice_done": (2090, 190), "t_receive_payment": (2210, 190),
    "p_payment_received": (2330, 190), "p_fulfillment_ready": (1610, 380), "t_pick_pack": (1730, 380),
    "p_packed": (1850, 380), "t_ship_product": (1970, 380), "p_shipped": (2090, 380),
    "t_prepare_join": (2450, 285), "p_wait_delivery": (2570, 285), "t_delivery_confirmed": (2690, 195),
    "p_delivery_ok": (2810, 195), "t_archive_order": (2930, 195), "p_done": (3050, 195),
    "t_goods_delayed": (2690, 430), "p_delay_case": (2810, 430), "t_register_complaint": (2930, 430),
    "p_complaint_registered": (3050, 430), "t_escalate_courier": (3170, 430),
}


TO_BE_PETRI_POSITIONS = {
    "p_start": (70, 285), "t_validate_order": (170, 285), "p_validated": (280, 285), "t_auto_checks_split": (390, 285),
    "p_stock_ready": (510, 190), "t_check_stock": (630, 190), "p_stock_checked": (750, 190),
    "p_payment_ready": (510, 380), "t_authorize_payment": (630, 380), "p_payment_checked": (750, 380),
    "t_checks_join": (870, 285), "p_order_decision": (990, 285), "t_invalid_order": (1110, 160),
    "p_reject_ready": (1230, 160), "t_notify_rejection": (1350, 160), "p_rejected": (1470, 160),
    "t_valid_order": (1110, 380), "p_reserve_ready": (1230, 380), "t_reserve_fulfillment": (1350, 380),
    "p_fulfillment_reserved": (1470, 380), "t_fulfill_split": (1590, 380), "p_invoice_ready": (1710, 255),
    "t_emit_invoice": (1830, 255), "p_invoice_done": (1950, 255), "t_receive_payment": (2070, 255),
    "p_payment_received": (2190, 255), "p_label_ready": (1710, 505), "t_create_label": (1830, 505),
    "p_label_created": (1950, 505), "t_pack_order": (2070, 505), "p_packed": (2190, 505),
    "t_ship_product": (2310, 505), "p_shipped": (2430, 505), "t_fulfillment_join": (2550, 380),
    "p_tracking_ready": (2670, 380), "t_track_shipment": (2790, 380), "p_sla_wait": (2910, 380),
    "t_delivery_confirmed": (3030, 255), "p_delivery_ok": (3150, 255), "t_archive_order": (3270, 255), "p_done": (3390, 255),
    "t_sla_breached": (3030, 505), "p_delay_case": (3150, 505), "t_open_complaint": (3270, 505),
    "p_complaint_open": (3390, 505), "t_notify_customer": (3510, 505), "p_customer_notified": (3630, 505),
    "t_expedite_courier": (3750, 505),
}


def main() -> int:
    as_is_nodes, as_is_flows = as_is_model()
    as_is_data, as_is_associations = as_is_artifacts()
    to_be_nodes, to_be_flows = to_be_model()
    to_be_data, to_be_associations = to_be_artifacts()
    render_bpmn_svg(
        as_is_nodes,
        as_is_flows,
        as_is_data,
        as_is_associations,
        "Assignment 1 As-Is BPMN 2.0 with pool, lanes, and data",
        ROOT / "screenshots/assignment1/as_is_bpmn.svg",
    )
    render_bpmn_svg(
        to_be_nodes,
        to_be_flows,
        to_be_data,
        to_be_associations,
        "Assignment 1 To-Be BPMN 2.0 with pool, lanes, and data",
        ROOT / "screenshots/assignment1/to_be_bpmn.svg",
    )
    render_petri_svg(
        as_is_petri_net(),
        AS_IS_PETRI_POSITIONS,
        "Assignment 1 As-Is Petri Net",
        ROOT / "screenshots/assignment1/as_is_petri_net.svg",
    )
    render_petri_svg(
        to_be_petri_net(),
        TO_BE_PETRI_POSITIONS,
        "Assignment 1 To-Be Petri Net",
        ROOT / "screenshots/assignment1/to_be_petri_net.svg",
    )
    print("Rendered Assignment 1 SVG evidence files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
