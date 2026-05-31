#!/usr/bin/env python3
"""Render Assignment 1 BPMN and Petri-net visuals as SVG evidence files."""

from __future__ import annotations

from html import escape
from pathlib import Path
from textwrap import wrap

from generate_assignment1_bpmn import (
    Flow,
    Node,
    PetriNet,
    as_is_model,
    as_is_petri_net,
    node_size,
    to_be_model,
    to_be_petri_net,
)


ROOT = Path(__file__).resolve().parents[1]
LANES = [
    "Customer",
    "Marketplace system",
    "Payment service",
    "Warehouse",
    "Courier",
    "Customer support",
]


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
    return "\n".join(
        [
            f'<polygon points="{cx:.1f},{y:.1f} {x+w:.1f},{cy:.1f} {cx:.1f},{y+h:.1f} {x:.1f},{cy:.1f}" '
            'fill="#fff" stroke="#20242a" stroke-width="2"/>',
            svg_text([icon], cx, cy + 5, 18, weight="700"),
            svg_text(label_lines(node.name, 18), cx, y + h + 18, 12),
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
    tw, th = node_size(target.kind)
    sx = source.x + shift_x + sw
    sy = source.y + sh / 2
    tx = target.x + shift_x
    ty = target.y + th / 2
    if tx >= sx:
        mid = (sx + tx) / 2
        return [(sx, sy), (mid, sy), (mid, ty), (tx, ty)]
    loop_y = max_y + 45
    return [(sx, sy), (sx + 60, sy), (sx + 60, loop_y), (tx - 60, loop_y), (tx - 60, ty), (tx, ty)]


def polyline(points: list[tuple[float, float]], css_class: str = "flow") -> str:
    value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline class="{css_class}" points="{value}" fill="none" marker-end="url(#arrow)"/>'


def render_bpmn_svg(nodes: list[Node], flows: list[Flow], title: str, out: Path) -> None:
    shift_x = 170
    all_lanes = [lane for lane in LANES if any(node.lane == lane for node in nodes)]
    max_x = max(node.x + shift_x + node_size(node.kind)[0] for node in nodes) + 110
    max_y = max(node.y + node_size(node.kind)[1] for node in nodes) + 70
    min_y = min(node.y for node in nodes) - 45
    height = max_y - min_y + 90

    lookup = {node.id: node for node in nodes}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{max_x:.0f}" height="{height:.0f}" viewBox="0 {min_y:.0f} {max_x:.0f} {height:.0f}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        "</defs>",
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.flow{stroke:#20242a;stroke-width:2.1;stroke-linejoin:round;stroke-linecap:round}.lane-label{fill:#0f766e;font-weight:700}.lane{fill:#f8fafc;stroke:#cbd5e1;stroke-width:1.4}.lane:nth-child(even){fill:#ffffff}.flow-label{fill:#596579;font-size:12px}",
        "</style>",
        '<rect x="0" y="-1000" width="100%" height="3000" fill="#fff"/>',
    ]

    for lane in all_lanes:
        lane_nodes = [node for node in nodes if node.lane == lane]
        lane_y = min(node.y for node in lane_nodes) - 28
        lane_h = max(node.y + node_size(node.kind)[1] for node in lane_nodes) - lane_y + 45
        parts.append(f'<rect class="lane" x="18" y="{lane_y:.1f}" width="{max_x-36:.1f}" height="{lane_h:.1f}"/>')
        parts.append(svg_text(label_lines(lane, 16), 92, lane_y + lane_h / 2 - 4, 14, weight="700"))

    for flow in flows:
        points = route_points(lookup[flow.source], lookup[flow.target], shift_x, max_y)
        parts.append(polyline(points))
        if flow.name:
            mid = points[len(points) // 2]
            parts.append(f'<text class="flow-label" x="{mid[0]:.1f}" y="{mid[1]-6:.1f}" text-anchor="middle">{escape(flow.name)}</text>')

    for node in nodes:
        w, h = node_size(node.kind)
        x = node.x + shift_x
        y = node.y
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


def render_petri_svg(net: PetriNet, positions: dict[str, tuple[float, float]], title: str, out: Path) -> None:
    width = max(x for x, _y in positions.values()) + 130
    height = max(y for _x, y in positions.values()) + 95
    place_labels = dict(net.places)
    transition_labels = dict(net.transitions)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        "<defs>",
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">',
        '<path d="M0,0 L0,6 L9,3 z" fill="#20242a"/>',
        "</marker>",
        "</defs>",
        "<style>",
        "text{font-family:Arial,Helvetica,sans-serif;fill:#20242a}.arc{stroke:#20242a;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}.place{fill:#fff;stroke:#20242a;stroke-width:1.8}.transition{fill:#f8fafc;stroke:#20242a;stroke-width:1.8}.silent{fill:#fff7ed;stroke-dasharray:5 3}",
        "</style>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        svg_text([title], width / 2, 28, 18, weight="700"),
    ]

    for source, target in net.arcs:
        sx, sy = shape_center(source, positions)
        tx, ty = shape_center(target, positions)
        parts.append(polyline([(sx, sy), ((sx + tx) / 2, sy), ((sx + tx) / 2, ty), (tx, ty)], "arc"))

    for place_id, label in net.places:
        x, y = positions[place_id]
        stroke = 3 if place_id in {net.initial_place, net.final_place} else 1.8
        parts.append(f'<circle class="place" cx="{x:.1f}" cy="{y:.1f}" r="27" stroke-width="{stroke}"/>')
        parts.append(svg_text(label_lines(label, 14), x, y + 47, 11))

    for transition_id, label in net.transitions:
        x, y = positions[transition_id]
        css = "transition silent" if label.startswith("silent:") else "transition"
        parts.append(f'<rect class="{css}" x="{x-48:.1f}" y="{y-20:.1f}" width="96" height="40" rx="5" ry="5"/>')
        parts.append(svg_text(label_lines(label, 13), x, y + 4 - (len(label_lines(label, 13)) - 1) * 6, 10))

    parts.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


AS_IS_PETRI_POSITIONS = {
    "p_start": (70, 190), "t_capture_order": (170, 190), "p_captured": (280, 190), "t_check_stock": (390, 190),
    "p_stock_decision": (500, 190), "t_stock_no": (610, 95), "p_reject_ready": (720, 95), "t_reject_order": (830, 95),
    "t_stock_yes": (610, 285), "p_stock_available": (720, 285), "t_reserve_item": (830, 285), "p_address_decision": (950, 285),
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
    "p_reject_ready": (1230, 160), "t_notify_rejection": (1350, 160),
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
    to_be_nodes, to_be_flows = to_be_model()
    render_bpmn_svg(
        as_is_nodes,
        as_is_flows,
        "Assignment 1 As-Is BPMN 2.0 with swimlanes",
        ROOT / "screenshots/assignment1/as_is_bpmn.svg",
    )
    render_bpmn_svg(
        to_be_nodes,
        to_be_flows,
        "Assignment 1 To-Be BPMN 2.0 with swimlanes",
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
