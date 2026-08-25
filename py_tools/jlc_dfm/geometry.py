"""Small geometry helpers used by the local manufacturing checks."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Tuple

# Reuse the router's authoritative KiCad pad/drill geometry.  In particular,
# Pad.size_x/size_y are already resolved into board space and only
# Pad.rect_rotation remains; applying Pad.rotation again is incorrect.
_ENGINE = Path(__file__).resolve().parents[2] / "py_router"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from check_drc import pad_to_pad_distance as _pad_to_pad_distance  # noqa: E402
from check_drc import point_to_pad_distance  # noqa: E402
from kicad_parser import pad_drill_circles  # noqa: E402

Point = Tuple[float, float]


def point_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_to_segment_distance(p: Point, a: Point, b: Point) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    vv = vx * vx + vy * vy
    if vv <= 1e-24:
        return point_distance(p, a)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    q = (a[0] + t * vx, a[1] + t * vy)
    return point_distance(p, q)


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    eps = 1e-12
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
        and abs(_orientation(a, b, p)) <= eps
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if ((o1 > 0 > o2) or (o1 < 0 < o2)) and ((o3 > 0 > o4) or (o3 < 0 < o4)):
        return True
    return any((
        abs(o1) <= 1e-12 and _on_segment(a, b, c),
        abs(o2) <= 1e-12 and _on_segment(a, b, d),
        abs(o3) <= 1e-12 and _on_segment(c, d, a),
        abs(o4) <= 1e-12 and _on_segment(c, d, b),
    ))


def segment_to_segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_to_segment_distance(a, c, d),
        point_to_segment_distance(b, c, d),
        point_to_segment_distance(c, a, b),
        point_to_segment_distance(d, a, b),
    )


def point_inside_pad(x: float, y: float, pad) -> bool:
    """True when a board-space point is inside authoritative pad copper."""
    return point_to_pad_distance(x, y, pad) <= 1e-9


def pad_edge_distance(a, b) -> float:
    """Minimum copper-edge distance using KiCad parser semantics."""
    distance, _ = _pad_to_pad_distance(a, b)
    return distance


def drill_to_pad_edge_distance(drilled_pad, smd_pad) -> float:
    """Minimum edge distance from a round/slot component drill to pad copper.

    Negative values mean the physical drill area intersects the SMD pad.  Slot
    drills are sampled as the same capsule-circle union used by the router.
    """
    circles = pad_drill_circles(drilled_pad)
    if not circles:
        return float("inf")
    return min(point_to_pad_distance(x, y, smd_pad) - diameter / 2.0
               for x, y, diameter in circles)
