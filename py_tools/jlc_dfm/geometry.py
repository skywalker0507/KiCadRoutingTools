"""Small geometry helpers used by the local manufacturing checks."""
from __future__ import annotations

import math
from typing import Tuple

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


def rotate_into_pad_frame(x: float, y: float, cx: float, cy: float, angle_deg: float) -> Point:
    """Return point coordinates relative to a pad's local axes.

    We only need a self-consistent geometric frame here; using -angle rotates a
    board point back into the pad frame for the parser's absolute pad angle.
    """
    rad = math.radians(-angle_deg)
    dx, dy = x - cx, y - cy
    return (dx * math.cos(rad) - dy * math.sin(rad), dx * math.sin(rad) + dy * math.cos(rad))


def point_inside_pad(x: float, y: float, pad) -> bool:
    """Conservative containment test for ordinary KiCad pad shapes."""
    px, py = rotate_into_pad_frame(x, y, pad.global_x, pad.global_y, getattr(pad, "rotation", 0.0) or 0.0)
    sx, sy = float(pad.size_x), float(pad.size_y)
    shape = (getattr(pad, "shape", "") or "").lower()
    eps = 1e-9
    if shape in ("circle",):
        return px * px + py * py <= (min(sx, sy) / 2.0 + eps) ** 2
    if shape in ("oval",):
        # Capsule along the major axis.
        if sx >= sy:
            half_line = max(0.0, (sx - sy) / 2.0)
            nearest_x = max(-half_line, min(half_line, px))
            return math.hypot(px - nearest_x, py) <= sy / 2.0 + eps
        half_line = max(0.0, (sy - sx) / 2.0)
        nearest_y = max(-half_line, min(half_line, py))
        return math.hypot(px, py - nearest_y) <= sx / 2.0 + eps
    # rect, roundrect, trapezoid, custom fallback: bounding rectangle. Custom
    # pads remain conservative and are explicitly reported as a limitation.
    return abs(px) <= sx / 2.0 + eps and abs(py) <= sy / 2.0 + eps


def pad_edge_distance(a, b) -> float:
    """Capsule-style pad edge distance used by the public JLC helper.

    Radius is the short axis / 2 and the centerline extends along the long axis.
    This intentionally avoids treating a suspicious/overlong pad bounding box as
    fully solid copper while remaining deterministic for rotated oval/rect pads.
    """
    def capsule(pad):
        sx, sy = float(pad.size_x), float(pad.size_y)
        radius = min(sx, sy) / 2.0
        half_len = max(0.0, (max(sx, sy) - min(sx, sy)) / 2.0)
        angle = math.radians(getattr(pad, "rotation", 0.0) or 0.0)
        if sx >= sy:
            ux, uy = math.cos(angle), math.sin(angle)
        else:
            ux, uy = -math.sin(angle), math.cos(angle)
        cx, cy = float(pad.global_x), float(pad.global_y)
        return ((cx - ux * half_len, cy - uy * half_len),
                (cx + ux * half_len, cy + uy * half_len), radius)

    a1, a2, ar = capsule(a)
    b1, b2, br = capsule(b)
    return segment_to_segment_distance(a1, a2, b1, b2) - ar - br
