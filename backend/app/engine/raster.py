"""Rendering, text and image extraction (PDFium)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from ..util import ToolError


@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]  # user space (x0, y0, x1, y1)
    page: int


def open_doc(path: Path | bytes, password: str | None = None) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(path, password=password)
    except pdfium.PdfiumError as exc:
        msg = str(exc).lower()
        if "password" in msg:
            raise ToolError("This PDF is password protected. Unlock it first.") from exc
        raise ToolError("This file is not a valid PDF or is damaged. Try the Repair tool first.") from exc


MAX_RENDER_PIXELS = 60_000_000  # e.g. A4 at 600 dpi is ~35 MP; giant pages are scaled down instead of exhausting memory


def render(page: pdfium.PdfPage, dpi: float = 150, grayscale: bool = False):
    """Render a page (crop box, rotation applied) to a PIL image."""
    dpi = max(18.0, min(float(dpi), 600.0))
    w, h = page.get_size()
    scale = dpi / 72.0
    if w * h * scale * scale > MAX_RENDER_PIXELS:
        scale = (MAX_RENDER_PIXELS / max(w * h, 1.0)) ** 0.5
    bitmap = page.render(scale=scale, grayscale=grayscale, may_draw_forms=True)
    img = bitmap.to_pil()
    return img.convert("L" if grayscale else "RGB")


def page_text(page: pdfium.PdfPage) -> str:
    tp = page.get_textpage()
    try:
        return tp.get_text_range()
    finally:
        tp.close()


def char_boxes(page: pdfium.PdfPage) -> tuple[str, list[tuple[float, float, float, float] | None]]:
    """Page text and the user-space box of every character (``None`` for generated characters)."""
    tp = page.get_textpage()
    try:
        n = tp.count_chars()
        text = tp.get_text_range(0, n) if n else ""
        boxes: list[tuple[float, float, float, float] | None] = []
        for i in range(n):
            x0, y0, x1, y1 = tp.get_charbox(i, loose=False)
            boxes.append((x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None)
        # get_text_range may return fewer code units than chars in rare cases; keep both aligned
        if len(text) != len(boxes):
            text = "".join(tp.get_text_range(i, 1)[:1] or " " for i in range(n))
        return text, boxes
    finally:
        tp.close()


def union(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def span_boxes(boxes: list[tuple[float, float, float, float] | None], start: int, end: int) -> list[tuple[float, float, float, float]]:
    """Boxes covering characters [start, end), one per visual line."""
    lines: list[list[tuple[float, float, float, float]]] = []
    for b in boxes[start:end]:
        if b is None:
            continue
        if lines:
            last = lines[-1][-1]
            same_line = abs((b[1] + b[3]) / 2 - (last[1] + last[3]) / 2) < max(b[3] - b[1], last[3] - last[1]) * 0.6
            if same_line:
                lines[-1].append(b)
                continue
        lines.append([b])
    return [union(line) for line in lines]


def words(page: pdfium.PdfPage, index: int) -> list[Word]:
    text, boxes = char_boxes(page)
    out = []
    for m in re.finditer(r"\S+", text):
        bs = [b for b in boxes[m.start():m.end()] if b]
        if bs:
            out.append(Word(m.group(0), union(bs), index))
    return out


def is_scanned(path: Path, sample: int = 5) -> bool:
    doc = open_doc(path)
    try:
        n = min(sample, len(doc))
        chars = 0
        for i in range(n):
            chars += len(page_text(doc[i]).strip())
        return n > 0 and chars < 25 * n
    finally:
        doc.close()


def iter_images(page: pdfium.PdfPage) -> Iterator[pdfium.PdfImage]:
    yield from page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=4)  # type: ignore[misc]


def content_bbox(img, threshold: int = 245) -> tuple[int, int, int, int] | None:
    """Bounding box of non-white content in a rendered page image."""
    from PIL import ImageOps

    gray = ImageOps.invert(img.convert("L")).point(lambda v: 255 if v > 255 - threshold else 0)
    return gray.getbbox()
