#!/usr/bin/env python3
"""Generate BPMN 2.0 XML models for the e-purchase assignment.

The XML can be imported into bpmn.io or Camunda Web Modeler for visual editing
and export. The report uses a compact TikZ rendering of the same process.
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


@dataclass(frozen=True)
class Flow:
    id: str
    source: str
    target: str
    name: str = ""


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


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


def as_is_model():
    nodes = [
        Node("Start_Order_Received", "startEvent", "Order received", 80, 160),
        Node("Capture_Order", "task", "Capture order", 150, 146),
        Node("Check_Stock", "task", "Check stock", 330, 146),
        Node("Gateway_Stock", "exclusiveGateway", "Stock available?", 510, 153),
        Node("Reject_Order", "task", "Reject order", 610, 60),
        Node("End_Rejected", "endEvent", "Order rejected", 790, 74),
        Node("Reserve_Item", "task", "Reserve item", 610, 146),
        Node("Gateway_Address", "exclusiveGateway", "Address known?", 790, 153),
        Node("Request_Address", "task", "Request address", 880, 245),
        Node("Parallel_Prepare", "parallelGateway", "Prepare order", 980, 153),
        Node("Authorize_Payment", "task", "Authorize payment", 1080, 80),
        Node("Emit_Invoice", "task", "Emit invoice", 1250, 80),
        Node("Pick_Pack", "task", "Pick and pack", 1080, 220),
        Node("Ship_Product", "task", "Ship product", 1250, 220),
        Node("Parallel_Ready", "parallelGateway", "Ready", 1440, 153),
        Node("Gateway_Delivery_Event", "eventBasedGateway", "Delivery event", 1530, 153),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 1630, 92, "message"),
        Node("Goods_Delayed", "intermediateCatchEvent", "Goods delayed", 1630, 232, "timer"),
        Node("Register_Complaint", "task", "Register complaint", 1710, 218),
        Node("Escalate_Courier", "task", "Escalate courier", 1880, 218),
        Node("Archive_Order", "task", "Archive order", 1880, 78),
        Node("End_Order_Closed", "endEvent", "Order closed", 2060, 92),
    ]
    flows = [
        Flow("F01", "Start_Order_Received", "Capture_Order"),
        Flow("F02", "Capture_Order", "Check_Stock"),
        Flow("F03", "Check_Stock", "Gateway_Stock"),
        Flow("F04", "Gateway_Stock", "Reject_Order", "No"),
        Flow("F05", "Reject_Order", "End_Rejected"),
        Flow("F06", "Gateway_Stock", "Reserve_Item", "Yes"),
        Flow("F07", "Reserve_Item", "Gateway_Address"),
        Flow("F08", "Gateway_Address", "Parallel_Prepare", "Yes"),
        Flow("F09", "Gateway_Address", "Request_Address", "No"),
        Flow("F10", "Request_Address", "Parallel_Prepare"),
        Flow("F11", "Parallel_Prepare", "Authorize_Payment"),
        Flow("F12", "Authorize_Payment", "Emit_Invoice"),
        Flow("F13", "Parallel_Prepare", "Pick_Pack"),
        Flow("F14", "Pick_Pack", "Ship_Product"),
        Flow("F15", "Emit_Invoice", "Parallel_Ready"),
        Flow("F16", "Ship_Product", "Parallel_Ready"),
        Flow("F17", "Parallel_Ready", "Gateway_Delivery_Event"),
        Flow("F18", "Gateway_Delivery_Event", "Delivery_Confirmed", "Delivered"),
        Flow("F19", "Gateway_Delivery_Event", "Goods_Delayed", "2 days late"),
        Flow("F20", "Goods_Delayed", "Register_Complaint"),
        Flow("F21", "Register_Complaint", "Escalate_Courier"),
        Flow("F22", "Escalate_Courier", "Delivery_Confirmed"),
        Flow("F23", "Delivery_Confirmed", "Archive_Order"),
        Flow("F24", "Archive_Order", "End_Order_Closed"),
    ]
    return nodes, flows


def to_be_model():
    nodes = [
        Node("Start_Checkout", "startEvent", "Checkout submitted", 80, 160),
        Node("Validate_Order", "task", "Validate order", 150, 146),
        Node("Auto_Checks", "parallelGateway", "Automated checks", 330, 153),
        Node("Check_Stock", "task", "Check stock", 430, 70),
        Node("Authorize_Payment", "task", "Authorize payment", 430, 210),
        Node("Checks_Join", "parallelGateway", "Checks done", 620, 153),
        Node("Gateway_Valid", "exclusiveGateway", "Order valid?", 720, 153),
        Node("Notify_Rejection", "task", "Notify rejection", 820, 60),
        Node("End_Rejected", "endEvent", "Order rejected", 1000, 74),
        Node("Reserve_Fulfillment", "task", "Reserve fulfillment", 820, 146),
        Node("Prepare_Parallel", "parallelGateway", "Fulfill", 1000, 153),
        Node("Emit_Invoice", "task", "Emit invoice", 1100, 70),
        Node("Create_Label", "task", "Create label", 1100, 210),
        Node("Pack_Order", "task", "Pack order", 1270, 210),
        Node("Ship_Product", "task", "Ship product", 1440, 210),
        Node("Fulfillment_Join", "parallelGateway", "Sent", 1610, 153),
        Node("Track_Shipment", "task", "Track shipment", 1700, 146),
        Node("Gateway_SLA", "eventBasedGateway", "SLA event", 1880, 153),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 1980, 92, "message"),
        Node("SLA_Breach", "intermediateCatchEvent", "SLA breached", 1980, 232, "timer"),
        Node("Open_Complaint", "task", "Open complaint", 2060, 218),
        Node("Notify_Customer", "task", "Notify customer", 2230, 218),
        Node("Expedite_Courier", "task", "Expedite courier", 2400, 218),
        Node("Archive_Order", "task", "Archive order", 2230, 78),
        Node("End_Closed", "endEvent", "Order closed", 2410, 92),
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
        Flow("F16", "Emit_Invoice", "Fulfillment_Join"),
        Flow("F17", "Ship_Product", "Fulfillment_Join"),
        Flow("F18", "Fulfillment_Join", "Track_Shipment"),
        Flow("F19", "Track_Shipment", "Gateway_SLA"),
        Flow("F20", "Gateway_SLA", "Delivery_Confirmed", "Delivered"),
        Flow("F21", "Gateway_SLA", "SLA_Breach", "Late"),
        Flow("F22", "SLA_Breach", "Open_Complaint"),
        Flow("F23", "Open_Complaint", "Notify_Customer"),
        Flow("F24", "Notify_Customer", "Expedite_Courier"),
        Flow("F25", "Expedite_Courier", "Gateway_SLA"),
        Flow("F26", "Delivery_Confirmed", "Archive_Order"),
        Flow("F27", "Archive_Order", "End_Closed"),
    ]
    return nodes, flows


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
    print(f"Wrote BPMN XML files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
