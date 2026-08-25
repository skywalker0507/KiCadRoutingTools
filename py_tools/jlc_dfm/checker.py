"""KiCad PCBData -> JLC-oriented local DFM preflight."""
from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .geometry import (
    drill_to_pad_edge_distance,
    pad_edge_distance,
    point_to_pad_distance,
    segment_to_segment_distance,
)
from .model import DfmReport, Finding
from .standards import JlcFr4Profile, make_jlc_fr4_profile


COVERAGE = [
    "board dimensions and copper layer count",
    "minimum routed trace width",
    "different-net same-layer track spacing",
    "through-via drill and outer diameter",
    "PTH annular-ring margin",
    "plated/non-plated slot dimensions represented as pad drills",
    "same-net pad-to-pad copper proximity preflight with composite-pad deduplication",
    "via-drill intersection with paste-bearing SMD pads and fill/cap metadata warning",
    "round/slot component-drill intersection with SMD pads",
    "BOM/CPL designator consistency (when both CSV files are supplied)",
]

LIMITATIONS = [
    "Does not replace KiCad DRC or official JLCPCB/JLCDFM CAM review.",
    "Does not have JLC's proprietary component-body/pin 3D models; online SMT collision, pin-pad overlap and plug-in-hole model checks remain official-gate items.",
    "BOM/CPL consistency compares their designator sets; without a reviewed assembly manifest it cannot prove that both files did not omit the same intended component.",
    "Zones, solder-mask bridges, silkscreen clipping and Gerber/CAM interpretation are not fully modeled in this first local preflight.",
    "Pad spacing reuses KiCadRoutingTools DRC geometry, including rect_rotation and custom polygons; it is still copper proximity, not actual solder-mask aperture analysis.",
    "Footprint drill holes used as thermal-via substitutes remain component drills; the checker warns on this geometry but cannot force CAM to treat them as IPC-4761 filled/capped vias.",
]


def _layer_count(pcb) -> int:
    copper = list(getattr(getattr(pcb, "board_info", None), "copper_layers", None) or [])
    return len(copper) or 2


def _board_size(pcb) -> Optional[Tuple[float, float]]:
    bounds = getattr(getattr(pcb, "board_info", None), "board_bounds", None)
    if not bounds:
        return None
    min_x, min_y, max_x, max_y = bounds
    return abs(max_x - min_x), abs(max_y - min_y)


def _obj_pad(pad) -> str:
    return f"{getattr(pad, 'component_ref', '?')}.{getattr(pad, 'pad_number', '?')}"


def _same_copper_side(a, b) -> bool:
    a_layers = set(getattr(a, "layers", None) or [])
    b_layers = set(getattr(b, "layers", None) or [])
    copper_a = {x for x in a_layers if x.endswith(".Cu") or x == "*.Cu"}
    copper_b = {x for x in b_layers if x.endswith(".Cu") or x == "*.Cu"}
    if "*.Cu" in copper_a or "*.Cu" in copper_b:
        return True
    return bool(copper_a & copper_b)


def _all_pads(pcb) -> List[object]:
    out, seen = [], set()
    for pads in (getattr(pcb, "pads_by_net", None) or {}).values():
        for p in pads:
            if id(p) not in seen:
                seen.add(id(p)); out.append(p)
    # Net-less NPTH/mechanical pads may only live under footprints.
    for fp in (getattr(pcb, "footprints", None) or {}).values():
        for p in getattr(fp, "pads", None) or []:
            if id(p) not in seen:
                seen.add(id(p)); out.append(p)
    return out


def _file_evidence(path: str) -> Dict[str, object]:
    p = Path(path).resolve()
    digest = hashlib.sha256(p.read_bytes()).hexdigest().upper()
    return {"path": str(p), "sha256": digest, "bytes": p.stat().st_size}


def _paste_bearing(pad) -> bool:
    return any(layer in ("F.Paste", "B.Paste", "*.Paste")
               for layer in (getattr(pad, "layers", None) or []))


def _same_logical_pad(a, b) -> bool:
    return (_obj_pad(a) == _obj_pad(b))


def _same_physical_pad(a, b) -> bool:
    """True for duplicate logical contacts drawn on identical copper."""
    attrs = ("global_x", "global_y", "size_x", "size_y", "rect_rotation")
    if any(abs(float(getattr(a, key, 0.0) or 0.0) -
               float(getattr(b, key, 0.0) or 0.0)) > 1e-9 for key in attrs):
        return False
    return ((getattr(a, "shape", "") or "").lower() ==
            (getattr(b, "shape", "") or "").lower() and
            set(getattr(a, "layers", None) or []) == set(getattr(b, "layers", None) or []) and
            float(getattr(a, "roundrect_rratio", 0.0) or 0.0) ==
            float(getattr(b, "roundrect_rratio", 0.0) or 0.0) and
            (getattr(a, "polygons", None) or []) == (getattr(b, "polygons", None) or []))


def check_pcb(pcb, *, source: str = "", profile: Optional[JlcFr4Profile] = None,
              outer_copper_oz: float = 1.0) -> DfmReport:
    layers = _layer_count(pcb)
    profile = profile or make_jlc_fr4_profile(layers, outer_copper_oz)
    report = DfmReport(
        source=source or getattr(pcb, "source_path", "") or "<PCBData>",
        profile=profile.to_dict(),
        coverage=list(COVERAGE),
        limitations=list(LIMITATIONS),
    )
    if source and Path(source).is_file():
        report.inputs["pcb"] = _file_evidence(source)
    f = report.findings

    size = _board_size(pcb)
    if size:
        w, h = sorted(size)
        min_w, min_h = sorted((profile.min_board_width, profile.min_board_height))
        max_w, max_h = sorted((profile.max_board_width, profile.max_board_height))
        if w < min_w or h < min_h:
            f.append(Finding("board_size", "error", f"Board {size[0]:.3f} x {size[1]:.3f} mm is below the selected JLC profile minimum.", measured=min(w, h), required=min_w))
        if w > max_w or h > max_h:
            f.append(Finding("board_size", "error", f"Board {size[0]:.3f} x {size[1]:.3f} mm exceeds the selected JLC profile maximum.", measured=max(w, h), required=max_h))

    # Trace width and same-layer different-net spacing. Pairwise checking is
    # intentionally bounded to route segments; KiCad DRC remains authoritative.
    segments = list(getattr(pcb, "segments", None) or [])
    report.metrics["copper_layers"] = layers
    report.metrics["segments_checked"] = len(segments)
    for seg in segments:
        if getattr(seg, "graphic", False):
            continue
        width = float(getattr(seg, "width", 0.0) or 0.0)
        if width + 1e-12 < profile.min_trace_width:
            f.append(Finding(
                "trace_width", "error",
                f"Track width {width:.4f} mm is below JLC profile minimum {profile.min_trace_width:.4f} mm.",
                measured=width, required=profile.min_trace_width,
                objects=(getattr(seg, "uuid", "") or f"net:{getattr(seg, 'net_id', '?')}",),
                location=(float(seg.start_x), float(seg.start_y)),
                details={"layer": getattr(seg, "layer", "")},
            ))

    # Grid candidate generation avoids a full O(N^2) scan on larger boards.
    cell = max(1.0, profile.min_trace_spacing * 8.0)
    bins: Dict[Tuple[str, int, int], List[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        if getattr(seg, "graphic", False):
            continue
        xmin = min(seg.start_x, seg.end_x) - seg.width / 2 - profile.min_trace_spacing
        xmax = max(seg.start_x, seg.end_x) + seg.width / 2 + profile.min_trace_spacing
        ymin = min(seg.start_y, seg.end_y) - seg.width / 2 - profile.min_trace_spacing
        ymax = max(seg.start_y, seg.end_y) + seg.width / 2 + profile.min_trace_spacing
        for gx in range(math.floor(xmin / cell), math.floor(xmax / cell) + 1):
            for gy in range(math.floor(ymin / cell), math.floor(ymax / cell) + 1):
                bins[(seg.layer, gx, gy)].append(i)
    pairs: Set[Tuple[int, int]] = set()
    for indices in bins.values():
        for pos, i in enumerate(indices):
            for j in indices[pos + 1:]:
                if i != j:
                    pairs.add((min(i, j), max(i, j)))
    for i, j in pairs:
        a, b = segments[i], segments[j]
        if a.layer != b.layer or a.net_id == b.net_id:
            continue
        center = segment_to_segment_distance(
            (a.start_x, a.start_y), (a.end_x, a.end_y),
            (b.start_x, b.start_y), (b.end_x, b.end_y),
        )
        gap = center - a.width / 2.0 - b.width / 2.0
        if gap + 1e-9 < profile.min_trace_spacing:
            f.append(Finding(
                "trace_spacing", "error",
                f"Different-net tracks on {a.layer} have {gap:.4f} mm edge spacing; profile requires {profile.min_trace_spacing:.4f} mm.",
                measured=gap, required=profile.min_trace_spacing,
                objects=(getattr(a, "uuid", "") or f"net:{a.net_id}", getattr(b, "uuid", "") or f"net:{b.net_id}"),
                location=((a.start_x + a.end_x) / 2.0, (a.start_y + a.end_y) / 2.0),
                details={"layer": a.layer, "nets": [a.net_id, b.net_id]},
            ))

    vias = list(getattr(pcb, "vias", None) or [])
    report.metrics["vias_checked"] = len(vias)
    for via in vias:
        drill, size_v = float(via.drill), float(via.size)
        name = getattr(via, "uuid", "") or f"via@{via.x:.3f},{via.y:.3f}"
        if drill + 1e-12 < profile.min_via_drill:
            f.append(Finding("via_drill", "error", f"Via drill {drill:.4f} mm is below profile minimum.", drill, profile.min_via_drill, objects=(name,), location=(via.x, via.y)))
        if drill - 1e-12 > profile.max_via_drill:
            f.append(Finding("via_drill", "error", f"Via drill {drill:.4f} mm exceeds profile maximum.", drill, profile.max_via_drill, objects=(name,), location=(via.x, via.y)))
        if size_v + 1e-12 < profile.min_via_outer_diameter:
            f.append(Finding("via_outer_diameter", "error", f"Via outer diameter {size_v:.4f} mm is below profile minimum.", size_v, profile.min_via_outer_diameter, objects=(name,), location=(via.x, via.y)))

    pads = _all_pads(pcb)
    report.metrics["pads_checked"] = len(pads)
    # PTH rings and slots.
    for pad in pads:
        ptype = (getattr(pad, "pad_type", "") or "").lower()
        drill_w = float(getattr(pad, "drill_w", 0.0) or 0.0)
        drill_h = float(getattr(pad, "drill_h", 0.0) or 0.0)
        drill = float(getattr(pad, "drill", 0.0) or 0.0)
        if drill <= 0 and drill_w <= 0 and drill_h <= 0:
            continue
        obj = _obj_pad(pad)
        hole_w = drill_w or drill
        hole_h = drill_h or drill
        if ptype == "thru_hole":
            # Drill w/h are in the pad frame, so compare corresponding axes.
            ring = min((float(pad.size_x) - hole_w) / 2.0,
                       (float(pad.size_y) - hole_h) / 2.0)
            if ring + 1e-12 < profile.min_pth_annular_ring:
                f.append(Finding(
                    "pth_annular_ring", "warning",
                    f"PTH pad {obj} has about {ring:.4f} mm minimum annular ring; JLC shared guidance is {profile.min_pth_annular_ring:.4f} mm. Confirm package/process-specific official DFM grading.",
                    ring, profile.min_pth_annular_ring, objects=(obj,),
                    location=(pad.global_x if getattr(pad, "hole_x", None) is None else pad.hole_x,
                              pad.global_y if getattr(pad, "hole_y", None) is None else pad.hole_y),
                ))
        is_slot = abs(hole_w - hole_h) > 1e-9 and min(hole_w, hole_h) > 0
        if is_slot:
            slot_w, slot_l = min(hole_w, hole_h), max(hole_w, hole_h)
            if ptype == "np_thru_hole":
                if slot_w + 1e-12 < profile.min_nonplated_slot_width:
                    f.append(Finding("nonplated_slot_width", "error", f"NPTH slot {obj} width {slot_w:.4f} mm is below profile minimum.", slot_w, profile.min_nonplated_slot_width, objects=(obj,), location=(pad.global_x, pad.global_y)))
            else:
                if slot_w + 1e-12 < profile.min_plated_slot_width or slot_l + 1e-12 < profile.min_plated_slot_length:
                    f.append(Finding("plated_slot_size", "error", f"Plated slot {obj} is {slot_w:.4f} x {slot_l:.4f} mm; profile minimum is {profile.min_plated_slot_width:.4f} x {profile.min_plated_slot_length:.4f} mm.", min(slot_w, slot_l), min(profile.min_plated_slot_width, profile.min_plated_slot_length), objects=(obj,), location=(pad.global_x, pad.global_y), details={"slot_width_mm": slot_w, "slot_length_mm": slot_l}))

    # Same-net pad spacing is a solder-mask/bridging preflight independent of
    # electrical DRC. A coarse spatial grid keeps the common case inexpensive.
    pad_cell = max(1.0, profile.min_pad_to_track_spacing * 8.0)
    pbin: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for i, pad in enumerate(pads):
        r = max(float(pad.size_x), float(pad.size_y)) / 2.0 + profile.min_pad_to_track_spacing
        for gx in range(math.floor((pad.global_x-r)/pad_cell), math.floor((pad.global_x+r)/pad_cell)+1):
            for gy in range(math.floor((pad.global_y-r)/pad_cell), math.floor((pad.global_y+r)/pad_cell)+1):
                pbin[(gx, gy)].append(i)
    ppairs: Set[Tuple[int, int]] = set()
    for indices in pbin.values():
        for pos, i in enumerate(indices):
            for j in indices[pos+1:]:
                if i != j:
                    ppairs.add((min(i,j), max(i,j)))
    for i, j in ppairs:
        a, b = pads[i], pads[j]
        if not _same_copper_side(a, b):
            continue
        # Respect KiCad net-tie exemptions already modeled by PCBData.
        try:
            if getattr(a, "net_id", 0) and id(b) in pcb.net_tie_exempt_pad_ids(a.net_id):
                continue
        except (AttributeError, TypeError):
            pass
        # Skip NPTH mechanical-only pads in copper spacing.
        if (getattr(a, "pad_type", "") == "np_thru_hole" or getattr(b, "pad_type", "") == "np_thru_hole"):
            continue
        if _same_logical_pad(a, b):
            # Composite pads (thermal-pad copper plus drill/paste primitives)
            # are one logical land, not a pad-spacing violation family.
            continue
        same_net = getattr(a, "net_id", None) == getattr(b, "net_id", None) and getattr(a, "net_id", None) not in (None, 0)
        if same_net and _same_physical_pad(a, b):
            f.append(Finding(
                "stacked_same_net_pads", "info",
                f"Same-net pads {_obj_pad(a)} and {_obj_pad(b)} intentionally share identical copper geometry.",
                objects=(_obj_pad(a), _obj_pad(b)),
                location=(float(a.global_x), float(a.global_y)),
            ))
            continue
        gap = pad_edge_distance(a, b)
        if gap + 1e-9 >= profile.min_pad_to_track_spacing:
            continue
        # The upstream EasyEDA helper exposes this as an independent SAME-NET
        # solder-mask/bridging preflight. Different-net copper clearance belongs
        # to KiCad DRC and is intentionally not duplicated here.
        if not same_net:
            continue
        f.append(Finding(
            "pad_spacing_same_net", "warning",
            f"Same-net pads {_obj_pad(a)} and {_obj_pad(b)} have approximately {gap:.4f} mm edge spacing; review solder-mask bridge / intentional pad merging.",
            gap, profile.min_pad_to_track_spacing, objects=(_obj_pad(a), _obj_pad(b)),
            location=((a.global_x+b.global_x)/2.0, (a.global_y+b.global_y)/2.0),
        ))

    # Component drills are Excellon ComponentDrill objects, not vias.  Compare
    # their real round/slot capsule against every SMD copper pad on a shared
    # outer side; centre-only containment misses slot-edge intersections.
    drilled_pads = [p for p in pads if (float(getattr(p, "drill", 0.0) or 0.0) > 0
                                         or float(getattr(p, "drill_w", 0.0) or 0.0) > 0
                                         or float(getattr(p, "drill_h", 0.0) or 0.0) > 0)]
    smd_pads = [p for p in pads if (getattr(p, "pad_type", "") or "").lower() == "smd"]
    for drilled in drilled_pads:
        hits = []
        for smd in smd_pads:
            if not _same_copper_side(drilled, smd):
                continue
            gap = drill_to_pad_edge_distance(drilled, smd)
            if gap <= 1e-9:
                hits.append((smd, gap))
        if hits:
            hx = drilled.global_x if getattr(drilled, "hole_x", None) is None else drilled.hole_x
            hy = drilled.global_y if getattr(drilled, "hole_y", None) is None else drilled.hole_y
            logical = [p for p, _ in hits if _same_logical_pad(drilled, p)]
            rule = "component_drill_in_smd_pad" if logical else "component_drill_intersects_smd_pad"
            names = sorted({_obj_pad(p) for p, _ in hits})
            f.append(Finding(
                rule, "warning",
                f"Component drill {_obj_pad(drilled)} intersects SMD pad copper ({', '.join(names)}). Confirm the Excellon/CAM classification and anti-wicking process explicitly.",
                measured=min(gap for _, gap in hits), required=0.0,
                objects=(_obj_pad(drilled), *names), location=(hx, hy),
                details={
                    "drill_pad_type": getattr(drilled, "pad_type", ""),
                    "same_logical_pad": bool(logical),
                    "paste_bearing_hits": sorted({_obj_pad(p) for p, _ in hits if _paste_bearing(p)}),
                },
            ))

    # Via-in-pad detection. This does not mark it as invalid; it creates a
    # manufacturing-process warning unless KiCad preserved both fill and cap metadata.
    paste_smd_pads = [p for p in smd_pads if _paste_bearing(p)]
    report.metrics["paste_bearing_smd_pads_checked"] = len(paste_smd_pads)
    for via in vias:
        hits = []
        for pad in paste_smd_pads:
            if not _same_copper_side(pad, type("ViaLayers", (), {"layers": via.layers})()):
                continue
            drill_gap = point_to_pad_distance(via.x, via.y, pad) - float(via.drill) / 2.0
            if drill_gap <= 1e-9:
                hits.append((pad, drill_gap))
        attrs = getattr(via, "tenting_attrs", None) or {}
        keys = {str(k).lower() for k in attrs}
        filled_capped = "filling" in keys and "capping" in keys
        if hits and not filled_capped:
            name = getattr(via, "uuid", "") or f"via@{via.x:.3f},{via.y:.3f}"
            pads_hit = sorted({_obj_pad(p) for p, _ in hits})
            f.append(Finding(
                "via_in_pad_process", "warning",
                f"Via drill intersects paste-bearing SMD pad area ({', '.join(pads_hit)}). Confirm filled/capped via-in-pad process to avoid solder wicking.",
                measured=min(gap for _, gap in hits), required=0.0,
                objects=(name, *pads_hit), location=(via.x, via.y),
                details={"via_protection_tokens": sorted(keys), "intersection_count": len(hits)},
            ))

    f.sort(key=lambda x: (0 if x.severity == "error" else 1 if x.severity == "warning" else 2, x.rule, x.location or (0,0), x.objects))
    return report


_DESIGNATOR_HEADERS = ("designator", "reference", "ref", "refdes", "refs", "位号")
_DNP_HEADERS = ("dnp", "do not populate", "populate", "不贴", "是否贴装")


def _find_header(fieldnames: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    normalized = {str(x).strip().lower(): x for x in fieldnames if x is not None}
    for c in candidates:
        if c.lower() in normalized:
            return normalized[c.lower()]
    return None


def _split_refs(value: str) -> List[str]:
    value = (value or "").strip()
    if not value:
        return []
    for sep in (";", " ", "\t"):
        value = value.replace(sep, ",")
    return [x.strip() for x in value.split(",") if x.strip()]


def _read_designators(path: str) -> Tuple[Set[str], int, List[str]]:
    refs: Set[str] = set()
    blank_rows = 0
    warnings: List[str] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        ref_col = _find_header(fields, _DESIGNATOR_HEADERS)
        if not ref_col:
            raise ValueError(f"No designator/reference column found in {path}; headers={fields}")
        dnp_col = _find_header(fields, _DNP_HEADERS)
        for row in reader:
            raw = (row.get(ref_col) or "").strip()
            if not raw:
                if any((v or "").strip() for v in row.values() if isinstance(v, str)):
                    blank_rows += 1
                continue
            if dnp_col:
                flag = (row.get(dnp_col) or "").strip().lower()
                if flag in ("dnp", "no", "false", "0", "不贴", "否"):
                    continue
            refs.update(_split_refs(raw))
    return refs, blank_rows, warnings


def check_bom_cpl(bom_path: str, cpl_path: str, report: Optional[DfmReport] = None) -> DfmReport:
    report = report or DfmReport(source=f"{bom_path} + {cpl_path}", profile={"name": "bom-cpl"}, coverage=["BOM/CPL designator consistency"], limitations=[])
    bom_refs, bom_blanks, _ = _read_designators(bom_path)
    cpl_refs, cpl_blanks, _ = _read_designators(cpl_path)
    report.inputs["bom"] = _file_evidence(bom_path)
    report.inputs["cpl"] = _file_evidence(cpl_path)
    report.metrics["bom_designators"] = len(bom_refs)
    report.metrics["cpl_designators"] = len(cpl_refs)
    for ref in sorted(bom_refs - cpl_refs):
        report.findings.append(Finding("bom_missing_cpl", "error", f"BOM designator {ref} is missing from CPL/position file.", objects=(ref,)))
    for ref in sorted(cpl_refs - bom_refs):
        report.findings.append(Finding("cpl_missing_bom", "error", f"CPL designator {ref} is missing from BOM.", objects=(ref,)))
    if bom_blanks:
        report.findings.append(Finding("bom_blank_designator", "warning", f"BOM contains {bom_blanks} non-empty row(s) with no designator; filter them before JLC SMT matching.", measured=float(bom_blanks), unit="rows"))
    if cpl_blanks:
        report.findings.append(Finding("cpl_blank_designator", "warning", f"CPL contains {cpl_blanks} non-empty row(s) with no designator.", measured=float(cpl_blanks), unit="rows"))
    return report
