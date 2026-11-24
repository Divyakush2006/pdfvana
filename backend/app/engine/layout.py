"""Reading-order layout analysis.

Turns each PDF page into a list of semantic blocks (headings, paragraphs,
list items, tables, images) that the Word / Markdown / HTML writers consume.
It handles single and two-column pages, hyphenation, ruled tables, scanned
pages that were OCR'd, and keeps font family, size, weight, slant and colour.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pikepdf

from . import geometry as g
from . import raster

BULLET_RE = re.compile(r"^\s*([•◦▪▫●○■□►▶✓✔·\-–—\*])\s+")
NUMBER_RE = re.compile(r"^\s*(\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|[ivxIVX]{1,4}[.)])\s+")
SUBSET_RE = re.compile(r"^[A-Z]{6}\+")


@dataclass
class Run:
    text: str
    font: str
    size: float
    bold: bool
    italic: bool
    color: str  # RRGGBB


@dataclass
class Line:
    x0: float
    top: float
    x1: float
    bottom: float
    runs: list[Run]

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @property
    def size(self) -> float:
        sizes = Counter()
        for r in self.runs:
            sizes[round(r.size, 1)] += len(r.text)
        return sizes.most_common(1)[0][0] if sizes else 10.0

    @property
    def bold(self) -> bool:
        total = sum(len(r.text.strip()) for r in self.runs) or 1
        return sum(len(r.text.strip()) for r in self.runs if r.bold) / total > 0.7


@dataclass
class Block:
    kind: str  # heading | para | list | table | image
    top: float
    x0: float = 0.0
    x1: float = 0.0
    runs: list[Run] = field(default_factory=list)
    level: int = 0
    align: str = "left"
    list_kind: str = ""
    rows: list[list[str]] = field(default_factory=list)
    image: Path | None = None
    width: float = 0.0
    height: float = 0.0
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs).strip()


@dataclass
class PageModel:
    width: float
    height: float
    blocks: list[Block]
    margin_left: float = 54.0
    margin_right: float = 54.0
    margin_top: float = 54.0


def _hex(color) -> str:
    try:
        if color is None:
            return "000000"
        if isinstance(color, (int, float)):
            v = int(max(0.0, min(float(color), 1.0)) * 255)
            return f"{v:02X}" * 3
        vals = [float(c) for c in color]
        if len(vals) == 1:
            v = int(max(0.0, min(vals[0], 1.0)) * 255)
            return f"{v:02X}" * 3
        if len(vals) == 3:
            return "".join(f"{int(max(0.0, min(c, 1.0)) * 255):02X}" for c in vals)
        if len(vals) == 4:  # CMYK
            c, m, y, k = vals
            return "".join(f"{int(255 * (1 - min(1.0, x + k))):02X}" for x in (c, m, y))
    except (TypeError, ValueError):
        pass
    return "000000"


def font_info(fontname: str) -> tuple[str, bool, bool]:
    name = SUBSET_RE.sub("", fontname or "")
    low = name.lower()
    bold = any(k in low for k in ("bold", "black", "heavy", "semibold", "demi"))
    italic = any(k in low for k in ("italic", "oblique"))
    family = re.split(r"[-,]", name)[0]
    family = re.sub(r"(MT|PS|PSMT|Std|Pro)$", "", family)
    family = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", family).strip()
    aliases = {"Arial": "Arial", "Helvetica": "Arial", "Times New Roman": "Times New Roman", "Times": "Times New Roman",
               "Courier": "Courier New", "Courier New": "Courier New", "Glyph Less Font": "Arial", "": "Calibri"}
    for k, v in aliases.items():
        if family.lower() == k.lower():
            family = v
            break
    return family or "Calibri", bold, italic


def _lines(words: list[dict]) -> list[Line]:
    """Group words into visual lines, splitting where a large horizontal gap suggests a column break."""
    words = sorted(words, key=lambda w: (round(w["top"] / 2), w["x0"]))
    rows: list[list[dict]] = []
    for w in words:
        placed = False
        for row in reversed(rows[-6:]):
            ref = row[-1]
            h = min(w["bottom"] - w["top"], ref["bottom"] - ref["top"]) or 1
            overlap = min(w["bottom"], ref["bottom"]) - max(w["top"], ref["top"])
            if overlap > 0.5 * h:
                row.append(w)
                placed = True
                break
        if not placed:
            rows.append([w])
    lines: list[Line] = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        segment: list[dict] = [row[0]]
        for w in row[1:]:
            gap = w["x0"] - segment[-1]["x1"]
            size = max(w.get("size", 10), segment[-1].get("size", 10))
            if gap > max(3.0 * size, 36):
                lines.append(_make_line(segment))
                segment = [w]
            else:
                segment.append(w)
        lines.append(_make_line(segment))
    return lines


def _make_line(words: list[dict]) -> Line:
    runs: list[Run] = []
    prev = None
    for w in words:
        family, bold, italic = font_info(w.get("fontname", ""))
        color = _hex(w.get("non_stroking_color"))
        size = round(float(w.get("size", 10)), 1)
        text = w["text"]
        if prev is not None:
            text = " " + text
        if runs and (runs[-1].font, runs[-1].size, runs[-1].bold, runs[-1].italic, runs[-1].color) == (family, size, bold, italic, color):
            runs[-1].text += text
        else:
            runs.append(Run(text, family, size, bold, italic, color))
        prev = w
    return Line(min(w["x0"] for w in words), min(w["top"] for w in words), max(w["x1"] for w in words),
                max(w["bottom"] for w in words), runs)


def _reading_order(lines: list[Line], width: float) -> tuple[list[Line], dict[int, str]]:
    """Order lines for reading, detecting a two-column body. Returns lines and a side map (id->left/right/full)."""
    mid = width / 2
    side = {}
    for ln in lines:
        side[id(ln)] = "left" if ln.x1 < mid + 8 else "right" if ln.x0 > mid - 8 else "full"
    left = [l for l in lines if side[id(l)] == "left"]
    right = [l for l in lines if side[id(l)] == "right"]
    full = [l for l in lines if side[id(l)] == "full"]
    if len(left) >= 4 and len(right) >= 4 and len(full) < 0.3 * len(lines):
        zone_top = min(l.top for l in left + right)
        above = sorted([l for l in full if l.top < zone_top], key=lambda l: l.top)
        below = sorted([l for l in full if l.top >= zone_top], key=lambda l: l.top)
        return above + sorted(left, key=lambda l: l.top) + sorted(right, key=lambda l: l.top) + below, side
    for k in side:
        side[k] = "full"
    return sorted(lines, key=lambda l: (round(l.top), l.x0)), side


def _paragraphs(lines: list[Line], side: dict[int, str]) -> list[Block]:
    if not lines:
        return []
    gaps = [b.top - a.bottom for a, b in zip(lines, lines[1:]) if 0 <= b.top - a.bottom < a.size * 2.5 and side[id(a)] == side[id(b)]]
    typical = statistics.median(gaps) if gaps else 3.0
    blocks: list[Block] = []
    cur: Block | None = None
    for ln in lines:
        text = ln.text
        bullet = BULLET_RE.match(text)
        number = NUMBER_RE.match(text)
        start_new = cur is None
        if cur is not None:
            prev = cur.lines[-1]
            gap = ln.top - prev.bottom
            col_right = max(l.x1 for l in cur.lines)
            if side[id(ln)] != side[id(prev)] or gap < -prev.size or gap > typical * 1.7 + 1.5:
                start_new = True
            elif abs(ln.size - prev.size) > 0.15 * prev.size or ln.bold != prev.bold and len(text) < 90:
                start_new = True
            elif bullet or number:
                start_new = True
            elif prev.text.rstrip().endswith((".", ":", "?", "!")) and prev.x1 < col_right - 4 * prev.size:
                start_new = True
            elif ln.x0 > cur.lines[0].x0 + 1.8 * ln.size and cur.kind != "list":
                start_new = True
        if start_new:
            cur = Block("list" if (bullet or number) else "para", ln.top, ln.x0, ln.x1, [], lines=[])
            if bullet or number:
                cur.list_kind = "bullet" if bullet else "number"
                marker_len = (bullet or number).end()
                runs = [Run(r.text, r.font, r.size, r.bold, r.italic, r.color) for r in ln.runs]
                cut = marker_len
                while runs and cut > 0:
                    if len(runs[0].text) <= cut:
                        cut -= len(runs[0].text)
                        runs.pop(0)
                    else:
                        runs[0].text = runs[0].text[cut:]
                        cut = 0
                cur.runs = runs
            else:
                cur.runs = [Run(r.text, r.font, r.size, r.bold, r.italic, r.color) for r in ln.runs]
            cur.lines.append(ln)
            blocks.append(cur)
            continue
        # continuation line: join with hyphenation handling
        last = cur.runs[-1] if cur.runs else None
        first_text = ln.runs[0].text if ln.runs else ""
        if last and last.text.endswith("-") and first_text[:1].islower():
            last.text = last.text[:-1]
        elif last:
            last.text += " "
        for r in ln.runs:
            if cur.runs and (cur.runs[-1].font, cur.runs[-1].size, cur.runs[-1].bold, cur.runs[-1].italic, cur.runs[-1].color) == (r.font, r.size, r.bold, r.italic, r.color):
                cur.runs[-1].text += r.text
            else:
                cur.runs.append(Run(r.text, r.font, r.size, r.bold, r.italic, r.color))
        cur.lines.append(ln)
        cur.x0, cur.x1 = min(cur.x0, ln.x0), max(cur.x1, ln.x1)
    return blocks


def _normalize_boxes(src: Path, dst: Path) -> Path:
    """Make MediaBox == visible CropBox so every library agrees on coordinates."""
    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            geo = g.PageGeometry.of(page)
            box = pikepdf.Array([geo.x0, geo.y0, geo.x1, geo.y1])
            page.obj["/MediaBox"] = box
            if "/CropBox" in page.obj:
                del page.obj["/CropBox"]
        pdf.save(dst)
    return dst


def analyze(pdf_path: Path, workdir: Path, progress=None) -> tuple[list[PageModel], float]:
    norm = _normalize_boxes(pdf_path, workdir / "__layout__.pdf")
    img_dir = workdir / "__layout_images__"
    img_dir.mkdir(exist_ok=True)
    pages: list[PageModel] = []
    size_counter: Counter = Counter()
    pdoc = raster.open_doc(norm)
    with pdfplumber.open(norm) as pdf, pikepdf.open(norm) as pk:
        n = len(pdf.pages)
        for pno, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["fontname", "size", "non_stroking_color"], x_tolerance=1.5,
                                       y_tolerance=2.5, keep_blank_chars=False, use_text_flow=False)
            ocr_page = any("GlyphLess" in (w.get("fontname") or "") for w in words)
            for w in words:
                size_counter[round(float(w.get("size", 10)), 1)] += len(w["text"])
            # tables
            tables = []
            try:
                for t in page.find_tables():
                    rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t.extract()]
                    if rows and len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        tables.append((t.bbox, rows))
            except Exception:
                tables = []

            def in_table(w):
                cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
                return any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b, _ in tables)

            text_words = [w for w in words if not in_table(w)]
            lines = _lines(text_words) if text_words else []
            ordered, side = _reading_order(lines, float(page.width))
            blocks = _paragraphs(ordered, side)
            # images
            images: list[Block] = []
            geo = g.PageGeometry.of(pk.pages[pno])
            area = float(page.width) * float(page.height)
            for k, img in enumerate(raster.iter_images(pdoc[pno])):
                try:
                    vb = geo.user_rect_to_view(img.get_bounds())
                except Exception:
                    continue
                w, h = vb[2] - vb[0], vb[3] - vb[1]
                if w < 20 or h < 20 or (ocr_page and w * h > 0.6 * area):
                    continue
                try:
                    pil = img.get_bitmap(render=True).to_pil().convert("RGB")
                except Exception:
                    continue
                path = img_dir / f"p{pno + 1}-{k + 1}.png"
                pil.save(path, optimize=True)
                images.append(Block("image", vb[1], vb[0], vb[2], image=path, width=w, height=h))
            extras = [Block("table", b[1], b[0], b[2], rows=rows) for b, rows in tables] + images
            for ex in sorted(extras, key=lambda b: b.top):
                ex_side = "full"
                if any(v != "full" for v in side.values()):
                    ex_side = "left" if ex.x1 < float(page.width) / 2 + 8 else "right" if ex.x0 > float(page.width) / 2 - 8 else "full"
                pos = len(blocks)
                for i, b in enumerate(blocks):
                    b_side = side.get(id(b.lines[0]), "full") if b.lines else "full"
                    if b.top > ex.top and (ex_side == "full" or b_side in (ex_side, "full")):
                        pos = i
                        break
                blocks.insert(pos, ex)
            xs0 = [b.x0 for b in blocks if b.kind != "image"] or [54]
            xs1 = [b.x1 for b in blocks if b.kind != "image"] or [float(page.width) - 54]
            tops = [b.top for b in blocks] or [54]
            pages.append(PageModel(float(page.width), float(page.height), blocks, max(18.0, min(xs0)),
                                   max(18.0, float(page.width) - max(xs1)), max(18.0, min(tops))))
            if progress:
                progress((pno + 1) / n, f"Analysing page {pno + 1} of {n}")
    pdoc.close()
    body = size_counter.most_common(1)[0][0] if size_counter else 11.0
    for pm in pages:
        _classify(pm, body)
    return pages, body


def _classify(pm: PageModel, body: float) -> None:
    for b in pm.blocks:
        if b.kind not in ("para",) or not b.lines:
            continue
        size = statistics.median([l.size for l in b.lines])
        text = b.text
        single = len(b.lines) <= 2 and len(text) < 160
        if size >= body * 1.5 and single:
            b.kind, b.level = "heading", 1
        elif size >= body * 1.22 and single:
            b.kind, b.level = "heading", 2
        elif size >= body * 1.08 and all(l.bold for l in b.lines) and single:
            b.kind, b.level = "heading", 3
        if len(b.lines) == 1:
            ln = b.lines[0]
            center = (ln.x0 + ln.x1) / 2
            width = pm.width - pm.margin_left - pm.margin_right
            if abs(center - pm.width / 2) < pm.width * 0.05 and (ln.x1 - ln.x0) < width * 0.8 and ln.x0 > pm.margin_left + 20:
                b.align = "center"
            elif ln.x0 > pm.width / 2 and abs(ln.x1 - (pm.width - pm.margin_right)) < 12:
                b.align = "right"
