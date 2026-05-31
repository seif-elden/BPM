#!/usr/bin/env python3
"""Generate BPMN 2.0 and Petri-net assets for the e-purchase assignment.

The XML can be imported into bpmn.io or Camunda Web Modeler for visual editing
and export. The Petri-net DOT/PNML files provide the second modeling approach
requested for extra coverage without embedding diagrams in LaTeX.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring
from xml.dom import minidom


NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}

for prefix, uri in NS.items():
    register_namespace(prefix, uri)


NodeType = Literal[
    "startEvent",
    "endEvent",
    "task",
    "exclusiveGateway",
    "parallelGateway",
    "eventBasedGateway",
    "intermediateCatchEvent",
]


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeType
    name: str
    x: int
    y: int
    event_definition: str | None = None
    lane: str = "Marketplace system"


@dataclass(frozen=True)
class Flow:
    id: str
    source: str
    target: str
    name: str = ""


@dataclass(frozen=True)
class PetriNet:
    id: str
    name: str
    places: list[tuple[str, str]]
    transitions: list[tuple[str, str]]
    arcs: list[tuple[str, str]]
    initial_place: str
    final_place: str


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def safe_id(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def node_size(kind: str) -> tuple[int, int]:
    if kind in {"startEvent", "endEvent", "intermediateCatchEvent"}:
        return 36, 36
    if kind.endswith("Gateway"):
        return 50, 50
    return 130, 64


def add_text(parent: Element, tag: str, text: str):
    child = SubElement(parent, tag)
    child.text = text
    return child


def build_bpmn(process_id: str, process_name: str, nodes: list[Node], flows: list[Flow]) -> str:
    definitions = Element(
        q("bpmn", "definitions"),
        {
            "id": f"Definitions_{process_id}",
            "targetNamespace": "https://cse346.local/epurchase",
        },
    )
    process = SubElement(
        definitions,
        q("bpmn", "process"),
        {"id": process_id, "name": process_name, "isExecutable": "false"},
    )

    incoming: dict[str, list[str]] = {node.id: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for flow in flows:
        outgoing[flow.source].append(flow.id)
        incoming[flow.target].append(flow.id)

    lanes: list[str] = []
    for node in nodes:
        if node.lane not in lanes:
            lanes.append(node.lane)
    lane_ids = {lane: f"{process_id}_{safe_id(lane)}_Lane" for lane in lanes}
    if lanes:
        lane_set = SubElement(process, q("bpmn", "laneSet"), {"id": f"{process_id}_LaneSet"})
        for lane in lanes:
            lane_el = SubElement(lane_set, q("bpmn", "lane"), {"id": lane_ids[lane], "name": lane})
            for node in nodes:
                if node.lane == lane:
                    add_text(lane_el, q("bpmn", "flowNodeRef"), node.id)

    for node in nodes:
        attrs = {"id": node.id, "name": node.name}
        element = SubElement(process, q("bpmn", node.kind), attrs)
        if node.event_definition == "timer":
            timer = SubElement(element, q("bpmn", "timerEventDefinition"))
            add_text(timer, q("bpmn", "timeDuration"), "P2D")
        elif node.event_definition == "message":
            SubElement(element, q("bpmn", "messageEventDefinition"))
        for flow_id in incoming[node.id]:
            add_text(element, q("bpmn", "incoming"), flow_id)
        for flow_id in outgoing[node.id]:
            add_text(element, q("bpmn", "outgoing"), flow_id)

    for flow in flows:
        attrs = {"id": flow.id, "sourceRef": flow.source, "targetRef": flow.target}
        if flow.name:
            attrs["name"] = flow.name
        SubElement(process, q("bpmn", "sequenceFlow"), attrs)

    diagram = SubElement(definitions, q("bpmndi", "BPMNDiagram"), {"id": f"Diagram_{process_id}"})
    plane = SubElement(
        diagram,
        q("bpmndi", "BPMNPlane"),
        {"id": f"Plane_{process_id}", "bpmnElement": process_id},
    )
    node_lookup = {node.id: node for node in nodes}
    for node in nodes:
        w, h = node_size(node.kind)
        shape = SubElement(
            plane,
            q("bpmndi", "BPMNShape"),
            {"id": f"{node.id}_di", "bpmnElement": node.id},
        )
        SubElement(shape, q("dc", "Bounds"), {"x": str(node.x), "y": str(node.y), "width": str(w), "height": str(h)})

    for lane in lanes:
        lane_nodes = [node for node in nodes if node.lane == lane]
        min_x = min(node.x for node in lane_nodes) - 110
        min_y = min(node.y for node in lane_nodes) - 35
        max_x = max(node.x + node_size(node.kind)[0] for node in lane_nodes) + 90
        max_y = max(node.y + node_size(node.kind)[1] for node in lane_nodes) + 35
        shape = SubElement(
            plane,
            q("bpmndi", "BPMNShape"),
            {"id": f"{lane_ids[lane]}_di", "bpmnElement": lane_ids[lane], "isHorizontal": "true"},
        )
        SubElement(
            shape,
            q("dc", "Bounds"),
            {"x": str(min_x), "y": str(min_y), "width": str(max_x - min_x), "height": str(max_y - min_y)},
        )

    for flow in flows:
        edge = SubElement(
            plane,
            q("bpmndi", "BPMNEdge"),
            {"id": f"{flow.id}_di", "bpmnElement": flow.id},
        )
        source = node_lookup[flow.source]
        target = node_lookup[flow.target]
        sw, sh = node_size(source.kind)
        tw, th = node_size(target.kind)
        SubElement(edge, q("di", "waypoint"), {"x": str(source.x + sw), "y": str(source.y + sh // 2)})
        SubElement(edge, q("di", "waypoint"), {"x": str(target.x), "y": str(target.y + th // 2)})

    rough = tostring(definitions, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def build_petri_dot(net: PetriNet) -> str:
    lines = [
        f'digraph {net.id} {{',
        "  rankdir=LR;",
        '  graph [label="' + net.name + '", labelloc=t, fontsize=18];',
        '  node [fontname="Arial"];',
    ]
    for place_id, label in net.places:
        shape = "doublecircle" if place_id == net.final_place else "circle"
        peripheries = "2" if place_id in {net.initial_place, net.final_place} else "1"
        lines.append(
            f'  {place_id} [shape={shape}, peripheries={peripheries}, '
            f'label="{label}", width=0.9];'
        )
    for transition_id, label in net.transitions:
        style = "dashed,rounded" if label.startswith("silent:") else "rounded"
        fill = ' fillcolor="#f4f4f4", style="filled,' + style + '"' if label.startswith("silent:") else f' style="{style}"'
        lines.append(f'  {transition_id} [shape=box,{fill}, label="{label}"];')
    for source, target in net.arcs:
        lines.append(f"  {source} -> {target};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def add_pnml_name(parent: Element, text: str):
    name = SubElement(parent, "name")
    add_text(name, "text", text)


def build_petri_pnml(net: PetriNet) -> str:
    pnml = Element("pnml")
    net_el = SubElement(
        pnml,
        "net",
        {"id": net.id, "type": "http://www.pnml.org/version-2009/grammar/ptnet"},
    )
    add_pnml_name(net_el, net.name)
    page = SubElement(net_el, "page", {"id": "page1"})

    for place_id, label in net.places:
        place = SubElement(page, "place", {"id": place_id})
        add_pnml_name(place, label)
        if place_id == net.initial_place:
            marking = SubElement(place, "initialMarking")
            add_text(marking, "text", "1")

    for transition_id, label in net.transitions:
        transition = SubElement(page, "transition", {"id": transition_id})
        add_pnml_name(transition, label)

    for index, (source, target) in enumerate(net.arcs, start=1):
        SubElement(page, "arc", {"id": f"a{index:03d}", "source": source, "target": target})

    rough = tostring(pnml, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def as_is_model():
    nodes = [
        Node("Start_Order_Received", "startEvent", "Order received", 80, 70, lane="Customer"),
        Node("Capture_Order", "task", "Capture order", 150, 185),
        Node("Check_Stock", "task", "Check stock", 330, 185),
        Node("Gateway_Stock", "exclusiveGateway", "Stock available?", 510, 192),
        Node("Reject_Order", "task", "Reject order", 610, 120),
        Node("End_Rejected", "endEvent", "Order rejected", 790, 134),
        Node("Reserve_Item", "task", "Reserve item", 610, 255),
        Node("Gateway_Address", "exclusiveGateway", "Address known?", 790, 262),
        Node("Request_Address", "task", "Request address", 880, 330),
        Node("Gateway_Address_Merge", "exclusiveGateway", "Address resolved", 1040, 262),
        Node("Parallel_Prepare", "parallelGateway", "Prepare order", 1140, 262),
        Node("Authorize_Payment", "task", "Authorize payment", 1240, 430, lane="Payment service"),
        Node("Emit_Invoice", "task", "Emit invoice", 1410, 430, lane="Payment service"),
        Node("Receive_Payment", "task", "Receive payment", 1580, 430, lane="Payment service"),
        Node("Pick_Pack", "task", "Pick and pack", 1240, 560, lane="Warehouse"),
        Node("Ship_Product", "task", "Ship product", 1410, 690, lane="Courier"),
        Node("Parallel_Ready", "parallelGateway", "Ready", 1760, 442),
        Node("Gateway_Delivery_Merge", "exclusiveGateway", "Continue wait", 1860, 442),
        Node("Gateway_Delivery_Event", "eventBasedGateway", "Delivery event", 1960, 442),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 2070, 670, "message", lane="Courier"),
        Node("Goods_Delayed", "intermediateCatchEvent", "Goods delayed", 2070, 760, "timer", lane="Courier"),
        Node("Register_Complaint", "task", "Register complaint", 2170, 875, lane="Customer support"),
        Node("Escalate_Courier", "task", "Escalate courier", 2340, 875, lane="Customer support"),
        Node("Archive_Order", "task", "Archive order", 2250, 185),
        Node("End_Order_Closed", "endEvent", "Order closed", 2430, 199),
    ]
    flows = [
        Flow("F01", "Start_Order_Received", "Capture_Order"),
        Flow("F02", "Capture_Order", "Check_Stock"),
        Flow("F03", "Check_Stock", "Gateway_Stock"),
        Flow("F04", "Gateway_Stock", "Reject_Order", "No"),
        Flow("F05", "Reject_Order", "End_Rejected"),
        Flow("F06", "Gateway_Stock", "Reserve_Item", "Yes"),
        Flow("F07", "Reserve_Item", "Gateway_Address"),
        Flow("F08", "Gateway_Address", "Gateway_Address_Merge", "Yes"),
        Flow("F09", "Gateway_Address", "Request_Address", "No"),
        Flow("F10", "Request_Address", "Gateway_Address_Merge"),
        Flow("F11", "Gateway_Address_Merge", "Parallel_Prepare"),
        Flow("F12", "Parallel_Prepare", "Authorize_Payment"),
        Flow("F13", "Authorize_Payment", "Emit_Invoice"),
        Flow("F14", "Emit_Invoice", "Receive_Payment"),
        Flow("F15", "Parallel_Prepare", "Pick_Pack"),
        Flow("F16", "Pick_Pack", "Ship_Product"),
        Flow("F17", "Receive_Payment", "Parallel_Ready"),
        Flow("F18", "Ship_Product", "Parallel_Ready"),
        Flow("F19", "Parallel_Ready", "Gateway_Delivery_Merge"),
        Flow("F20", "Gateway_Delivery_Merge", "Gateway_Delivery_Event"),
        Flow("F21", "Gateway_Delivery_Event", "Delivery_Confirmed", "Delivered"),
        Flow("F22", "Gateway_Delivery_Event", "Goods_Delayed", "2 days late"),
        Flow("F23", "Goods_Delayed", "Register_Complaint"),
        Flow("F24", "Register_Complaint", "Escalate_Courier"),
        Flow("F25", "Escalate_Courier", "Gateway_Delivery_Merge"),
        Flow("F26", "Delivery_Confirmed", "Archive_Order"),
        Flow("F27", "Archive_Order", "End_Order_Closed"),
    ]
    return nodes, flows


def to_be_model():
    nodes = [
        Node("Start_Checkout", "startEvent", "Checkout submitted", 80, 70, lane="Customer"),
        Node("Validate_Order", "task", "Validate order", 150, 185),
        Node("Auto_Checks", "parallelGateway", "Automated checks", 330, 192),
        Node("Check_Stock", "task", "Check stock", 450, 560, lane="Warehouse"),
        Node("Authorize_Payment", "task", "Authorize payment", 450, 430, lane="Payment service"),
        Node("Checks_Join", "parallelGateway", "Checks done", 650, 192),
        Node("Gateway_Valid", "exclusiveGateway", "Order valid?", 760, 192),
        Node("Notify_Rejection", "task", "Notify rejection", 860, 120),
        Node("End_Rejected", "endEvent", "Order rejected", 1040, 134),
        Node("Reserve_Fulfillment", "task", "Reserve fulfillment", 860, 255),
        Node("Prepare_Parallel", "parallelGateway", "Fulfill", 1040, 262),
        Node("Emit_Invoice", "task", "Emit invoice", 1160, 430, lane="Payment service"),
        Node("Receive_Payment", "task", "Receive payment", 1340, 430, lane="Payment service"),
        Node("Create_Label", "task", "Create label", 1160, 560, lane="Warehouse"),
        Node("Pack_Order", "task", "Pack order", 1340, 560, lane="Warehouse"),
        Node("Ship_Product", "task", "Ship product", 1520, 690, lane="Courier"),
        Node("Fulfillment_Join", "parallelGateway", "Sent", 1710, 442),
        Node("Track_Shipment", "task", "Track shipment", 1810, 185),
        Node("Gateway_SLA_Merge", "exclusiveGateway", "Continue tracking", 1990, 192),
        Node("Gateway_SLA", "eventBasedGateway", "SLA event", 2090, 192),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 2210, 670, "message", lane="Courier"),
        Node("SLA_Breach", "intermediateCatchEvent", "SLA breached", 2210, 760, "timer", lane="Courier"),
        Node("Open_Complaint", "task", "Open complaint", 2310, 875, lane="Customer support"),
        Node("Notify_Customer", "task", "Notify customer", 2480, 875, lane="Customer support"),
        Node("Expedite_Courier", "task", "Expedite courier", 2650, 875, lane="Customer support"),
        Node("Archive_Order", "task", "Archive order", 2400, 185),
        Node("End_Closed", "endEvent", "Order closed", 2580, 199),
    ]
    flows = [
        Flow("F01", "Start_Checkout", "Validate_Order"),
        Flow("F02", "Validate_Order", "Auto_Checks"),
        Flow("F03", "Auto_Checks", "Check_Stock"),
        Flow("F04", "Auto_Checks", "Authorize_Payment"),
        Flow("F05", "Check_Stock", "Checks_Join"),
        Flow("F06", "Authorize_Payment", "Checks_Join"),
        Flow("F07", "Checks_Join", "Gateway_Valid"),
        Flow("F08", "Gateway_Valid", "Notify_Rejection", "Invalid"),
        Flow("F09", "Notify_Rejection", "End_Rejected"),
        Flow("F10", "Gateway_Valid", "Reserve_Fulfillment", "Valid"),
        Flow("F11", "Reserve_Fulfillment", "Prepare_Parallel"),
        Flow("F12", "Prepare_Parallel", "Emit_Invoice"),
        Flow("F13", "Prepare_Parallel", "Create_Label"),
        Flow("F14", "Create_Label", "Pack_Order"),
        Flow("F15", "Pack_Order", "Ship_Product"),
        Flow("F16", "Emit_Invoice", "Receive_Payment"),
        Flow("F17", "Receive_Payment", "Fulfillment_Join"),
        Flow("F18", "Ship_Product", "Fulfillment_Join"),
        Flow("F19", "Fulfillment_Join", "Track_Shipment"),
        Flow("F20", "Track_Shipment", "Gateway_SLA_Merge"),
        Flow("F21", "Gateway_SLA_Merge", "Gateway_SLA"),
        Flow("F22", "Gateway_SLA", "Delivery_Confirmed", "Delivered"),
        Flow("F23", "Gateway_SLA", "SLA_Breach", "Late"),
        Flow("F24", "SLA_Breach", "Open_Complaint"),
        Flow("F25", "Open_Complaint", "Notify_Customer"),
        Flow("F26", "Notify_Customer", "Expedite_Courier"),
        Flow("F27", "Expedite_Courier", "Gateway_SLA_Merge"),
        Flow("F28", "Delivery_Confirmed", "Archive_Order"),
        Flow("F29", "Archive_Order", "End_Closed"),
    ]
    return nodes, flows


def as_is_petri_net() -> PetriNet:
    places = [
        ("p_start", "Order received"),
        ("p_captured", "Order captured"),
        ("p_stock_decision", "Stock checked"),
        ("p_stock_available", "Stock available"),
        ("p_reject_ready", "Reject path"),
        ("p_address_decision", "Address decision"),
        ("p_address_missing", "Missing address"),
        ("p_ready_to_prepare", "Ready to prepare"),
        ("p_payment_ready", "Payment branch"),
        ("p_fulfillment_ready", "Fulfillment branch"),
        ("p_payment_authorized", "Payment authorized"),
        ("p_invoice_done", "Invoice emitted"),
        ("p_payment_received", "Payment received"),
        ("p_packed", "Packed"),
        ("p_shipped", "Shipped"),
        ("p_wait_delivery", "Waiting delivery"),
        ("p_delay_case", "Delay active"),
        ("p_complaint_registered", "Complaint registered"),
        ("p_delivery_ok", "Delivery confirmed"),
        ("p_done", "Case closed"),
    ]
    transitions = [
        ("t_capture_order", "Capture order"),
        ("t_check_stock", "Check stock"),
        ("t_stock_no", "silent: no stock"),
        ("t_reject_order", "Reject order"),
        ("t_stock_yes", "silent: stock available"),
        ("t_reserve_item", "Reserve item"),
        ("t_address_no", "silent: address missing"),
        ("t_request_address", "Request address"),
        ("t_address_yes", "silent: address known"),
        ("t_prepare_split", "silent: parallel split"),
        ("t_authorize_payment", "Authorize payment"),
        ("t_emit_invoice", "Emit invoice"),
        ("t_receive_payment", "Receive payment"),
        ("t_pick_pack", "Pick and pack"),
        ("t_ship_product", "Ship product"),
        ("t_prepare_join", "silent: parallel join"),
        ("t_delivery_confirmed", "Message: delivery confirmed"),
        ("t_goods_delayed", "Timer: goods delayed"),
        ("t_register_complaint", "Register complaint"),
        ("t_escalate_courier", "Escalate courier"),
        ("t_archive_order", "Archive order"),
    ]
    arcs = [
        ("p_start", "t_capture_order"),
        ("t_capture_order", "p_captured"),
        ("p_captured", "t_check_stock"),
        ("t_check_stock", "p_stock_decision"),
        ("p_stock_decision", "t_stock_no"),
        ("t_stock_no", "p_reject_ready"),
        ("p_reject_ready", "t_reject_order"),
        ("t_reject_order", "p_done"),
        ("p_stock_decision", "t_stock_yes"),
        ("t_stock_yes", "p_stock_available"),
        ("p_stock_available", "t_reserve_item"),
        ("t_reserve_item", "p_address_decision"),
        ("p_address_decision", "t_address_no"),
        ("t_address_no", "p_address_missing"),
        ("p_address_missing", "t_request_address"),
        ("t_request_address", "p_ready_to_prepare"),
        ("p_address_decision", "t_address_yes"),
        ("t_address_yes", "p_ready_to_prepare"),
        ("p_ready_to_prepare", "t_prepare_split"),
        ("t_prepare_split", "p_payment_ready"),
        ("t_prepare_split", "p_fulfillment_ready"),
        ("p_payment_ready", "t_authorize_payment"),
        ("t_authorize_payment", "p_payment_authorized"),
        ("p_payment_authorized", "t_emit_invoice"),
        ("t_emit_invoice", "p_invoice_done"),
        ("p_invoice_done", "t_receive_payment"),
        ("t_receive_payment", "p_payment_received"),
        ("p_fulfillment_ready", "t_pick_pack"),
        ("t_pick_pack", "p_packed"),
        ("p_packed", "t_ship_product"),
        ("t_ship_product", "p_shipped"),
        ("p_payment_received", "t_prepare_join"),
        ("p_shipped", "t_prepare_join"),
        ("t_prepare_join", "p_wait_delivery"),
        ("p_wait_delivery", "t_delivery_confirmed"),
        ("t_delivery_confirmed", "p_delivery_ok"),
        ("p_delivery_ok", "t_archive_order"),
        ("t_archive_order", "p_done"),
        ("p_wait_delivery", "t_goods_delayed"),
        ("t_goods_delayed", "p_delay_case"),
        ("p_delay_case", "t_register_complaint"),
        ("t_register_complaint", "p_complaint_registered"),
        ("p_complaint_registered", "t_escalate_courier"),
        ("t_escalate_courier", "p_wait_delivery"),
    ]
    return PetriNet(
        id="assignment1_as_is_petri",
        name="Assignment 1 As-Is E-Purchase Petri Net",
        places=places,
        transitions=transitions,
        arcs=arcs,
        initial_place="p_start",
        final_place="p_done",
    )


def to_be_petri_net() -> PetriNet:
    places = [
        ("p_start", "Checkout submitted"),
        ("p_validated", "Order validated"),
        ("p_stock_ready", "Stock check ready"),
        ("p_payment_ready", "Payment check ready"),
        ("p_stock_checked", "Stock checked"),
        ("p_payment_checked", "Payment checked"),
        ("p_order_decision", "Order decision"),
        ("p_reject_ready", "Reject path"),
        ("p_reserve_ready", "Ready to reserve"),
        ("p_fulfillment_reserved", "Fulfillment reserved"),
        ("p_invoice_ready", "Invoice branch"),
        ("p_label_ready", "Label branch"),
        ("p_invoice_done", "Invoice emitted"),
        ("p_payment_received", "Payment received"),
        ("p_label_created", "Label created"),
        ("p_packed", "Packed"),
        ("p_shipped", "Shipped"),
        ("p_tracking_ready", "Tracking ready"),
        ("p_sla_wait", "Waiting SLA event"),
        ("p_delay_case", "Delay active"),
        ("p_complaint_open", "Complaint open"),
        ("p_customer_notified", "Customer notified"),
        ("p_delivery_ok", "Delivery confirmed"),
        ("p_done", "Case closed"),
    ]
    transitions = [
        ("t_validate_order", "Validate order"),
        ("t_auto_checks_split", "silent: automated checks split"),
        ("t_check_stock", "Check stock"),
        ("t_authorize_payment", "Authorize payment"),
        ("t_checks_join", "silent: checks join"),
        ("t_invalid_order", "silent: invalid order"),
        ("t_notify_rejection", "Notify rejection"),
        ("t_valid_order", "silent: valid order"),
        ("t_reserve_fulfillment", "Reserve fulfillment"),
        ("t_fulfill_split", "silent: fulfillment split"),
        ("t_emit_invoice", "Emit invoice"),
        ("t_receive_payment", "Receive payment"),
        ("t_create_label", "Create label"),
        ("t_pack_order", "Pack order"),
        ("t_ship_product", "Ship product"),
        ("t_fulfillment_join", "silent: fulfillment join"),
        ("t_track_shipment", "Track shipment"),
        ("t_delivery_confirmed", "Message: delivery confirmed"),
        ("t_sla_breached", "Timer: SLA breached"),
        ("t_open_complaint", "Open complaint"),
        ("t_notify_customer", "Notify customer"),
        ("t_expedite_courier", "Expedite courier"),
        ("t_archive_order", "Archive order"),
    ]
    arcs = [
        ("p_start", "t_validate_order"),
        ("t_validate_order", "p_validated"),
        ("p_validated", "t_auto_checks_split"),
        ("t_auto_checks_split", "p_stock_ready"),
        ("t_auto_checks_split", "p_payment_ready"),
        ("p_stock_ready", "t_check_stock"),
        ("t_check_stock", "p_stock_checked"),
        ("p_payment_ready", "t_authorize_payment"),
        ("t_authorize_payment", "p_payment_checked"),
        ("p_stock_checked", "t_checks_join"),
        ("p_payment_checked", "t_checks_join"),
        ("t_checks_join", "p_order_decision"),
        ("p_order_decision", "t_invalid_order"),
        ("t_invalid_order", "p_reject_ready"),
        ("p_reject_ready", "t_notify_rejection"),
        ("t_notify_rejection", "p_done"),
        ("p_order_decision", "t_valid_order"),
        ("t_valid_order", "p_reserve_ready"),
        ("p_reserve_ready", "t_reserve_fulfillment"),
        ("t_reserve_fulfillment", "p_fulfillment_reserved"),
        ("p_fulfillment_reserved", "t_fulfill_split"),
        ("t_fulfill_split", "p_invoice_ready"),
        ("t_fulfill_split", "p_label_ready"),
        ("p_invoice_ready", "t_emit_invoice"),
        ("t_emit_invoice", "p_invoice_done"),
        ("p_invoice_done", "t_receive_payment"),
        ("t_receive_payment", "p_payment_received"),
        ("p_label_ready", "t_create_label"),
        ("t_create_label", "p_label_created"),
        ("p_label_created", "t_pack_order"),
        ("t_pack_order", "p_packed"),
        ("p_packed", "t_ship_product"),
        ("t_ship_product", "p_shipped"),
        ("p_payment_received", "t_fulfillment_join"),
        ("p_shipped", "t_fulfillment_join"),
        ("t_fulfillment_join", "p_tracking_ready"),
        ("p_tracking_ready", "t_track_shipment"),
        ("t_track_shipment", "p_sla_wait"),
        ("p_sla_wait", "t_delivery_confirmed"),
        ("t_delivery_confirmed", "p_delivery_ok"),
        ("p_delivery_ok", "t_archive_order"),
        ("t_archive_order", "p_done"),
        ("p_sla_wait", "t_sla_breached"),
        ("t_sla_breached", "p_delay_case"),
        ("p_delay_case", "t_open_complaint"),
        ("t_open_complaint", "p_complaint_open"),
        ("p_complaint_open", "t_notify_customer"),
        ("t_notify_customer", "p_customer_notified"),
        ("p_customer_notified", "t_expedite_courier"),
        ("t_expedite_courier", "p_sla_wait"),
    ]
    return PetriNet(
        id="assignment1_to_be_petri",
        name="Assignment 1 To-Be E-Purchase Petri Net",
        places=places,
        transitions=transitions,
        arcs=arcs,
        initial_place="p_start",
        final_place="p_done",
    )


def main() -> int:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    for process_id, process_name, factory, file_name in [
        ("Epurchase_AsIs", "E-Purchase As-Is Process", as_is_model, "assignment1_epurchase_as_is.bpmn"),
        ("Epurchase_ToBe", "E-Purchase To-Be Process", to_be_model, "assignment1_epurchase_to_be.bpmn"),
    ]:
        nodes, flows = factory()
        xml = build_bpmn(process_id, process_name, nodes, flows)
        (out_dir / file_name).write_text(xml, encoding="utf-8")
    for net, file_stem in [
        (as_is_petri_net(), "assignment1_epurchase_as_is_petri"),
        (to_be_petri_net(), "assignment1_epurchase_to_be_petri"),
    ]:
        (out_dir / f"{file_stem}.dot").write_text(build_petri_dot(net), encoding="utf-8")
        (out_dir / f"{file_stem}.pnml").write_text(build_petri_pnml(net), encoding="utf-8")
    print(f"Wrote BPMN XML and Petri-net files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
