"""Vector stamps: small one-page PDFs (text, image or drawing) placed onto pages
as Form XObjects with an exact position, size, rotation and opacity.

Latin text is typeset locally with ReportLab's built-in fonts.  Any other script
(Devanagari, Arabic, CJK, Tamil…) is typeset by the browser engine of the
conversion service, which shapes complex scripts correctly.
"""
from __future__ import annotations

import html
import io
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from ..util import ToolError, hex_to_rgb
from . import geometry as g


@dataclass
class Stamp:
    pdf: pikepdf.Pdf
    index: int = 0

    @property
    def page(self) -> pikepdf.Page:
        return self.pdf.pages[self.index]

    @property
    def box(self) -> tuple[float, float, float, float]:
        mb = [float(v) for v in self.page.mediabox]
        return min(mb[0], mb[2]), min(mb[1], mb[3]), max(mb[0], mb[2]), max(mb[1], mb[3])

    @property
    def width(self) -> float:
        b = self.box
        return b[2] - b[0]

    @property
    def height(self) -> float:
        b = self.box
        return b[3] - b[1]


def _latin(text: str) -> bool:
    try:
        text.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _rl_canvas(w: float, h: float):
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h), pageCompression=1)
    c.setTitle("")
    return c, buf


def _finish(c, buf) -> pikepdf.Pdf:
    c.showPage()
    c.save()
    return pikepdf.open(io.BytesIO(buf.getvalue()))


def text_stamps(labels: list[str], font_size: float, color: str = "#000000", opacity: float = 1.0,
                bold: bool = False) -> list[Stamp]:
    """One tightly-cropped stamp per label (same order)."""
    if not labels:
        return []
    if all(_latin(t) for t in labels):
        return [_latin_stamp(t, font_size, color, opacity, bold) for t in labels]
    from ..convert import browser_text_pdf

    pdf = browser_text_pdf(labels, font_size, color, opacity, bold)
    return [Stamp(pdf, i) for i in range(len(pdf.pages))]


def _latin_stamp(text: str, font_size: float, color: str, opacity: float, bold: bool) -> Stamp:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    font = "Helvetica-Bold" if bold else "Helvetica"
    w = max(stringWidth(text, font, font_size), 1.0)
    pad = font_size * 0.12
    h = font_size * 1.18
    c, buf = _rl_canvas(w + 2 * pad, h + 2 * pad)
    r, gr, b = hex_to_rgb(color)
    c.setFillColorRGB(r, gr, b)
    if opacity < 1:
        c.setFillAlpha(opacity)
    c.setFont(font, font_size)
    c.drawString(pad, pad + font_size * 0.22, text)
    return Stamp(_finish(c, buf))


def image_stamp(image: Path | bytes, opacity: float = 1.0, trim: bool = False, max_px: int = 2400) -> Stamp:
    """A stamp holding an image (transparency preserved)."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader

    try:
        im = Image.open(io.BytesIO(image) if isinstance(image, bytes) else image)
        im.load()
    except Exception as exc:
        raise ToolError("The image could not be read. Use a PNG, JPG or WebP file.") from exc
    im = im.convert("RGBA")
    if trim:
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
    if max(im.size) > max_px:
        im.thumbnail((max_px, max_px))
    if opacity < 1:
        alpha = im.getchannel("A").point(lambda a: int(a * max(0.0, min(opacity, 1.0))))
        im.putalpha(alpha)
    w, h = im.size
    c, buf = _rl_canvas(w, h)
    c.drawImage(ImageReader(im), 0, 0, w, h, mask="auto")
    return Stamp(_finish(c, buf))


def rect_overlay(width: float, height: float, rects: list[tuple[float, float, float, float, tuple, float]],
                 labels: list[tuple[float, float, str, tuple, float]] | None = None) -> Stamp:
    """Full-size overlay with filled rectangles ``(x, y_top, w, h, rgb, alpha)`` in view units (y down)
    and optional labels ``(x, y_baseline, text, rgb, size)``."""
    c, buf = _rl_canvas(width, height)
    for x, y, w, h, rgb, alpha in rects:
        c.setFillColorRGB(*rgb)
        c.setFillAlpha(alpha)
        c.rect(x, height - y - h, w, h, stroke=0, fill=1)
    c.setFillAlpha(1)
    for x, y, text, rgb, size in labels or []:
        c.setFillColorRGB(*rgb)
        c.setFont("Helvetica-Bold", size)
        c.drawString(x, height - y, text)
    return Stamp(_finish(c, buf))


class Stamper:
    """Places stamps on the pages of a target PDF."""

    def __init__(self, pdf: pikepdf.Pdf):
        self.pdf = pdf
        self._forms: dict[tuple[int, int], pikepdf.Object] = {}
        self._wrapped: set[int] = set()

    def _form(self, stamp: Stamp) -> pikepdf.Object:
        key = (id(stamp.pdf), stamp.index)
        if key not in self._forms:
            self._forms[key] = self.pdf.copy_foreign(stamp.page.as_form_xobject())
        return self._forms[key]

    def _isolate(self, page: pikepdf.Page) -> None:
        """Wrap the existing content in q/Q so its graphics state can't leak into our stamps."""
        key = page.obj.objgen
        if key in self._wrapped:
            return
        page.contents_add(pikepdf.Stream(self.pdf, b"q\n"), prepend=True)
        page.contents_add(pikepdf.Stream(self.pdf, b"\nQ\n"), prepend=False)
        self._wrapped.add(key)

    def place(self, page: pikepdf.Page, stamp: Stamp, center: tuple[float, float], width: float,
              angle: float = 0.0, under: bool = False) -> None:
        geo = g.PageGeometry.of(page)
        m = g.placement_matrix(geo, stamp.box, center, width, angle)
        form = self._form(stamp)
        name = page.add_resource(form, pikepdf.Name.XObject, prefix="Pv")
        ops = f"q {g.fmt(m)} cm {name} Do Q\n".encode()
        if under:
            page.contents_add(pikepdf.Stream(self.pdf, ops), prepend=True)
        else:
            self._isolate(page)
            page.contents_add(pikepdf.Stream(self.pdf, ops), prepend=False)

    def place_box(self, page: pikepdf.Page, stamp: Stamp, view_box: tuple[float, float, float, float],
                  angle: float = 0.0) -> None:
        """Place a stamp so its (rotated) bounding box fills ``view_box`` (u0, v0, u1, v1)."""
        u0, v0, u1, v1 = view_box
        bw, _ = g.rotated_size(stamp.width, stamp.height, angle)
        scale_w = (u1 - u0) / max(bw, 1e-6)
        self.place(page, stamp, ((u0 + u1) / 2, (v0 + v1) / 2), stamp.width * scale_w, angle)


def anchor(view_w: float, view_h: float, position: str, w: float, h: float, margin: float) -> tuple[float, float]:
    """Top-left corner of a ``w``×``h`` box at a named position inside the visible page."""
    if position == "center":
        v, hz = "middle", "center"
    else:
        v, _, hz = position.partition("-")
    x = {"left": margin, "center": (view_w - w) / 2, "right": view_w - w - margin}.get(hz, (view_w - w) / 2)
    y = {"top": margin, "middle": (view_h - h) / 2, "bottom": view_h - h - margin}.get(v, (view_h - h) / 2)
    return x, y


def css_color(color: str, opacity: float) -> str:
    r, gr, b = hex_to_rgb(color)
    return f"rgba({int(r * 255)},{int(gr * 255)},{int(b * 255)},{max(0.0, min(opacity, 1.0)):.3f})"


def label_html(labels: list[str], font_size: float, color: str, opacity: float, bold: bool) -> str:
    font_size = font_size / 0.75  # CSS px -> PDF points (the browser prints 96 px per 72 pt)
    pages = "".join(f"<div class='p'><span>{html.escape(t)}</span></div>" for t in labels)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"@page{{size:{max(400, int(font_size * 40))}px {int(font_size * 3)}px;margin:0}}"
        "html,body{margin:0;padding:0}"
        f".p{{height:{int(font_size * 3)}px;page-break-after:always;overflow:hidden}}"
        f"span{{display:inline-block;padding:{int(font_size * 0.3)}px;white-space:nowrap;"
        f"font-family:'Noto Sans','DejaVu Sans',sans-serif;font-size:{font_size}px;"
        f"font-weight:{'700' if bold else '400'};color:{css_color(color, opacity)}}}"
        f"</style></head><body>{pages}</body></html>"
    )
