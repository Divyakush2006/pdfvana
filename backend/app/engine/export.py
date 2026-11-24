"""Writers that turn analysed PDF pages into Office and text formats."""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pdfplumber
import pikepdf

from ..util import ToolError
from . import layout as lay
from . import raster

XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _clean(s: str) -> str:
    return XML_BAD.sub("", s or "")


# --------------------------------------------------------------------------- Word

def to_docx(pdf: Path, dst: Path, workdir: Path, progress=None) -> Path:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    pages, body = lay.analyze(pdf, workdir, progress)
    doc = Document()
    fonts = [r.font for pm in pages for b in pm.blocks for r in b.runs]
    base_font = max(set(fonts), key=fonts.count) if fonts else "Calibri"
    normal = doc.styles["Normal"]
    normal.font.name = base_font
    normal.font.size = Pt(body)
    normal.paragraph_format.space_after = Pt(max(2.0, body * 0.45))
    align = {"center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT}

    def add_runs(p, runs, heading=False):
        for r in runs:
            text = _clean(r.text)
            if not text:
                continue
            run = p.add_run(text)
            f = run.font
            f.name = r.font
            f.size = Pt(max(1.0, r.size))
            f.bold = r.bold if not heading else (r.bold or None)
            f.italic = r.italic
            if r.color and r.color != "000000":
                f.color.rgb = RGBColor.from_string(r.color)
            elif heading:
                f.color.rgb = RGBColor(0, 0, 0)

    for i, pm in enumerate(pages):
        section = doc.sections[0] if i == 0 else doc.add_section(WD_SECTION.NEW_PAGE)
        section.page_width, section.page_height = Pt(pm.width), Pt(pm.height)
        section.left_margin = Pt(min(pm.margin_left, pm.width / 3))
        section.right_margin = Pt(min(pm.margin_right, pm.width / 3))
        section.top_margin = Pt(min(pm.margin_top, pm.height / 4))
        section.bottom_margin = Pt(36)
        text_width = pm.width - section.left_margin.pt - section.right_margin.pt
        for b in pm.blocks:
            if b.kind == "heading":
                p = doc.add_heading(level=min(b.level, 3))
                add_runs(p, b.runs, heading=True)
            elif b.kind == "list":
                style = "List Bullet" if b.list_kind == "bullet" else "List Number"
                p = doc.add_paragraph(style=style)
                add_runs(p, b.runs)
            elif b.kind == "para":
                p = doc.add_paragraph()
                add_runs(p, b.runs)
            elif b.kind == "table":
                cols = max(len(r) for r in b.rows)
                t = doc.add_table(rows=len(b.rows), cols=cols)
                t.style = "Table Grid"
                for ri, row in enumerate(b.rows):
                    for ci in range(cols):
                        cell = t.cell(ri, ci)
                        cell.text = _clean(row[ci] if ci < len(row) else "")
                        if ri == 0:
                            for para in cell.paragraphs:
                                for run in para.runs:
                                    run.font.bold = True
                doc.add_paragraph()
                continue
            elif b.kind == "image" and b.image and b.image.exists():
                try:
                    doc.add_picture(str(b.image), width=Pt(min(b.width, text_width)))
                except Exception:
                    pass
                continue
            else:
                continue
            if b.align in align:
                p.alignment = align[b.align]
    if not any(pm.blocks for pm in pages):
        raise ToolError("No text was found. If this is a scanned document, enable text recognition (OCR).")
    doc.save(dst)
    return dst


# --------------------------------------------------------------------------- Markdown / HTML

def _md_inline(runs: list[lay.Run], heading: bool = False) -> str:
    parts = []
    for r in runs:
        t = _clean(r.text)
        if not t.strip():
            parts.append(t)
            continue
        t = re.sub(r"([\\`*_\[\]])", r"\\\1", t)
        lead, core, trail = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S).groups()
        if not heading and r.bold and r.italic:
            core = f"***{core}***"
        elif not heading and r.bold:
            core = f"**{core}**"
        elif r.italic:
            core = f"*{core}*"
        parts.append(lead + core + trail)
    return re.sub(r"\*\*\s*\*\*", "", "".join(parts)).strip()


def to_markdown(pdf: Path, workdir: Path, include_images: bool = False, progress=None) -> tuple[str, Path]:
    pages, _ = lay.analyze(pdf, workdir, progress)
    out: list[str] = []
    for pm in pages:
        n = 0
        for b in pm.blocks:
            if b.kind == "heading":
                out.append("#" * min(b.level, 6) + " " + _md_inline(b.runs, True))
            elif b.kind == "para":
                out.append(_md_inline(b.runs))
            elif b.kind == "list":
                n = n + 1 if b.list_kind == "number" else 0
                out.append(("1. " if b.list_kind == "number" else "- ") + _md_inline(b.runs))
                continue
            elif b.kind == "table":
                cols = max(len(r) for r in b.rows)
                rows = [[_clean(c).replace("|", "\\|") for c in r] + [""] * (cols - len(r)) for r in b.rows]
                out.append("| " + " | ".join(rows[0]) + " |")
                out.append("|" + "---|" * cols)
                out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
            elif b.kind == "image" and include_images and b.image:
                out.append(f"![]({b.image.name})")
            n = 0
            out.append("")
        out.append("")
    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    if not md.strip():
        raise ToolError("No text was found. If this is a scanned document, enable text recognition (OCR).")
    return md, workdir / "__layout_images__"


# --------------------------------------------------------------------------- PowerPoint

def _strip_text_ops(instructions):
    out, depth = [], 0
    for item in instructions:
        op = str(item.operator)
        if op == "BT":
            depth += 1
            continue
        if op == "ET":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        out.append(item)
    return out


def strip_text(src: Path, dst: Path) -> Path:
    """Copy of the PDF with every text object removed (keeps images and vector art)."""
    with pikepdf.open(src) as pdf:
        seen: set = set()

        def walk_resources(res):
            if not res or "/XObject" not in res:
                return
            for _, xo in res["/XObject"].items():
                try:
                    if xo.get("/Subtype") != "/Form" or xo.objgen in seen:
                        continue
                    seen.add(xo.objgen)
                    xo.write(pikepdf.unparse_content_stream(_strip_text_ops(pikepdf.parse_content_stream(xo))))
                    walk_resources(xo.get("/Resources"))
                except Exception:
                    continue

        for page in pdf.pages:
            try:
                ops = _strip_text_ops(pikepdf.parse_content_stream(page))
                page.obj["/Contents"] = pdf.make_stream(pikepdf.unparse_content_stream(ops))
            except Exception:
                continue
            walk_resources(page.obj.get("/Resources"))
        pdf.save(dst)
    return dst


def to_pptx(pdf: Path, dst: Path, workdir: Path, editable: bool = True, dpi: int = 160, progress=None) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Pt

    norm = lay._normalize_boxes(pdf, workdir / "__pptx_norm__.pdf")
    bg_src = strip_text(norm, workdir / "__pptx_bg__.pdf") if editable else norm
    bg_doc = raster.open_doc(bg_src)
    EMU = 12700
    prs = Presentation()
    with pdfplumber.open(norm) as plumb:
        n = len(plumb.pages)
        first = plumb.pages[0]
        prs.slide_width, prs.slide_height = Emu(int(float(first.width) * EMU)), Emu(int(float(first.height) * EMU))
        blank = prs.slide_layouts[6]
        for i, page in enumerate(plumb.pages):
            pw, ph = float(page.width), float(page.height)
            sx, sy = prs.slide_width / (pw * EMU), prs.slide_height / (ph * EMU)
            slide = prs.slides.add_slide(blank)
            words = page.extract_words(extra_attrs=["fontname", "size", "non_stroking_color"], x_tolerance=1.5, y_tolerance=2.5) if editable else []
            ocr_page = any("GlyphLess" in (w.get("fontname") or "") for w in words)
            img_doc = raster.open_doc(norm) if ocr_page else None
            bg = raster.render((img_doc or bg_doc)[i], dpi)
            if img_doc:
                img_doc.close()
            buf = io.BytesIO()
            bg.save(buf, format="PNG", optimize=True)
            slide.shapes.add_picture(io.BytesIO(buf.getvalue()), 0, 0, prs.slide_width, prs.slide_height)
            if editable and not ocr_page and words:
                for ln in lay._lines(words):
                    box = slide.shapes.add_textbox(
                        Emu(int(ln.x0 * EMU * sx)), Emu(int(ln.top * EMU * sy)),
                        Emu(int(max(ln.x1 - ln.x0, 4) * EMU * sx * 1.06)), Emu(int(max(ln.bottom - ln.top, 4) * EMU * sy)))
                    tf = box.text_frame
                    tf.word_wrap = False
                    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                    para = tf.paragraphs[0]
                    for r in ln.runs:
                        run = para.add_run()
                        run.text = _clean(r.text)
                        f = run.font
                        f.size = Pt(max(1.0, round(r.size * sy, 1)))
                        f.name, f.bold, f.italic = r.font, r.bold, r.italic
                        f.color.rgb = RGBColor.from_string(r.color or "000000")
            if progress:
                progress((i + 1) / n, f"Slide {i + 1} of {n}")
    bg_doc.close()
    prs.save(dst)
    return dst


# --------------------------------------------------------------------------- Excel / CSV

def _cell_value(val):
    if val is None:
        return None
    s = str(val).replace("\n", " ").strip()
    t = s.replace(",", "").replace("₹", "").replace("$", "").replace("€", "").replace("£", "").replace("%", "").strip()
    if t and re.fullmatch(r"-?\d+(\.\d+)?", t):
        num = float(t)
        if s.endswith("%"):
            return num / 100
        return int(num) if "." not in t else num
    return s


def _page_tables(page) -> list[list[list[str]]]:
    out = []
    try:
        for t in page.find_tables():
            rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in t.extract()]
            if rows:
                out.append(rows)
    except Exception:
        pass
    return out


def _text_rows(page) -> list[list[str]]:
    words = page.extract_words(extra_attrs=["size"], x_tolerance=1.5, y_tolerance=2.5)
    if not words:
        return []
    segments = lay._lines(words)
    rows: list[list[lay.Line]] = []
    for seg in sorted(segments, key=lambda s: (s.top, s.x0)):
        if rows and abs(rows[-1][0].top - seg.top) < max(3.0, 0.4 * seg.size):
            rows[-1].append(seg)
        else:
            rows.append([seg])
    return [[s.text for s in sorted(r, key=lambda s: s.x0)] for r in rows]


def to_xlsx(pdf: Path, dst: Path, progress=None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="D0D5DD")
    head = PatternFill("solid", fgColor="E8F5EE")
    with pdfplumber.open(pdf) as plumb:
        n = len(plumb.pages)
        for i, page in enumerate(plumb.pages):
            ws = wb.create_sheet(f"Page {i + 1}")
            row = 1
            tables = _page_tables(page)
            for rows in tables:
                for r_i, r in enumerate(rows):
                    for c_i, val in enumerate(r):
                        cell = ws.cell(row=row, column=c_i + 1, value=_cell_value(val))
                        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                        if r_i == 0:
                            cell.font, cell.fill = Font(bold=True), head
                    row += 1
                row += 1
            if not tables:
                for r in _text_rows(page):
                    for c_i, val in enumerate(r):
                        ws.cell(row=row, column=c_i + 1, value=_cell_value(val))
                    row += 1
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, width + 2), 60)
            if progress:
                progress((i + 1) / n, f"Page {i + 1} of {n}")
    wb.save(dst)
    return dst


def to_csv(pdf: Path, outdir: Path, base: str) -> list[Path]:
    out = []
    with pdfplumber.open(pdf) as plumb:
        for i, page in enumerate(plumb.pages):
            for t_i, rows in enumerate(_page_tables(page)):
                p = outdir / f"{base}-page{i + 1}-table{t_i + 1}.csv"
                with p.open("w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerows(rows)
                out.append(p)
    if not out:
        raise ToolError("No tables were detected in this PDF. Try PDF to Excel instead.")
    return out
