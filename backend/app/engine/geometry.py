"""Page geometry.

*User space* is the PDF content coordinate system: origin bottom-left, y up,
before the page's ``/Rotate`` is applied.  *View space* is what a reader sees
on screen: origin at the top-left of the visible (crop) box, y down, after
rotation.  Every tool works in view space and converts at the last moment, so
rotated pages and offset crop boxes behave correctly everywhere.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pikepdf

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(m1: Matrix, m2: Matrix) -> Matrix:
    """Concatenate: apply ``m1`` first, then ``m2`` (PDF ``cm`` semantics)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def translate(tx: float, ty: float) -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def scale(sx: float, sy: float | None = None) -> Matrix:
    return (sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)


def rotate(degrees: float) -> Matrix:
    """Counter-clockwise rotation in a y-up system."""
    r = math.radians(degrees)
    c, s = math.cos(r), math.sin(r)
    return (c, s, -s, c, 0.0, 0.0)


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def fmt(m: Matrix) -> str:
    return " ".join(f"{v:.6f}".rstrip("0").rstrip(".") if v else "0" for v in m)


def _box(page: pikepdf.Page | pikepdf.Dictionary, name: str) -> tuple[float, float, float, float] | None:
    obj = page.obj if isinstance(page, pikepdf.Page) else page
    node = obj
    while node is not None:  # boxes are inheritable
        if name in node:
            x0, y0, x1, y1 = (float(v) for v in node[name])
            return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
        node = node.get("/Parent")
    return None


def _rotation(page: pikepdf.Page) -> int:
    node = page.obj
    while node is not None:
        if "/Rotate" in node:
            return int(node["/Rotate"]) % 360
        node = node.get("/Parent")
    return 0


@dataclass(frozen=True)
class PageGeometry:
    x0: float
    y0: float
    x1: float
    y1: float
    rotation: int  # 0, 90, 180 or 270

    @classmethod
    def of(cls, page: pikepdf.Page) -> PageGeometry:
        media = _box(page, "/MediaBox") or (0.0, 0.0, 612.0, 792.0)
        crop = _box(page, "/CropBox") or media
        # the visible area is the crop box clipped to the media box
        x0, y0 = max(crop[0], media[0]), max(crop[1], media[1])
        x1, y1 = min(crop[2], media[2]), min(crop[3], media[3])
        if x1 - x0 < 1 or y1 - y0 < 1:
            x0, y0, x1, y1 = media
        rot = _rotation(page)
        return cls(x0, y0, x1, y1, rot - rot % 90)

    @property
    def width(self) -> float:  # visible width
        return (self.x1 - self.x0) if self.rotation in (0, 180) else (self.y1 - self.y0)

    @property
    def height(self) -> float:  # visible height
        return (self.y1 - self.y0) if self.rotation in (0, 180) else (self.x1 - self.x0)

    def view_up_to_user(self) -> Matrix:
        """Matrix from "view space with y up" (origin bottom-left of the visible page) to user space."""
        H = self.height
        if self.rotation == 90:
            return (0.0, 1.0, -1.0, 0.0, self.x0 + H, self.y0)
        if self.rotation == 180:
            return (-1.0, 0.0, 0.0, -1.0, self.x1, self.y0 + H)
        if self.rotation == 270:
            return (0.0, -1.0, 1.0, 0.0, self.x1 - H, self.y1)
        return (1.0, 0.0, 0.0, 1.0, self.x0, self.y0)

    def view_to_user(self, u: float, v: float) -> tuple[float, float]:
        """View point (origin top-left, y down) -> user space."""
        return apply(self.view_up_to_user(), u, self.height - v)

    def user_to_view(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.view_up_to_user()
        det = a * d - b * c
        # inverse of a rotation/translation matrix
        x2, y2 = x - e, y - f
        p = (d * x2 - c * y2) / det
        q = (-b * x2 + a * y2) / det
        return p, self.height - q

    def user_rect_to_view(self, r: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        (u0, v0), (u1, v1) = self.user_to_view(r[0], r[1]), self.user_to_view(r[2], r[3])
        return min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1)

    def view_rect_to_user(self, r: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        (x0, y0), (x1, y1) = self.view_to_user(r[0], r[1]), self.view_to_user(r[2], r[3])
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def placement_matrix(geo: PageGeometry, stamp_box: tuple[float, float, float, float], center: tuple[float, float],
                     width: float, angle: float = 0.0) -> Matrix:
    """Matrix that draws a stamp (whose own box is ``stamp_box``) centred at a view-space point,
    scaled to ``width`` view units and rotated ``angle`` degrees counter-clockwise as seen by the reader."""
    sx0, sy0, sx1, sy1 = stamp_box
    sw = max(sx1 - sx0, 1e-6)
    s = width / sw
    cu, cv = center
    m = translate(-(sx0 + sx1) / 2, -(sy0 + sy1) / 2)
    m = mul(m, scale(s))
    m = mul(m, rotate(angle))
    m = mul(m, translate(cu, geo.height - cv))
    return mul(m, geo.view_up_to_user())


def rotated_size(w: float, h: float, angle: float) -> tuple[float, float]:
    r = math.radians(angle)
    c, s = abs(math.cos(r)), abs(math.sin(r))
    return w * c + h * s, w * s + h * c
