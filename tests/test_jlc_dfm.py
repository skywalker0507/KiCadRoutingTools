from dataclasses import dataclass, field
import json
from pathlib import Path

import pytest

from py_tools.jlc_dfm.checker import check_bom_cpl, check_pcb
from py_tools.jlc_dfm.cli import _load_profile
from py_tools.jlc_dfm.geometry import point_to_segment_distance, segment_to_segment_distance
from py_tools.jlc_dfm.standards import make_jlc_fr4_profile


@dataclass
class BoardInfo:
    copper_layers: list = field(default_factory=lambda: ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"])
    board_bounds: tuple = (0.0, 0.0, 40.0, 30.0)


@dataclass
class Segment:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str
    net_id: int
    uuid: str = ""
    graphic: bool = False


@dataclass
class Via:
    x: float
    y: float
    size: float
    drill: float
    layers: list = field(default_factory=lambda: ["F.Cu", "B.Cu"])
    net_id: int = 1
    uuid: str = ""
    tenting_attrs: dict = field(default_factory=dict)


@dataclass
class Pad:
    component_ref: str
    pad_number: str
    global_x: float
    global_y: float
    size_x: float
    size_y: float
    shape: str = "rect"
    layers: list = field(default_factory=lambda: ["F.Cu", "F.Paste", "F.Mask"])
    net_id: int = 1
    rotation: float = 0.0
    rect_rotation: float = 0.0
    roundrect_rratio: float = 0.0
    polygons: object = None
    pad_type: str = "smd"
    drill: float = 0.0
    drill_w: float = 0.0
    drill_h: float = 0.0
    hole_x: object = None
    hole_y: object = None


@dataclass
class Footprint:
    pads: list


@dataclass
class PCB:
    board_info: BoardInfo = field(default_factory=BoardInfo)
    segments: list = field(default_factory=list)
    vias: list = field(default_factory=list)
    pads_by_net: dict = field(default_factory=dict)
    footprints: dict = field(default_factory=dict)
    source_path: str = "fixture.kicad_pcb"

    def net_tie_exempt_pad_ids(self, net_id):
        return set()


def rules(report):
    return [f.rule for f in report.findings]


def test_fr4_four_layer_profile_matches_public_jlc_tier():
    p = make_jlc_fr4_profile(4, 1.0)
    assert p.min_trace_width == pytest.approx(0.09)
    assert p.min_trace_spacing == pytest.approx(0.09)
    assert p.min_via_drill == pytest.approx(0.15)
    assert p.min_plated_slot_width == pytest.approx(0.35)


def test_geometry_segment_distances():
    assert point_to_segment_distance((1, 1), (0, 0), (2, 0)) == pytest.approx(1.0)
    assert segment_to_segment_distance((0, 0), (2, 0), (1, -1), (1, 1)) == 0.0
    assert segment_to_segment_distance((0, 0), (2, 0), (0, 1), (2, 1)) == pytest.approx(1.0)


def test_trace_width_and_spacing_failures_are_structured():
    pcb = PCB(segments=[
        Segment(0, 1, 10, 1, 0.08, "F.Cu", 1, "a"),
        Segment(0, 1.20, 10, 1.20, 0.10, "F.Cu", 2, "b"),
    ])
    report = check_pcb(pcb)
    assert "trace_width" in rules(report)
    # center distance .20 - .04 - .05 = .11, so no spacing failure
    assert "trace_spacing" not in rules(report)
    pcb.segments[1].start_y = pcb.segments[1].end_y = 1.15
    report = check_pcb(pcb)
    assert "trace_spacing" in rules(report)
    assert not report.passed


def test_via_limits_and_via_in_pad_warning():
    pad = Pad("U1", "1", 5.0, 5.0, 1.0, 1.0, net_id=1)
    via = Via(5.0, 5.0, size=0.24, drill=0.14, net_id=1)
    pcb = PCB(vias=[via], pads_by_net={1: [pad]}, footprints={"U1": Footprint([pad])})
    report = check_pcb(pcb)
    assert "via_drill" in rules(report)
    assert "via_outer_diameter" in rules(report)
    assert "via_in_pad_process" in rules(report)


def test_filled_capped_via_in_pad_is_not_warned():
    pad = Pad("U1", "1", 5.0, 5.0, 1.0, 1.0, net_id=1)
    via = Via(5.0, 5.0, size=0.45, drill=0.20, net_id=1,
              tenting_attrs={"filling": "yes", "capping": "yes"})
    pcb = PCB(vias=[via], pads_by_net={1: [pad]}, footprints={"U1": Footprint([pad])})
    report = check_pcb(pcb)
    assert "via_in_pad_process" not in rules(report)


def test_slot_and_pth_annular_checks():
    pth = Pad("J1", "S1", 5, 5, 0.70, 1.20, pad_type="thru_hole",
              drill=0.60, drill_w=0.60, drill_h=0.30, layers=["*.Cu", "*.Mask"])
    pcb = PCB(pads_by_net={0: [pth]}, footprints={"J1": Footprint([pth])})
    report = check_pcb(pcb)
    # 0.30 x 0.60 plated slot is below the 4-layer 0.35 x 0.70 profile.
    assert "plated_slot_size" in rules(report)
    assert "pth_annular_ring" in rules(report)


def test_same_net_close_pads_require_review():
    a = Pad("R1", "1", 1.0, 1.0, 0.5, 0.5, net_id=7)
    b = Pad("U1", "2", 1.55, 1.0, 0.5, 0.5, net_id=7)
    pcb = PCB(pads_by_net={7: [a, b]}, footprints={"R1": Footprint([a]), "U1": Footprint([b])})
    report = check_pcb(pcb)
    hits = [x for x in report.findings if x.rule == "pad_spacing_same_net"]
    assert len(hits) == 1
    assert hits[0].severity == "warning"
    assert not report.passed
    assert report.status == "review_required"


def test_bom_cpl_consistency_and_blank_row(tmp_path: Path):
    bom = tmp_path / "bom.csv"
    cpl = tmp_path / "cpl.csv"
    bom.write_text("Designator,Comment,Footprint\nR1,1K,R0402\nR2,2K,R0402\n,header artifact,R0402\n", encoding="utf-8")
    cpl.write_text("Designator,Mid X,Mid Y,Layer,Rotation\nR1,1,1,Top,0\nR3,2,2,Top,0\n", encoding="utf-8")
    report = check_bom_cpl(str(bom), str(cpl))
    rr = rules(report)
    assert "bom_missing_cpl" in rr
    assert "cpl_missing_bom" in rr
    assert "bom_blank_designator" in rr
    assert not report.passed


def test_different_net_pad_spacing_is_left_to_kicad_drc():
    a = Pad("U1", "1", 1.0, 1.0, 0.5, 0.5, net_id=1)
    b = Pad("U1", "2", 1.54, 1.0, 0.5, 0.5, net_id=2)
    pcb = PCB(pads_by_net={1: [a], 2: [b]}, footprints={"U1": Footprint([a, b])})
    report = check_pcb(pcb)
    assert "pad_spacing" not in rules(report)
    assert "pad_spacing_same_net" not in rules(report)


def test_component_drill_inside_smd_pad_warns_about_cam_semantics():
    thermal = Pad("U1", "EP", 5.0, 5.0, 3.0, 3.0, net_id=1)
    drill_pad = Pad("U1", "EP", 5.0, 5.0, 0.45, 0.45, shape="circle",
                    layers=["*.Cu", "*.Mask"], net_id=1, pad_type="thru_hole", drill=0.20)
    pcb = PCB(pads_by_net={1: [thermal, drill_pad]}, footprints={"U1": Footprint([thermal, drill_pad])})
    report = check_pcb(pcb)
    assert "component_drill_in_smd_pad" in rules(report)


def test_rotated_kicad_pad_uses_rect_rotation_not_absolute_rotation_again():
    # Parser-resolved dimensions are already in board space: these long pads
    # run along X and are separated along Y. Reapplying rotation=90 made them
    # falsely overlap in the first EasyEDA adapter.
    a = Pad("U4", "1", 10.0, 10.0, 1.73, 0.34, shape="oval",
            net_id=1, rotation=90.0, rect_rotation=0.0)
    b = Pad("U4", "3", 10.0, 11.3, 1.73, 0.34, shape="oval",
            net_id=1, rotation=90.0, rect_rotation=0.0)
    pcb = PCB(pads_by_net={1: [a, b]}, footprints={"U4": Footprint([a, b])})
    assert "pad_spacing_same_net" not in rules(check_pcb(pcb))


def test_composite_same_number_pad_is_not_a_spacing_family():
    land = Pad("U1", "41", 5.0, 5.0, 3.9, 3.9, net_id=1,
               layers=["F.Cu", "F.Mask"])
    thermal = Pad("U1", "41", 5.7, 5.0, 0.6, 0.6, shape="circle",
                  layers=["*.Cu", "F.Mask"], net_id=1,
                  pad_type="thru_hole", drill=0.2)
    pcb = PCB(pads_by_net={1: [land, thermal]}, footprints={"U1": Footprint([land, thermal])})
    report = check_pcb(pcb)
    assert "component_drill_in_smd_pad" in rules(report)
    assert "pad_spacing_same_net" not in rules(report)


def test_identical_stacked_same_net_contacts_are_info_not_review():
    a = Pad("J1", "A1", 5.0, 5.0, 0.6, 1.15, shape="roundrect", net_id=1)
    b = Pad("J1", "B12", 5.0, 5.0, 0.6, 1.15, shape="roundrect", net_id=1)
    pcb = PCB(pads_by_net={1: [a, b]}, footprints={"J1": Footprint([a, b])})
    report = check_pcb(pcb)
    assert rules(report) == ["stacked_same_net_pads"]
    assert report.status == "pass"


def test_via_drill_edge_intersection_is_detected_when_center_is_outside_pad():
    pad = Pad("C1", "1", 5.0, 5.0, 1.0, 1.0, net_id=1)
    via = Via(5.58, 5.0, size=0.45, drill=0.20, net_id=1)
    pcb = PCB(vias=[via], pads_by_net={1: [pad]}, footprints={"C1": Footprint([pad])})
    report = check_pcb(pcb)
    assert "via_in_pad_process" in rules(report)


def test_component_slot_edge_intersection_is_detected_across_pad_numbers():
    smd = Pad("J1", "A1", 0.55, 0.0, 1.0, 1.0, net_id=1)
    slot = Pad("J1", "SH", 0.0, 0.0, 0.6, 1.7, shape="oval",
               layers=["*.Cu", "*.Mask"], net_id=2,
               pad_type="thru_hole", drill=1.7, drill_w=0.2, drill_h=1.7)
    pcb = PCB(pads_by_net={1: [smd], 2: [slot]}, footprints={"J1": Footprint([smd, slot])})
    report = check_pcb(pcb)
    assert "component_drill_intersects_smd_pad" in rules(report)


def test_report_binds_bom_cpl_hashes_and_has_stable_fingerprint(tmp_path: Path):
    bom = tmp_path / "bom.csv"
    cpl = tmp_path / "cpl.csv"
    bom.write_text("Designator\nR1\n", encoding="utf-8")
    cpl.write_text("Designator\nR1\n", encoding="utf-8")
    first = check_bom_cpl(str(bom), str(cpl)).to_dict()
    mirror = tmp_path / "other-machine-path"
    mirror.mkdir()
    bom2, cpl2 = mirror / "bom.csv", mirror / "cpl.csv"
    bom2.write_bytes(bom.read_bytes())
    cpl2.write_bytes(cpl.read_bytes())
    second = check_bom_cpl(str(bom2), str(cpl2)).to_dict()
    assert first["inputs"]["bom"]["sha256"]
    assert first["inputs"]["cpl"]["sha256"]
    assert first["metrics"] == {"bom_designators": 1, "cpl_designators": 1}
    assert first["evidence_fingerprint_sha256"] == second["evidence_fingerprint_sha256"]


def test_external_profile_fails_closed_on_unknown_field_or_layer_mismatch(tmp_path: Path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"layer_count": 4, "min_trace_width": 0.11}), encoding="utf-8")
    assert _load_profile(path, 4).min_trace_width == pytest.approx(0.11)
    with pytest.raises(ValueError, match="does not match"):
        _load_profile(path, 2)
    path.write_text(json.dumps({"layer_count": 4, "invented_rule": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown profile"):
        _load_profile(path, 4)
