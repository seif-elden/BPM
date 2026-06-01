#!/usr/bin/env python3
"""Generate BPMN 2.0 and Petri-net assets for the e-purchase assignment.

The XML can be imported into bpmn.io or Camunda Web Modeler for visual editing
and export. The Petri-net DOT/PNML files provide the second modeling approach
requested for extra coverage without embedding diagrams in LaTeX.
"""

from __future__ import annotations

import hashlib
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


LANES = [
    "Customer",
    "Marketplace system",
    "Customer support",
    "Payment service",
    "Warehouse",
    "Courier",
]


NodeType = Literal[
    "startEvent",
    "endEvent",
    "task",
    "exclusiveGateway",
    "parallelGateway",
    "eventBasedGateway",
    "intermediateCatchEvent",
]

ArtifactKind = Literal["dataObjectReference", "dataStoreReference"]


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
class DataArtifact:
    id: str
    kind: ArtifactKind
    name: str
    x: int
    y: int
    lane: str = "Marketplace system"


@dataclass(frozen=True)
class DataAssociation:
    id: str
    source: str
    target: str
    direction: str = "None"


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


def artifact_size(kind: str) -> tuple[int, int]:
    if kind == "dataStoreReference":
        return 74, 54
    return 66, 50


def participant_for_lane(lane: str) -> str:
    return {
        "Customer": "Customer",
        "Marketplace system": "E-Commerce Operations",
        "Customer support": "E-Commerce Operations",
        "Payment service": "Payment Service",
        "Warehouse": "Warehouse/Fulfillment",
        "Courier": "Courier/Shipment",
    }[lane]


PARTICIPANT_VERTICAL_OFFSETS = {
    "Customer": 0,
    "E-Commerce Operations": 0,
    "Payment Service": 180,
    "Warehouse/Fulfillment": 290,
    "Courier/Shipment": 390,
}

BPMN_PARTICIPANT_BANDS = {
    "Customer": (18, 140),
    "E-Commerce Operations": (155, 575),
    "Payment Service": (610, 790),
    "Warehouse/Fulfillment": (825, 1010),
    "Courier/Shipment": (1045, 1250),
}

BPMN_ECOM_LANE_BANDS = {
    "Marketplace system": (155, 400),
    "Customer support": (405, 575),
}

BPMN_TARGET_NAMESPACE = "https://bpm-assignment.example.edu/epurchase"


def participant_vertical_offset(lane: str) -> int:
    return PARTICIPANT_VERTICAL_OFFSETS[participant_for_lane(lane)]


def display_y(item: Node | DataArtifact) -> int:
    return item.y + participant_vertical_offset(item.lane)


def generated_id(prefix: str, scope: str, raw_id: str) -> str:
    digest = hashlib.sha1(f"{scope}:{prefix}:{raw_id}".encode("utf-8")).hexdigest()[:7]
    return f"{prefix}_{digest}"


def bpmn_node_prefix(kind: str) -> str:
    if kind == "task":
        return "Activity"
    if kind.endswith("Gateway"):
        return "Gateway"
    if kind.endswith("Event"):
        return "Event"
    return "FlowNode"


def bpmn_data_prefix(kind: str) -> str:
    if kind == "dataStoreReference":
        return "DataStoreReference"
    return "DataObjectReference"


def add_text(parent: Element, tag: str, text: str):
    child = SubElement(parent, tag)
    child.text = text
    return child


def build_bpmn(
    process_id: str,
    process_name: str,
    nodes: list[Node],
    flows: list[Flow],
    artifacts: list[DataArtifact] | None = None,
    associations: list[DataAssociation] | None = None,
    pool_name: str | None = None,
) -> str:
    artifacts = artifacts or []
    associations = associations or []
    participant_order = [
        "Customer",
        "E-Commerce Operations",
        "Payment Service",
        "Warehouse/Fulfillment",
        "Courier/Shipment",
    ]
    definitions_id = generated_id("Definitions", process_id, "definitions")
    collaboration_id = generated_id("Collaboration", process_id, "collaboration")
    diagram_id = generated_id("BPMNDiagram", process_id, "diagram")
    plane_id = generated_id("BPMNPlane", process_id, "plane")
    participant_ids = {
        name: generated_id("Participant", process_id, name) for name in participant_order
    }
    process_ids = {name: generated_id("Process", process_id, name) for name in participant_order}
    lane_ids = {
        (participant, lane): generated_id("Lane", process_id, f"{participant}:{lane}")
        for participant in participant_order
        for lane in LANES
    }
    node_ids = {
        node.id: generated_id(bpmn_node_prefix(node.kind), process_id, node.id) for node in nodes
    }
    artifact_ids = {
        artifact.id: generated_id(bpmn_data_prefix(artifact.kind), process_id, artifact.id)
        for artifact in artifacts
    }
    data_object_ids = {
        artifact.id: generated_id("DataObject", process_id, artifact.id)
        for artifact in artifacts
        if artifact.kind == "dataObjectReference"
    }
    sequence_flow_ids = {flow.id: generated_id("Flow", process_id, flow.id) for flow in flows}
    message_flow_ids = {
        flow.id: generated_id("MessageFlow", process_id, flow.id) for flow in flows
    }
    association_ids = {
        association.id: generated_id("Association", process_id, association.id)
        for association in associations
    }

    node_participant = {node.id: participant_for_lane(node.lane) for node in nodes}
    artifact_participant = {artifact.id: participant_for_lane(artifact.lane) for artifact in artifacts}
    element_participant = {**node_participant, **artifact_participant}
    element_ids = {**node_ids, **artifact_ids}
    item_lookup: dict[str, Node | DataArtifact] = {node.id: node for node in nodes}
    item_lookup.update({artifact.id: artifact for artifact in artifacts})

    sequence_flows = [
        flow for flow in flows if node_participant[flow.source] == node_participant[flow.target]
    ]
    message_flows = [
        flow for flow in flows if node_participant[flow.source] != node_participant[flow.target]
    ]

    definitions = Element(
        q("bpmn", "definitions"),
        {
            "id": definitions_id,
            "targetNamespace": BPMN_TARGET_NAMESPACE,
        },
    )
    collaboration = SubElement(
        definitions,
        q("bpmn", "collaboration"),
        {"id": collaboration_id, "name": f"{process_name} collaboration"},
    )
    for participant in participant_order:
        has_content = any(value == participant for value in element_participant.values())
        if not has_content:
            continue
        SubElement(
            collaboration,
            q("bpmn", "participant"),
            {
                "id": participant_ids[participant],
                "name": participant,
                "processRef": process_ids[participant],
            },
        )
    for flow in message_flows:
        attrs = {
            "id": message_flow_ids[flow.id],
            "sourceRef": node_ids[flow.source],
            "targetRef": node_ids[flow.target],
        }
        if flow.name:
            attrs["name"] = flow.name
        SubElement(collaboration, q("bpmn", "messageFlow"), attrs)

    incoming: dict[str, list[str]] = {node.id: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for flow in sequence_flows:
        outgoing[flow.source].append(sequence_flow_ids[flow.id])
        incoming[flow.target].append(sequence_flow_ids[flow.id])

    for participant in participant_order:
        participant_nodes = [node for node in nodes if node_participant[node.id] == participant]
        participant_artifacts = [artifact for artifact in artifacts if artifact_participant[artifact.id] == participant]
        if not participant_nodes and not participant_artifacts:
            continue
        process = SubElement(
            definitions,
            q("bpmn", "process"),
            {"id": process_ids[participant], "name": f"{participant} process", "isExecutable": "false"},
        )

        lanes: list[str] = []
        for node in participant_nodes:
            if node.lane not in lanes:
                lanes.append(node.lane)
        for artifact in participant_artifacts:
            if artifact.lane not in lanes:
                lanes.append(artifact.lane)
        if len(lanes) > 1:
            lane_set = SubElement(
                process,
                q("bpmn", "laneSet"),
                {"id": generated_id("LaneSet", process_id, participant)},
            )
            for lane in lanes:
                lane_el = SubElement(
                    lane_set,
                    q("bpmn", "lane"),
                    {"id": lane_ids[(participant, lane)], "name": lane},
                )
                for node in participant_nodes:
                    if node.lane == lane:
                        add_text(lane_el, q("bpmn", "flowNodeRef"), node_ids[node.id])

        for node in participant_nodes:
            attrs = {"id": node_ids[node.id], "name": node.name}
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

        for artifact in participant_artifacts:
            if artifact.kind == "dataObjectReference":
                data_object_id = data_object_ids[artifact.id]
                SubElement(process, q("bpmn", "dataObject"), {"id": data_object_id, "name": artifact.name})
                SubElement(
                    process,
                    q("bpmn", "dataObjectReference"),
                    {
                        "id": artifact_ids[artifact.id],
                        "name": artifact.name,
                        "dataObjectRef": data_object_id,
                    },
                )
            else:
                SubElement(
                    process,
                    q("bpmn", "dataStoreReference"),
                    {"id": artifact_ids[artifact.id], "name": artifact.name},
                )

        for flow in sequence_flows:
            if node_participant[flow.source] != participant:
                continue
            attrs = {
                "id": sequence_flow_ids[flow.id],
                "sourceRef": node_ids[flow.source],
                "targetRef": node_ids[flow.target],
            }
            if flow.name:
                attrs["name"] = flow.name
            SubElement(process, q("bpmn", "sequenceFlow"), attrs)

        for association in associations:
            source_participant = element_participant.get(association.source)
            target_participant = element_participant.get(association.target)
            if source_participant != participant or target_participant != participant:
                continue
            SubElement(
                process,
                q("bpmn", "association"),
                {
                    "id": association_ids[association.id],
                    "sourceRef": element_ids[association.source],
                    "targetRef": element_ids[association.target],
                    "associationDirection": association.direction,
                },
            )

    diagram = SubElement(definitions, q("bpmndi", "BPMNDiagram"), {"id": diagram_id})
    plane = SubElement(
        diagram,
        q("bpmndi", "BPMNPlane"),
        {"id": plane_id, "bpmnElement": collaboration_id},
    )

    item_bounds: dict[str, tuple[int, int, int, int]] = {}
    for node in nodes:
        w, h = node_size(node.kind)
        item_bounds[node.id] = (node.x, display_y(node), w, h)
    for artifact in artifacts:
        w, h = artifact_size(artifact.kind)
        item_bounds[artifact.id] = (artifact.x, display_y(artifact), w, h)

    diagram_x = 0
    diagram_width = max(x + w for x, _y, w, _h in item_bounds.values()) + 140

    for participant in participant_order:
        participant_items = [
            item_id for item_id, value in element_participant.items() if value == participant
        ]
        if not participant_items:
            continue
        bounds = [item_bounds[item_id] for item_id in participant_items]
        dynamic_min_y = min(y for _x, y, _w, _h in bounds) - 20
        dynamic_max_y = max(y + h for _x, y, _w, h in bounds) + 20
        min_y, max_y = BPMN_PARTICIPANT_BANDS.get(participant, (dynamic_min_y, dynamic_max_y))
        pool_shape = SubElement(
            plane,
            q("bpmndi", "BPMNShape"),
            {
                "id": generated_id("BPMNShape", process_id, f"participant:{participant}"),
                "bpmnElement": participant_ids[participant],
                "isHorizontal": "true",
            },
        )
        SubElement(
            pool_shape,
            q("dc", "Bounds"),
            {
                "x": str(diagram_x),
                "y": str(min_y),
                "width": str(diagram_width),
                "height": str(max_y - min_y),
            },
        )

        lanes = sorted({item_lookup[item_id].lane for item_id in participant_items}, key=lambda lane: LANES.index(lane) if lane in LANES else 99)
        if len(lanes) > 1:
            for lane in lanes:
                lane_items = [item_id for item_id in participant_items if item_lookup[item_id].lane == lane]
                lane_bounds = [item_bounds[item_id] for item_id in lane_items]
                dynamic_lane_min_y = min(y for _x, y, _w, _h in lane_bounds) - 14
                dynamic_lane_max_y = max(y + h for _x, y, _w, h in lane_bounds) + 14
                lane_min_y, lane_max_y = BPMN_ECOM_LANE_BANDS.get(
                    lane, (dynamic_lane_min_y, dynamic_lane_max_y)
                )
                lane_id = lane_ids[(participant, lane)]
                lane_shape = SubElement(
                    plane,
                    q("bpmndi", "BPMNShape"),
                    {
                        "id": generated_id("BPMNShape", process_id, f"lane:{participant}:{lane}"),
                        "bpmnElement": lane_id,
                        "isHorizontal": "true",
                    },
                )
                SubElement(
                    lane_shape,
                    q("dc", "Bounds"),
                    {
                        "x": str(diagram_x + 44),
                        "y": str(lane_min_y),
                        "width": str(diagram_width - 44),
                        "height": str(lane_max_y - lane_min_y),
                    },
                )

    for node in nodes:
        w, h = node_size(node.kind)
        shape = SubElement(
            plane,
            q("bpmndi", "BPMNShape"),
            {
                "id": generated_id("BPMNShape", process_id, f"node:{node.id}"),
                "bpmnElement": node_ids[node.id],
            },
        )
        SubElement(shape, q("dc", "Bounds"), {"x": str(node.x), "y": str(display_y(node)), "width": str(w), "height": str(h)})

    for artifact in artifacts:
        w, h = artifact_size(artifact.kind)
        shape = SubElement(
            plane,
            q("bpmndi", "BPMNShape"),
            {
                "id": generated_id("BPMNShape", process_id, f"artifact:{artifact.id}"),
                "bpmnElement": artifact_ids[artifact.id],
            },
        )
        SubElement(shape, q("dc", "Bounds"), {"x": str(artifact.x), "y": str(display_y(artifact)), "width": str(w), "height": str(h)})

    node_lookup = {node.id: node for node in nodes}

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

    def flow_waypoints(source: Node, target: Node, is_message: bool = False) -> list[tuple[float, float]]:
        sw, sh = node_size(source.kind)
        _tw, th = node_size(target.kind)
        source_y = display_y(source)
        target_y = display_y(target)
        if is_message:
            tw, th = node_size(target.kind)
            source_center = (source.x + sw / 2, source_y + sh / 2)
            target_center = (target.x + tw / 2, target_y + th / 2)
            return [
                boundary_point(source_center, (sw, sh), target_center),
                boundary_point(target_center, (tw, th), source_center),
            ]

        if not is_message and source.kind == "exclusiveGateway" and target_y > source_y + 35:
            sx = source.x + sw / 2
            sy = source_y + sh
            tx = target.x
            ty = target_y + th / 2
            mid_y = (sy + ty) / 2
            return [(sx, sy), (sx, mid_y), (tx, mid_y), (tx, ty)]

        sx = source.x + sw
        sy = source_y + sh / 2
        tx = target.x
        ty = target_y + th / 2
        if tx >= sx:
            mid = (sx + tx) / 2
            return [(sx, sy), (mid, sy), (mid, ty), (tx, ty)]

        if not is_message and participant_for_lane(source.lane) == participant_for_lane(target.lane) == "E-Commerce Operations":
            local_y = BPMN_ECOM_LANE_BANDS["Marketplace system"][1] + 2
            return [
                (sx, sy),
                (sx + 45, sy),
                (sx + 45, local_y),
                (tx - 55, local_y),
                (tx - 55, ty),
                (tx, ty),
            ]

        side_x = max(sx, tx) + 70
        return [(sx, sy), (side_x, sy), (side_x, ty), (tx, ty)]

    def association_waypoints(source: Node | DataArtifact, target: Node | DataArtifact) -> list[tuple[float, float]]:
        if isinstance(source, Node):
            sw, sh = node_size(source.kind)
        else:
            sw, sh = artifact_size(source.kind)
        if isinstance(target, Node):
            tw, th = node_size(target.kind)
        else:
            tw, th = artifact_size(target.kind)

        sx = source.x + sw / 2
        sy = display_y(source) + sh / 2
        tx = target.x + tw / 2
        ty = display_y(target) + th / 2
        if abs(sx - tx) < 90:
            return [(sx, sy), (tx, ty)]
        mid_x = sx + (30 if tx > sx else -30)
        return [(sx, sy), (mid_x, sy), (mid_x, ty), (tx, ty)]

    def add_waypoints(edge: Element, points: list[tuple[float, float]]) -> None:
        for x, y in points:
            SubElement(edge, q("di", "waypoint"), {"x": f"{x:.1f}", "y": f"{y:.1f}"})

    for flow in sequence_flows:
        edge = SubElement(
            plane,
            q("bpmndi", "BPMNEdge"),
            {
                "id": generated_id("BPMNEdge", process_id, f"sequence:{flow.id}"),
                "bpmnElement": sequence_flow_ids[flow.id],
            },
        )
        source = node_lookup[flow.source]
        target = node_lookup[flow.target]
        add_waypoints(edge, flow_waypoints(source, target))

    for flow in message_flows:
        edge = SubElement(
            plane,
            q("bpmndi", "BPMNEdge"),
            {
                "id": generated_id("BPMNEdge", process_id, f"message:{flow.id}"),
                "bpmnElement": message_flow_ids[flow.id],
            },
        )
        source = node_lookup[flow.source]
        target = node_lookup[flow.target]
        add_waypoints(edge, flow_waypoints(source, target, is_message=True))

    for association in associations:
        source_participant = element_participant.get(association.source)
        target_participant = element_participant.get(association.target)
        if source_participant != target_participant:
            continue
        edge = SubElement(
            plane,
            q("bpmndi", "BPMNEdge"),
            {
                "id": generated_id("BPMNEdge", process_id, f"association:{association.id}"),
                "bpmnElement": association_ids[association.id],
            },
        )
        source = item_lookup[association.source]
        target = item_lookup[association.target]
        add_waypoints(edge, association_waypoints(source, target))

    rough = tostring(definitions, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")

def build_petri_dot(net: PetriNet) -> str:
    place_ids = {
        place_id: generated_id("Place", net.id, place_id) for place_id, _label in net.places
    }
    transition_ids = {
        transition_id: generated_id("Transition", net.id, transition_id)
        for transition_id, _label in net.transitions
    }
    sink_places = {place_id for place_id, _label in net.places} - {
        source for source, _target in net.arcs
    }
    lines = [
        f'digraph {generated_id("Net", net.id, "net")} {{',
        "  rankdir=LR;",
        '  graph [label="' + net.name + '", labelloc=t, fontsize=18];',
        '  node [fontname="Arial"];',
    ]
    for place_id, label in net.places:
        shape = "doublecircle" if place_id in sink_places else "circle"
        peripheries = "2" if place_id in {net.initial_place, *sink_places} else "1"
        lines.append(
            f'  {place_ids[place_id]} [shape={shape}, peripheries={peripheries}, '
            f'label="{label}", width=0.9];'
        )
    for transition_id, label in net.transitions:
        lines.append(f'  {transition_ids[transition_id]} [shape=box, style="rounded", label="{label}"];')
    for source, target in net.arcs:
        source_id = place_ids.get(source, transition_ids.get(source))
        target_id = place_ids.get(target, transition_ids.get(target))
        lines.append(f"  {source_id} -> {target_id};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def add_pnml_name(parent: Element, text: str):
    name = SubElement(parent, "name")
    add_text(name, "text", text)


def build_petri_pnml(net: PetriNet) -> str:
    place_ids = {
        place_id: generated_id("Place", net.id, place_id) for place_id, _label in net.places
    }
    transition_ids = {
        transition_id: generated_id("Transition", net.id, transition_id)
        for transition_id, _label in net.transitions
    }
    pnml = Element("pnml")
    net_el = SubElement(
        pnml,
        "net",
        {"id": generated_id("Net", net.id, "net"), "type": "http://www.pnml.org/version-2009/grammar/ptnet"},
    )
    add_pnml_name(net_el, net.name)
    page = SubElement(net_el, "page", {"id": generated_id("Page", net.id, "page")})

    for place_id, label in net.places:
        place = SubElement(page, "place", {"id": place_ids[place_id]})
        add_pnml_name(place, label)
        if place_id == net.initial_place:
            marking = SubElement(place, "initialMarking")
            add_text(marking, "text", "1")

    for transition_id, label in net.transitions:
        transition = SubElement(page, "transition", {"id": transition_ids[transition_id]})
        add_pnml_name(transition, label)

    for index, (source, target) in enumerate(net.arcs, start=1):
        source_id = place_ids.get(source, transition_ids.get(source))
        target_id = place_ids.get(target, transition_ids.get(target))
        SubElement(
            page,
            "arc",
            {
                "id": generated_id("Arc", net.id, f"{index}:{source}:{target}"),
                "source": source_id,
                "target": target_id,
            },
        )

    rough = tostring(pnml, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def as_is_model():
    nodes = [
        Node("Start_Order_Received", "startEvent", "Order received", 80, 70, lane="Customer"),
        Node("Capture_Order", "task", "Capture order", 150, 185),
        Node("Check_Stock", "task", "Check stock", 330, 185),
        Node("Gateway_Stock", "exclusiveGateway", "Stock available?", 510, 192),
        Node("Reject_Order", "task", "Reject order", 610, 155),
        Node("End_Rejected", "endEvent", "Order rejected", 790, 169),
        Node("Reserve_Item", "task", "Reserve item", 610, 255),
        Node("Gateway_Address", "exclusiveGateway", "Address known?", 790, 262),
        Node("Request_Address", "task", "Request address", 880, 330),
        Node("Confirm_Order_Details", "task", "Confirm order details", 1040, 255),
        Node("Parallel_Prepare", "parallelGateway", "Prepare order", 1230, 262),
        Node("Send_Payment_Request", "task", "Send payment request", 1330, 205),
        Node("Send_Fulfillment_Request", "task", "Send fulfillment request", 1330, 315),
        Node("Receive_Payment_Status", "task", "Receive payment status", 1670, 205),
        Node("Receive_Shipment_Status", "task", "Receive shipment status", 1670, 315),
        Node("Authorize_Payment", "task", "Authorize payment", 1330, 450, lane="Payment service"),
        Node("Emit_Invoice", "task", "Emit invoice", 1500, 450, lane="Payment service"),
        Node("Receive_Payment", "task", "Receive payment", 1670, 450, lane="Payment service"),
        Node("Pick_Pack", "task", "Pick and pack", 1330, 560, lane="Warehouse"),
        Node("Ship_Product", "task", "Ship product", 1500, 690, lane="Courier"),
        Node("Parallel_Ready", "parallelGateway", "Ready", 1850, 262),
        Node("Monitor_Delivery", "task", "Monitor delivery", 1950, 255),
        Node("Gateway_Delivery_Event", "exclusiveGateway", "Delivery status?", 2140, 262),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 2250, 185, "message"),
        Node("Goods_Delayed", "intermediateCatchEvent", "Goods delayed", 2250, 420, "timer", lane="Customer support"),
        Node("Register_Complaint", "task", "Register complaint", 2350, 420, lane="Customer support"),
        Node("Escalate_Courier", "task", "Escalate courier", 2520, 420, lane="Customer support"),
        Node("Archive_Order", "task", "Archive order", 2430, 185),
        Node("End_Order_Closed", "endEvent", "Order closed", 2610, 199),
    ]
    flows = [
        Flow("F01", "Start_Order_Received", "Capture_Order"),
        Flow("F02", "Capture_Order", "Check_Stock"),
        Flow("F03", "Check_Stock", "Gateway_Stock"),
        Flow("F04", "Gateway_Stock", "Reject_Order", "No"),
        Flow("F05", "Reject_Order", "End_Rejected"),
        Flow("F06", "Gateway_Stock", "Reserve_Item", "Yes"),
        Flow("F07", "Reserve_Item", "Gateway_Address"),
        Flow("F08", "Gateway_Address", "Confirm_Order_Details", "Yes"),
        Flow("F09", "Gateway_Address", "Request_Address", "No"),
        Flow("F10", "Request_Address", "Confirm_Order_Details"),
        Flow("F11", "Confirm_Order_Details", "Parallel_Prepare"),
        Flow("F12", "Parallel_Prepare", "Send_Payment_Request"),
        Flow("F13", "Send_Payment_Request", "Receive_Payment_Status"),
        Flow("F14", "Receive_Payment_Status", "Parallel_Ready"),
        Flow("F15", "Parallel_Prepare", "Send_Fulfillment_Request"),
        Flow("F16", "Send_Fulfillment_Request", "Receive_Shipment_Status"),
        Flow("F17", "Receive_Shipment_Status", "Parallel_Ready"),
        Flow("F18", "Send_Payment_Request", "Authorize_Payment", "Payment request"),
        Flow("F19", "Authorize_Payment", "Emit_Invoice"),
        Flow("F20", "Emit_Invoice", "Receive_Payment"),
        Flow("F21", "Receive_Payment", "Receive_Payment_Status", "Payment status"),
        Flow("F22", "Send_Fulfillment_Request", "Pick_Pack", "Fulfillment request"),
        Flow("F23", "Pick_Pack", "Ship_Product", "Parcel handoff"),
        Flow("F24", "Ship_Product", "Receive_Shipment_Status", "Shipment status"),
        Flow("F25", "Parallel_Ready", "Monitor_Delivery"),
        Flow("F26", "Monitor_Delivery", "Gateway_Delivery_Event"),
        Flow("F27", "Gateway_Delivery_Event", "Delivery_Confirmed", "Delivered"),
        Flow("F28", "Gateway_Delivery_Event", "Goods_Delayed", "2 days late"),
        Flow("F29", "Goods_Delayed", "Register_Complaint"),
        Flow("F30", "Register_Complaint", "Escalate_Courier"),
        Flow("F31", "Escalate_Courier", "Monitor_Delivery"),
        Flow("F32", "Delivery_Confirmed", "Archive_Order"),
        Flow("F33", "Archive_Order", "End_Order_Closed"),
    ]
    return nodes, flows


def to_be_model():
    nodes = [
        Node("Start_Checkout", "startEvent", "Checkout submitted", 80, 70, lane="Customer"),
        Node("Validate_Order", "task", "Validate order", 150, 185),
        Node("Auto_Checks", "parallelGateway", "Automated checks", 330, 192),
        Node("Send_Payment_Precheck", "task", "Send payment pre-check", 440, 150),
        Node("Send_Stock_Query", "task", "Send stock query", 440, 250),
        Node("Receive_Payment_Precheck", "task", "Receive pre-check status", 620, 150),
        Node("Receive_Stock_Status", "task", "Receive stock status", 620, 250),
        Node("Check_Stock", "task", "Check stock", 440, 560, lane="Warehouse"),
        Node("Authorize_Payment", "task", "Authorize payment", 440, 450, lane="Payment service"),
        Node("Checks_Join", "parallelGateway", "Checks done", 800, 192),
        Node("Review_Check_Results", "task", "Review check results", 900, 185),
        Node("Gateway_Valid", "exclusiveGateway", "Order valid?", 1080, 192),
        Node("Notify_Rejection", "task", "Notify rejection", 1180, 155),
        Node("End_Rejected", "endEvent", "Order rejected", 1360, 169),
        Node("Reserve_Fulfillment", "task", "Reserve fulfillment", 1180, 255),
        Node("Prepare_Parallel", "parallelGateway", "Fulfill", 1360, 262),
        Node("Send_Invoice_Request", "task", "Send invoice request", 1480, 205),
        Node("Send_Label_Request", "task", "Send label request", 1480, 315),
        Node("Receive_Payment_Status", "task", "Receive payment status", 1830, 205),
        Node("Receive_Shipment_Status", "task", "Receive shipment status", 1830, 315),
        Node("Emit_Invoice", "task", "Emit invoice", 1480, 450, lane="Payment service"),
        Node("Receive_Payment", "task", "Receive payment", 1660, 450, lane="Payment service"),
        Node("Create_Label", "task", "Create label", 1480, 560, lane="Warehouse"),
        Node("Pack_Order", "task", "Pack order", 1660, 560, lane="Warehouse"),
        Node("Ship_Product", "task", "Ship product", 1840, 690, lane="Courier"),
        Node("Fulfillment_Join", "parallelGateway", "Sent", 2030, 262),
        Node("Track_Shipment", "task", "Track shipment", 2130, 185),
        Node("Gateway_SLA", "exclusiveGateway", "SLA status?", 2330, 192),
        Node("Delivery_Confirmed", "intermediateCatchEvent", "Delivery confirmed", 2450, 185, "message"),
        Node("SLA_Breach", "intermediateCatchEvent", "SLA breached", 2450, 420, "timer", lane="Customer support"),
        Node("Open_Complaint", "task", "Open complaint", 2550, 420, lane="Customer support"),
        Node("Notify_Customer", "task", "Notify customer", 2720, 420, lane="Customer support"),
        Node("Expedite_Courier", "task", "Expedite courier", 2890, 420, lane="Customer support"),
        Node("Archive_Order", "task", "Archive order", 2640, 185),
        Node("End_Closed", "endEvent", "Order closed", 2820, 199),
    ]
    flows = [
        Flow("F01", "Start_Checkout", "Validate_Order"),
        Flow("F02", "Validate_Order", "Auto_Checks"),
        Flow("F03", "Auto_Checks", "Send_Payment_Precheck"),
        Flow("F04", "Auto_Checks", "Send_Stock_Query"),
        Flow("F05", "Send_Payment_Precheck", "Receive_Payment_Precheck"),
        Flow("F06", "Send_Stock_Query", "Receive_Stock_Status"),
        Flow("F07", "Receive_Payment_Precheck", "Checks_Join"),
        Flow("F08", "Receive_Stock_Status", "Checks_Join"),
        Flow("F09", "Send_Stock_Query", "Check_Stock", "Stock query"),
        Flow("F10", "Check_Stock", "Receive_Stock_Status", "Stock status"),
        Flow("F11", "Send_Payment_Precheck", "Authorize_Payment", "Payment pre-check"),
        Flow("F12", "Authorize_Payment", "Receive_Payment_Precheck", "Pre-check status"),
        Flow("F13", "Checks_Join", "Review_Check_Results"),
        Flow("F14", "Review_Check_Results", "Gateway_Valid"),
        Flow("F15", "Gateway_Valid", "Notify_Rejection", "Invalid"),
        Flow("F16", "Notify_Rejection", "End_Rejected"),
        Flow("F17", "Gateway_Valid", "Reserve_Fulfillment", "Valid"),
        Flow("F18", "Reserve_Fulfillment", "Prepare_Parallel"),
        Flow("F19", "Prepare_Parallel", "Send_Invoice_Request"),
        Flow("F20", "Send_Invoice_Request", "Receive_Payment_Status"),
        Flow("F21", "Receive_Payment_Status", "Fulfillment_Join"),
        Flow("F22", "Prepare_Parallel", "Send_Label_Request"),
        Flow("F23", "Send_Label_Request", "Receive_Shipment_Status"),
        Flow("F24", "Receive_Shipment_Status", "Fulfillment_Join"),
        Flow("F25", "Send_Invoice_Request", "Emit_Invoice", "Invoice request"),
        Flow("F26", "Emit_Invoice", "Receive_Payment"),
        Flow("F27", "Receive_Payment", "Receive_Payment_Status", "Payment status"),
        Flow("F28", "Send_Label_Request", "Create_Label", "Label request"),
        Flow("F29", "Create_Label", "Pack_Order"),
        Flow("F30", "Pack_Order", "Ship_Product", "Parcel handoff"),
        Flow("F31", "Ship_Product", "Receive_Shipment_Status", "Shipment status"),
        Flow("F32", "Fulfillment_Join", "Track_Shipment"),
        Flow("F33", "Track_Shipment", "Gateway_SLA"),
        Flow("F34", "Gateway_SLA", "Delivery_Confirmed", "Delivered"),
        Flow("F35", "Gateway_SLA", "SLA_Breach", "Late"),
        Flow("F36", "SLA_Breach", "Open_Complaint"),
        Flow("F37", "Open_Complaint", "Notify_Customer"),
        Flow("F38", "Notify_Customer", "Expedite_Courier"),
        Flow("F39", "Expedite_Courier", "Track_Shipment"),
        Flow("F40", "Delivery_Confirmed", "Archive_Order"),
        Flow("F41", "Archive_Order", "End_Closed"),
    ]
    return nodes, flows


def as_is_artifacts() -> tuple[list[DataArtifact], list[DataAssociation]]:
    artifacts = [
        DataArtifact("Data_Order_Request", "dataObjectReference", "Order request", 0, 25, lane="Customer"),
        DataArtifact("Data_Stock_Record", "dataStoreReference", "Product/stock data", 330, 270),
        DataArtifact("Data_Address_Profile", "dataObjectReference", "Customer address", 930, 205),
        DataArtifact("Data_Payment_Record", "dataObjectReference", "Payment record", 1670, 535, lane="Payment service"),
        DataArtifact("Data_Invoice", "dataObjectReference", "Invoice", 1500, 535, lane="Payment service"),
        DataArtifact("Data_Pick_List", "dataObjectReference", "Pick list", 1330, 640, lane="Warehouse"),
        DataArtifact("Data_Shipment_Record", "dataStoreReference", "Shipment tracking", 1500, 775, lane="Courier"),
        DataArtifact("Data_Complaint_Case", "dataObjectReference", "Complaint case", 2320, 500, lane="Customer support"),
        DataArtifact("Data_Order_Archive", "dataStoreReference", "Order archive", 2530, 255),
    ]
    associations = [
        DataAssociation("A01", "Start_Order_Received", "Data_Order_Request", "One"),
        DataAssociation("A02", "Data_Stock_Record", "Check_Stock", "One"),
        DataAssociation("A03", "Reserve_Item", "Data_Stock_Record", "One"),
        DataAssociation("A04", "Data_Address_Profile", "Gateway_Address", "One"),
        DataAssociation("A05", "Request_Address", "Data_Address_Profile", "One"),
        DataAssociation("A06", "Authorize_Payment", "Data_Payment_Record", "One"),
        DataAssociation("A07", "Emit_Invoice", "Data_Invoice", "One"),
        DataAssociation("A08", "Receive_Payment", "Data_Payment_Record", "One"),
        DataAssociation("A09", "Pick_Pack", "Data_Pick_List", "One"),
        DataAssociation("A10", "Ship_Product", "Data_Shipment_Record", "One"),
        DataAssociation("A11", "Data_Shipment_Record", "Delivery_Confirmed", "One"),
        DataAssociation("A12", "Register_Complaint", "Data_Complaint_Case", "One"),
        DataAssociation("A13", "Escalate_Courier", "Data_Complaint_Case", "One"),
        DataAssociation("A14", "Archive_Order", "Data_Order_Archive", "One"),
    ]
    return artifacts, associations


def to_be_artifacts() -> tuple[list[DataArtifact], list[DataAssociation]]:
    artifacts = [
        DataArtifact("Data_Checkout_Record", "dataObjectReference", "Checkout/order record", 0, 25, lane="Customer"),
        DataArtifact("Data_Customer_Profile", "dataObjectReference", "Customer profile", 150, 275),
        DataArtifact("Data_Inventory_Record", "dataStoreReference", "Inventory record", 440, 640, lane="Warehouse"),
        DataArtifact("Data_Payment_Authorization", "dataObjectReference", "Payment authorization", 500, 535, lane="Payment service"),
        DataArtifact("Data_Invoice", "dataObjectReference", "Invoice", 1480, 535, lane="Payment service"),
        DataArtifact("Data_Shipping_Label", "dataObjectReference", "Shipping label", 1480, 640, lane="Warehouse"),
        DataArtifact("Data_Tracking_Record", "dataStoreReference", "Tracking record", 1840, 775, lane="Courier"),
        DataArtifact("Data_Complaint_Case", "dataObjectReference", "Complaint case", 2460, 500, lane="Customer support"),
        DataArtifact("Data_Audit_Log", "dataStoreReference", "Audit/order archive", 2770, 255),
    ]
    associations = [
        DataAssociation("A01", "Start_Checkout", "Data_Checkout_Record", "One"),
        DataAssociation("A02", "Data_Customer_Profile", "Validate_Order", "One"),
        DataAssociation("A03", "Data_Inventory_Record", "Check_Stock", "One"),
        DataAssociation("A04", "Reserve_Fulfillment", "Data_Inventory_Record", "One"),
        DataAssociation("A05", "Authorize_Payment", "Data_Payment_Authorization", "One"),
        DataAssociation("A06", "Emit_Invoice", "Data_Invoice", "One"),
        DataAssociation("A07", "Receive_Payment", "Data_Payment_Authorization", "One"),
        DataAssociation("A08", "Create_Label", "Data_Shipping_Label", "One"),
        DataAssociation("A09", "Ship_Product", "Data_Tracking_Record", "One"),
        DataAssociation("A10", "Track_Shipment", "Data_Tracking_Record", "One"),
        DataAssociation("A11", "Data_Tracking_Record", "Delivery_Confirmed", "One"),
        DataAssociation("A12", "Open_Complaint", "Data_Complaint_Case", "One"),
        DataAssociation("A13", "Notify_Customer", "Data_Complaint_Case", "One"),
        DataAssociation("A14", "Expedite_Courier", "Data_Complaint_Case", "One"),
        DataAssociation("A15", "Archive_Order", "Data_Audit_Log", "One"),
    ]
    return artifacts, associations

def as_is_petri_net() -> PetriNet:
    places = [
        ("p_start", "Order received"),
        ("p_captured", "Order captured"),
        ("p_stock_decision", "Stock checked"),
        ("p_stock_available", "Stock available"),
        ("p_reject_ready", "Reject path"),
        ("p_rejected", "Order rejected"),
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
        ("t_stock_no", "No stock"),
        ("t_reject_order", "Reject order"),
        ("t_stock_yes", "Stock available"),
        ("t_reserve_item", "Reserve item"),
        ("t_address_no", "Address missing"),
        ("t_request_address", "Request address"),
        ("t_address_yes", "Address known"),
        ("t_prepare_split", "Parallel split"),
        ("t_authorize_payment", "Authorize payment"),
        ("t_emit_invoice", "Emit invoice"),
        ("t_receive_payment", "Receive payment"),
        ("t_pick_pack", "Pick and pack"),
        ("t_ship_product", "Ship product"),
        ("t_prepare_join", "Parallel join"),
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
        ("t_reject_order", "p_rejected"),
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
        ("p_rejected", "Order rejected"),
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
        ("t_auto_checks_split", "Automated checks split"),
        ("t_check_stock", "Check stock"),
        ("t_authorize_payment", "Authorize payment"),
        ("t_checks_join", "Checks join"),
        ("t_invalid_order", "Invalid order"),
        ("t_notify_rejection", "Notify rejection"),
        ("t_valid_order", "Valid order"),
        ("t_reserve_fulfillment", "Reserve fulfillment"),
        ("t_fulfill_split", "Fulfillment split"),
        ("t_emit_invoice", "Emit invoice"),
        ("t_receive_payment", "Receive payment"),
        ("t_create_label", "Create label"),
        ("t_pack_order", "Pack order"),
        ("t_ship_product", "Ship product"),
        ("t_fulfillment_join", "Fulfillment join"),
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
        ("t_notify_rejection", "p_rejected"),
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
    for process_id, process_name, model_factory, artifact_factory, file_name in [
        (
            "Epurchase_AsIs",
            "E-Purchase As-Is Process",
            as_is_model,
            as_is_artifacts,
            "assignment1_epurchase_as_is.bpmn",
        ),
        (
            "Epurchase_ToBe",
            "E-Purchase To-Be Process",
            to_be_model,
            to_be_artifacts,
            "assignment1_epurchase_to_be.bpmn",
        ),
    ]:
        nodes, flows = model_factory()
        artifacts, associations = artifact_factory()
        xml = build_bpmn(
            process_id,
            process_name,
            nodes,
            flows,
            artifacts,
            associations,
            pool_name="Amazon/Souq e-purchase operations pool",
        )
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
