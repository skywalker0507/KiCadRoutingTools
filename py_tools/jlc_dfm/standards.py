"""JLCPCB-oriented process profiles.

Values are adapted from the public EasyEDA/JLC order DFM checker and kept in a
small, explicit profile object so projects can override them instead of baking
factory rules throughout the checker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class JlcFr4Profile:
    name: str = "jlc-fr4-standard"
    layer_count: int = 4
    outer_copper_oz: float = 1.0

    min_board_width: float = 3.0
    min_board_height: float = 3.0
    max_board_width: float = 663.0
    max_board_height: float = 593.0

    min_trace_width: float = 0.09
    min_trace_spacing: float = 0.09
    min_pad_to_track_spacing: float = 0.10
    min_bga_pad_to_track_spacing: float = 0.09

    min_via_drill: float = 0.15
    max_via_drill: float = 6.30
    min_via_outer_diameter: float = 0.25

    # Shared JLC plugin/PTH annular-ring guidance. Kept as a warning because
    # the online DFM may apply package/process-specific grading.
    min_pth_annular_ring: float = 0.15

    min_plated_slot_width: float = 0.35
    min_plated_slot_length: float = 0.70
    min_nonplated_slot_width: float = 1.00

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def _trace_limits(copper_oz: float, layer_count: int) -> Tuple[float, float]:
    tiers = (
        (1.0, 0.10, 0.10, 0.09, 0.09),
        (2.0, 0.16, 0.16, 0.15, 0.15),
        (2.5, 0.20, 0.20, None, None),
        (3.5, 0.25, 0.25, None, None),
        (4.5, 0.30, 0.30, None, None),
        (5.0, 0.35, 0.35, None, None),
        (6.0, 0.45, 0.45, None, None),
    )
    tier = next((t for t in tiers if t[0] >= copper_oz), tiers[-1])
    _, width, spacing, multi_width, multi_spacing = tier
    if layer_count >= 3 and multi_width is not None:
        return multi_width, multi_spacing
    return width, spacing


def _max_board_size(layer_count: int) -> Tuple[float, float]:
    # Public JLC checker resolves by the highest applicable minLayers tier.
    if layer_count >= 6:
        return 656.0, 586.0
    if layer_count >= 4:
        return 663.0, 593.0
    if layer_count >= 2:
        return 670.0, 600.0
    return 606.0, 510.0


def make_jlc_fr4_profile(layer_count: int = 4, outer_copper_oz: float = 1.0) -> JlcFr4Profile:
    width, spacing = _trace_limits(outer_copper_oz, layer_count)
    max_w, max_h = _max_board_size(layer_count)
    if layer_count >= 3:
        via_drill, via_outer = 0.15, 0.25
        slot_w, slot_l = 0.35, 0.70
    elif layer_count >= 2:
        via_drill, via_outer = 0.15, 0.25
        slot_w, slot_l = 0.50, 1.00
    else:
        via_drill, via_outer = 0.30, 0.50
        # Plated slots are not a meaningful single-layer default; retain the
        # conservative two-layer floor rather than pretending to validate it.
        slot_w, slot_l = 0.50, 1.00
    return JlcFr4Profile(
        layer_count=layer_count,
        outer_copper_oz=outer_copper_oz,
        max_board_width=max_w,
        max_board_height=max_h,
        min_trace_width=width,
        min_trace_spacing=spacing,
        min_via_drill=via_drill,
        min_via_outer_diameter=via_outer,
        min_plated_slot_width=slot_w,
        min_plated_slot_length=slot_l,
    )
