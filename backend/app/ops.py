"""PDF -> PDF operations: organise, optimise, edit, secure and compare."""
from __future__ import annotations

import difflib
import io
import os
import re
import shutil
from pathlib import Path
from collections.abc import Callable

import pikepdf

from .engine import geometry as g
from .engine import raster
from .engine.stamp import Stamper, anchor, image_stamp, rect_overlay, text_stamps
from .util import ToolError, hex_to_rgb, human_size, parse_pages, run

Progress = Callable[[float, str], None]
PAPER = {"a4": (595.28, 841.89), "letter": (612.0, 792.0)}


# --------------------------------------------------------------------------- helpers

def open_pike(path: Path, password: str = "") -> pikepdf.Pdf:
    try:
        pdf = pikepdf.open(path, password=password or "")
    except pikepdf.PasswordError as exc:
        raise ToolError("This PDF is password protected. Unlock it first.") from exc
    except pikepdf.PdfError as exc:
        raise ToolError("This file is not a valid PDF or is damaged. Try the Repair tool first.") from exc
    if len(pdf.pages) == 0:
        raise ToolError("This PDF has no pages.")
    return pdf


def page_count(src: Path) -> int:
    with open_pike(src) as pdf:
        return len(pdf.pages)


def _place_page(dst_pdf: pikepdf.Pdf, target: pikepdf.Page, src_page: pikepdf.Page, rect: tuple[float, float, float, float],
                expand: bool = True) -> None:
    """Draw ``src_page`` (as seen, with its rotation) scaled into ``rect`` (user space) of ``target``."""
    form = dst_pdf.copy_foreign(src_page.as_form_xobject(handle_transformations=True))
    name = target.add_resource(form, pikepdf.Name.XObject, prefix="Pg")
    ops = target.calc_form_xobject_placement(form, name, pikepdf.Rectangle(*rect), invert_transformations=True,
                                             allow_shrink=True, allow_expand=expand)
    target.contents_add(pikepdf.Stream(dst_pdf, b"q\n" + ops + b"\nQ\n"))


# --------------------------------------------------------------------------- organise

def merge(items: list[tuple[Path, str]], dst: Path, bookmarks: bool = True, normalize: str = "none") -> Path:
    out = pikepdf.new()
    sources = []
    first_size: tuple[float, float] | None = None
    with out.open_outline() as outline:
        for path, title in items:
            src = open_pike(path)
            sources.append(src)
            start = len(out.pages)
            if normalize and normalize != "none":
                for page in src.pages:
                    geo = g.PageGeometry.of(page)
                    if normalize == "first":
                        first_size = first_size or (geo.width, geo.height)
                        bw, bh = first_size
                    else:
                        bw, bh = PAPER.get(normalize, PAPER["a4"])
                    if (geo.width > geo.height) != (bw > bh):
                        bw, bh = bh, bw
                    out.add_blank_page(page_size=(bw, bh))
                    _place_page(out, out.pages[-1], page, (0, 0, bw, bh))
            else:
                out.pages.extend(src.pages)
            if bookmarks and len(out.pages) > start:
                outline.root.append(pikepdf.OutlineItem(title, start))
    out.save(dst)
    for s in sources:
        s.close()
    return dst


def select_pages(src: Path, dst: Path, indexes: list[int]) -> Path:
    pdf = open_pike(src)
    out = pikepdf.new()
    for i in indexes:
        out.pages.append(pdf.pages[i])
    out.save(dst)
    pdf.close()
    return dst


def organize(src: Path, dst: Path, layout: list[dict]) -> Path:
    """layout: [{"p": zero-based page or -1 for blank, "r": extra rotation}, ...]"""
    pdf = open_pike(src)
    out = pikepdf.new()
    n = len(pdf.pages)
    for item in layout:
        p, r = int(item.get("p", 0)), int(item.get("r", 0)) % 360
        if p == -1:
            geo = g.PageGeometry.of(pdf.pages[0])
            out.add_blank_page(page_size=(geo.width, geo.height))
        else:
            if not 0 <= p < n:
                raise ToolError("The page layout refers to a page that does not exist.")
            out.pages.append(pdf.pages[p])
        if r:
            out.pages[-1].rotate(r, relative=True)
    if not len(out.pages):
        raise ToolError("You removed every page. Keep at least one.")
    out.save(dst)
    pdf.close()
    return dst


def rotate(src: Path, dst: Path, angle: int, pages: str = "all") -> Path:
    pdf = open_pike(src)
    for i in parse_pages(pages, len(pdf.pages)):
        pdf.pages[i].rotate(int(angle), relative=True)
    pdf.save(dst)
    pdf.close()
    return dst


# --------------------------------------------------------------------------- optimise

COMPRESS_LEVELS = {"light": (220, 0.25), "recommended": (150, 0.45), "strong": (110, 0.7), "extreme": (80, 1.0)}


def _gs_compress(src: Path, dst: Path, dpi: int, qfactor: float, grayscale: bool = False) -> Path:
    q = f"<< /QFactor {qfactor} /Blend 1 /HSamples [2 1 1 2] /VSamples [2 1 1 2] >>"
    args = [
        "gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
        "-dDetectDuplicateImages=true", "-dCompressFonts=true", "-dSubsetFonts=true", "-dEmbedAllFonts=true",
        "-dPassThroughJPEGImages=false", "-dPassThroughJPXImages=false",
        "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Bicubic", f"-dColorImageResolution={dpi}",
        "-dColorImageDownsampleThreshold=1.2",
        "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Bicubic", f"-dGrayImageResolution={dpi}",
        "-dGrayImageDownsampleThreshold=1.2",
        "-dDownsampleMonoImages=true", "-dMonoImageDownsampleType=/Subsample", f"-dMonoImageResolution={max(dpi * 2, 200)}",
        "-dAutoFilterColorImages=false", "-dColorImageFilter=/DCTEncode",
        "-dAutoFilterGrayImages=false", "-dGrayImageFilter=/DCTEncode",
    ]
    if grayscale:
        args += ["-sColorConversionStrategy=Gray", "-dProcessColorModel=/DeviceGray"]
    args += [f"-sOutputFile={dst}", "-c", f"<< /ColorImageDict {q} /GrayImageDict {q} >> setdistillerparams", "-f", str(src)]
    run(args)
    return dst


def _qpdf_optimize(src: Path, dst: Path) -> Path:
    run(["qpdf", "--object-streams=generate", "--compress-streams=y", "--recompress-flate",
         "--compression-level=9", "--linearize", str(src), str(dst)], ok_codes=(0, 3))
    return dst


def compress(src: Path, dst: Path, level: str = "recommended", target_mb: float = 0, grayscale: bool = False,
             progress: Progress | None = None) -> tuple[Path, str]:
    work = dst.parent
    original = src.stat().st_size
    candidates: list[Path] = []
    try:
        candidates.append(_qpdf_optimize(src, work / f"{dst.stem}-lossless.pdf"))
    except Exception:
        pass
    if target_mb and target_mb > 0:
        target = target_mb * 1024 * 1024
        ladder = [(220, .3), (170, .4), (140, .5), (120, .6), (100, .76), (85, .9), (72, 1.1), (60, 1.35), (50, 1.6), (40, 2.0)]
        hit = None
        for i, (dpi, q) in enumerate(ladder):
            if progress:
                progress(0.1 + 0.8 * i / len(ladder), f"Trying {dpi} dpi")
            c = _gs_compress(src, work / f"{dst.stem}-{dpi}.pdf", dpi, q, grayscale)
            candidates.append(c)
            if c.stat().st_size <= target:
                hit = c
                break
        best = hit or min(candidates, key=lambda p: p.stat().st_size)
    else:
        dpi, q = COMPRESS_LEVELS.get(level, COMPRESS_LEVELS["recommended"])
        if progress:
            progress(0.3, "Optimising images and fonts")
        candidates.append(_gs_compress(src, work / f"{dst.stem}-gs.pdf", dpi, q, grayscale))
        best = min(candidates, key=lambda p: p.stat().st_size)
    try:
        final = _qpdf_optimize(best, work / f"{dst.stem}-final.pdf")
        if final.stat().st_size < best.stat().st_size:
            best = final
    except Exception:
        pass
    if best.stat().st_size >= original and not grayscale:
        shutil.copyfile(src, dst)
        return dst, "This PDF is already well optimised — we kept the original."
    shutil.move(str(best), dst)
    new = dst.stat().st_size
    note = ""
    if target_mb and new > target_mb * 1024 * 1024:
        note = f" Smallest possible without losing readability; above your {target_mb:g} MB target."
    return dst, f"{human_size(original)} → {human_size(new)} ({100 - new * 100 / original:.0f}% smaller).{note}"


def repair(src: Path, dst: Path) -> tuple[Path, str]:
    def with_pikepdf():
        with pikepdf.open(src, attempt_recovery=True) as pdf:
            pdf.save(dst)

    attempts = [
        lambda: run(["qpdf", "--decrypt", str(src), str(dst)], ok_codes=(0, 3)),
        with_pikepdf,
        lambda: run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", f"-sOutputFile={dst}", str(src)]),
    ]
    for attempt in attempts:
        try:
            attempt()
            with pikepdf.open(dst) as pdf:
                if len(pdf.pages) > 0:
                    return dst, f"Recovered {len(pdf.pages)} page(s)."
        except Exception:
            continue
    raise ToolError("This file is too badly damaged to recover.")


def to_pdfa(src: Path, dst: Path, level: str = "2") -> Path:
    level = level if level in ("1", "2", "3") else "2"
    try:
        run(["ocrmypdf", "-q", "--skip-text", "--tesseract-timeout", "0", "--optimize", "0",
             "--invalidate-digital-signatures", "--output-type", f"pdfa-{level}", str(src), str(dst)], ok_codes=(0, 10))
    except Exception:
        run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", f"-dPDFA={level}", "-dPDFACompatibilityPolicy=1",
             "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite", f"-sOutputFile={dst}", str(src)])
    return dst


def ocr_languages() -> list[str]:
    try:
        out = run(["tesseract", "--list-langs"], timeout=20).stdout.splitlines()
        return sorted(l.strip() for l in out[1:] if l.strip() and l.strip() not in ("osd", "equ"))
    except Exception:
        return ["eng"]


def ocr(src: Path, dst: Path, langs: list[str] | str = "eng", mode: str = "skip", deskew: bool = True,
        rotate_pages: bool = True, clean: bool = False, pdfa: bool = False, sidecar: Path | None = None) -> Path:
    if isinstance(langs, str):
        langs = [l for l in re.split(r"[+, ]+", langs) if l]
    available = set(ocr_languages())
    langs = [l for l in langs if l in available] or ["eng"]
    args = ["ocrmypdf", "-q", "-l", "+".join(langs), "--jobs", str(max(1, (os.cpu_count() or 2) // 2)),
            "--output-type", "pdfa-2" if pdfa else "pdf", "--optimize", "1", "--invalidate-digital-signatures"]
    args.append({"force": "--force-ocr", "redo": "--redo-ocr"}.get(mode, "--skip-text"))
    if mode != "redo":
        if deskew:
            args.append("--deskew")
        if clean:
            args.append("--clean")
    if rotate_pages:
        args.append("--rotate-pages")
    if sidecar:
        args += ["--sidecar", str(sidecar)]
    try:
        run(args + [str(src), str(dst)], ok_codes=(0, 10))
    except RuntimeError as exc:
        if "Tagged PDF" in str(exc) or "page already has text" in str(exc):
            run([a for a in args if a not in ("--skip-text", "--redo-ocr", "--deskew", "--clean")] + ["--force-ocr", str(src), str(dst)], ok_codes=(0, 10))
        else:
            raise
    return dst


# --------------------------------------------------------------------------- security

def protect(src: Path, dst: Path, user_pw: str, owner_pw: str = "", allow_print: bool = True,
            allow_copy: bool = True, allow_modify: bool = False) -> Path:
    if not user_pw:
        raise ToolError("Please enter a password.")
    pdf = open_pike(src)
    perms = pikepdf.Permissions(
        print_lowres=allow_print, print_highres=allow_print, extract=allow_copy, accessibility=True,
        modify_annotation=allow_modify, modify_assembly=allow_modify, modify_form=allow_modify, modify_other=allow_modify,
    )
    pdf.save(dst, encryption=pikepdf.Encryption(user=user_pw, owner=owner_pw or user_pw + "#owner", R=6, allow=perms))
    pdf.close()
    return dst


def unlock(src: Path, dst: Path, password: str = "") -> Path:
    try:
        pdf = pikepdf.open(src, password=password or "")
    except pikepdf.PasswordError as exc:
        raise ToolError("Wrong password. Enter the password used to open this PDF." if password
                        else "This PDF needs its password to be unlocked. Enter it and try again.") from exc
    except pikepdf.PdfError as exc:
        raise ToolError("This file is not a valid PDF.") from exc
    pdf.save(dst)
    pdf.close()
    return dst


REDACT_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "phone": r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?!\w)",
    "card": r"\b(?:\d[ -]?){13,19}\b",
    "url": r"https?://\S+|www\.\S+",
    "date": r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "pan": r"\b[A-Z]{5}\d{4}[A-Z]\b",
}


def redact(src: Path, dst: Path, terms: str = "", patterns: list[str] | None = None, case_sensitive: bool = False,
           color: str = "#000000", dpi: int = 200, keep_searchable: bool = True) -> tuple[Path, str]:
    """True redaction: pages with matches are re-drawn as images with the boxes burned in, so the
    original text, vectors and images underneath cannot be recovered. Text is then re-recognised so the
    rest of the page stays searchable."""
    from PIL import ImageDraw

    words = [t.strip() for t in re.split(r"[\n,]+", terms or "") if t.strip()]
    regexes = [re.compile(re.escape(w), 0 if case_sensitive else re.IGNORECASE) for w in words]
    regexes += [re.compile(REDACT_PATTERNS[p]) for p in (patterns or []) if p in REDACT_PATTERNS]
    if not regexes:
        raise ToolError("Enter words to redact or choose at least one type of information.")
    rgb = tuple(int(c * 255) for c in hex_to_rgb(color))
    doc = raster.open_doc(src)
    hits: dict[int, list[tuple[float, float, float, float]]] = {}
    pdf = open_pike(src)
    try:
        for i in range(len(doc)):
            text, boxes = raster.char_boxes(doc[i])
            found = []
            for rx in regexes:
                for m in rx.finditer(text):
                    if len(m.group(0).strip()) >= 2:
                        found += raster.span_boxes(boxes, m.start(), m.end())
            if found:
                hits[i] = found
        if not hits:
            pdf.close()
            shutil.copyfile(src, dst)
            return dst, "No matching text was found, so nothing was redacted."
        import img2pdf

        total = 0
        replacements: list[pikepdf.Pdf] = []  # must stay open until the target is saved
        for i, found in hits.items():
            page = pdf.pages[i]
            geo = g.PageGeometry.of(page)
            img = raster.render(doc[i], dpi)
            draw = ImageDraw.Draw(img)
            sx, sy = img.width / geo.width, img.height / geo.height
            for b in found:
                u0, v0, u1, v1 = geo.user_rect_to_view(b)
                pad = 1.0
                draw.rectangle([(u0 - pad) * sx, (v0 - pad) * sy, (u1 + pad) * sx, (v1 + pad) * sy], fill=rgb)
            total += len(found)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
            layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
            one = pikepdf.open(io.BytesIO(img2pdf.convert(buf.getvalue(), layout_fun=layout)))
            replacements.append(one)
            pdf.pages.insert(i, one.pages[0])
            del pdf.pages[i + 1]
        pdf.docinfo = pdf.make_indirect(pikepdf.Dictionary())
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
        tmp = dst.with_name(dst.stem + "-raster.pdf")
        pdf.save(tmp)
        for one in replacements:
            one.close()
    finally:
        doc.close()
        pdf.close()
    if keep_searchable:
        try:
            ocr(tmp, dst, "eng", "skip", deskew=False, rotate_pages=False)
        except Exception:
            shutil.move(str(tmp), dst)
    else:
        shutil.move(str(tmp), dst)
    return dst, f"Permanently removed {total} item(s) on {len(hits)} page(s)."


def sanitize(src: Path, dst: Path, metadata=True, javascript=True, attachments=True, links=False, forms=False,
             hidden_text=False) -> Path:
    pdf = open_pike(src)
    root = pdf.Root
    if javascript:
        for key in ("/OpenAction", "/AA"):
            if key in root:
                del root[key]
        names = root.get("/Names")
        if names is not None and "/JavaScript" in names:
            del names["/JavaScript"]
    if attachments:
        names = root.get("/Names")
        if names is not None and "/EmbeddedFiles" in names:
            del names["/EmbeddedFiles"]
    if metadata:
        pdf.docinfo = pdf.make_indirect(pikepdf.Dictionary())
        if "/Metadata" in root:
            del root["/Metadata"]
    if "/AcroForm" in root and javascript:
        af = root["/AcroForm"]
        if "/XFA" in af:
            del af["/XFA"]
    for page in pdf.pages:
        obj = page.obj
        if javascript and "/AA" in obj:
            del obj["/AA"]
        if "/Thumb" in obj:
            del obj["/Thumb"]
        if metadata and "/Metadata" in obj:
            del obj["/Metadata"]
        annots = obj.get("/Annots")
        if annots is None:
            continue
        keep = pikepdf.Array()
        for a in annots:
            sub = a.get("/Subtype")
            if attachments and sub == "/FileAttachment":
                continue
            if links and sub == "/Link":
                continue
            if javascript:
                act = a.get("/A")
                if act is not None and act.get("/S") in ("/JavaScript", "/Launch", "/SubmitForm", "/ImportData"):
                    continue
                if "/AA" in a:
                    del a["/AA"]
            if forms and sub == "/Widget" and "/V" in a:
                del a["/V"]
            keep.append(a)
        obj["/Annots"] = keep
    _ = hidden_text
    pdf.remove_unreferenced_resources()
    pdf.save(dst)
    pdf.close()
    return dst


# --------------------------------------------------------------------------- edit

POSITIONS = ("top-left", "top-center", "top-right", "middle-left", "center", "middle-right",
             "bottom-left", "bottom-center", "bottom-right")


def _grid(view_w: float, view_h: float, w: float, h: float) -> list[tuple[float, float]]:
    step_x, step_y = w * 1.15 + 40, h * 1.3 + 40
    out, y, row = [], -h / 2, 0
    while y < view_h + h:
        x = -w / 2 + (row % 2) * step_x / 2
        while x < view_w + w:
            out.append((x, y))
            x += step_x
        y += step_y
        row += 1
    return out


def watermark(src: Path, dst: Path, text: str = "", image: Path | None = None, font_size: int = 48,
              opacity: float = 0.3, rotation: int = 45, position: str = "center", color: str = "#d32f2f",
              pages: str = "all", mosaic: bool = False, bold: bool = True, image_scale: float = 0.4,
              layer: str = "over") -> Path:
    opacity = max(0.02, min(float(opacity), 1.0))
    if image is not None:
        stamp = image_stamp(image, opacity)
    else:
        if not text.strip():
            raise ToolError("Enter the watermark text or choose an image.")
        stamp = text_stamps([text], font_size, color, opacity, bold)[0]
    pdf = open_pike(src)
    st = Stamper(pdf)
    for i in parse_pages(pages, len(pdf.pages)):
        page = pdf.pages[i]
        geo = g.PageGeometry.of(page)
        width = geo.width * max(0.05, min(float(image_scale), 1.0)) if image is not None else stamp.width
        height = width * stamp.height / stamp.width
        bw, bh = g.rotated_size(width, height, rotation)
        spots = _grid(geo.width, geo.height, bw, bh) if mosaic else [anchor(geo.width, geo.height, position, bw, bh, 24)]
        for x, y in spots:
            st.place(page, stamp, (x + bw / 2, y + bh / 2), width, rotation, under=layer == "under")
    pdf.save(dst)
    pdf.close()
    return dst


def page_numbers(src: Path, dst: Path, position: str = "bottom-center", fmt: str = "{n}", start: int = 1,
                 font_size: int = 11, margin: int = 28, pages: str = "all", skip_first: bool = False,
                 color: str = "#333333") -> Path:
    pdf = open_pike(src)
    selected = parse_pages(pages, len(pdf.pages))
    if skip_first:
        selected = [i for i in selected if i != 0]
    offset = 1 if skip_first else 0
    total = start + len(pdf.pages) - 1 - offset
    fmt = fmt or "{n}"
    labels = [fmt.replace("{n}", str(start + i - offset)).replace("{total}", str(total)) for i in selected]
    stamps = text_stamps(labels, font_size, color, 1.0, False)
    st = Stamper(pdf)
    for i, stamp in zip(selected, stamps):
        page = pdf.pages[i]
        geo = g.PageGeometry.of(page)
        x, y = anchor(geo.width, geo.height, position, stamp.width, stamp.height, margin)
        st.place(page, stamp, (x + stamp.width / 2, y + stamp.height / 2), stamp.width)
    pdf.save(dst)
    pdf.close()
    return dst


def header_footer(src: Path, dst: Path, header: str = "", footer: str = "", font_size: int = 10,
                  color: str = "#444444", align: str = "center") -> Path:
    pdf = open_pike(src)
    total = len(pdf.pages)
    jobs = []
    for i in range(total):
        for text, v in ((header, "top"), (footer, "bottom")):
            if text:
                jobs.append((i, v, text.replace("{n}", str(i + 1)).replace("{total}", str(total))))
    if not jobs:
        raise ToolError("Enter a header or a footer.")
    stamps = text_stamps([j[2] for j in jobs], font_size, color, 1.0, False)
    st = Stamper(pdf)
    for (i, v, _), stamp in zip(jobs, stamps):
        page = pdf.pages[i]
        geo = g.PageGeometry.of(page)
        x, y = anchor(geo.width, geo.height, f"{v}-{align}", stamp.width, stamp.height, 22)
        st.place(page, stamp, (x + stamp.width / 2, y + stamp.height / 2), stamp.width)
    pdf.save(dst)
    pdf.close()
    return dst


def stamp_image(src: Path, dst: Path, image: Path, pages: str = "last", x: float = 0.62, y: float = 0.82,
                width: float = 0.28) -> Path:
    """Place an image (signature, stamp, logo) at a relative position (fractions of the visible page)."""
    stamp = image_stamp(image, 1.0, trim=True)
    pdf = open_pike(src)
    st = Stamper(pdf)
    spec = {"first": "1", "last": "last"}.get(pages, pages)
    for i in parse_pages(spec, len(pdf.pages)):
        page = pdf.pages[i]
        geo = g.PageGeometry.of(page)
        w = geo.width * max(0.03, min(float(width), 1.0))
        h = w * stamp.height / stamp.width
        x0 = min(max(0.0, float(x)) * geo.width, geo.width - w)
        y0 = min(max(0.0, float(y)) * geo.height, geo.height - h)
        st.place(page, stamp, (x0 + w / 2, y0 + h / 2), w)
    pdf.save(dst)
    pdf.close()
    return dst


def crop(src: Path, dst: Path, mode: str = "auto", top: float = 10, right: float = 10, bottom: float = 10,
         left: float = 10, pages: str = "all") -> Path:
    pdf = open_pike(src)
    doc = raster.open_doc(src) if mode == "auto" else None
    mm = 72 / 25.4
    try:
        for i in parse_pages(pages, len(pdf.pages)):
            page = pdf.pages[i]
            geo = g.PageGeometry.of(page)
            if mode == "auto":
                img = raster.render(doc[i], 50, grayscale=True)
                box = raster.content_bbox(img)
                if not box:
                    continue
                sx, sy = geo.width / img.width, geo.height / img.height
                pad = 6
                view = (max(0, box[0] * sx - pad), max(0, box[1] * sy - pad),
                        min(geo.width, box[2] * sx + pad), min(geo.height, box[3] * sy + pad))
            else:
                view = (left * mm, top * mm, geo.width - right * mm, geo.height - bottom * mm)
            if view[2] - view[0] < 20 or view[3] - view[1] < 20:
                raise ToolError("Those margins would remove the whole page.")
            page.obj["/CropBox"] = pikepdf.Array(list(geo.view_rect_to_user(view)))
        pdf.save(dst)
    finally:
        if doc:
            doc.close()
        pdf.close()
    return dst


def flatten(src: Path, dst: Path, rasterize: bool = False, dpi: int = 200) -> Path:
    if rasterize:
        import img2pdf

        doc = raster.open_doc(src)
        try:
            imgs = []
            for i in range(len(doc)):
                buf = io.BytesIO()
                raster.render(doc[i], dpi).save(buf, format="JPEG", quality=90)
                imgs.append(buf.getvalue())
        finally:
            doc.close()
        dst.write_bytes(img2pdf.convert(imgs, layout_fun=img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))))
        return dst
    pdf = open_pike(src)
    try:
        pdf.generate_appearance_streams()
    except Exception:
        pass
    pdf.flatten_annotations(mode="all")
    if "/AcroForm" in pdf.Root:
        del pdf.Root["/AcroForm"]
    pdf.save(dst)
    pdf.close()
    return dst


def set_metadata(src: Path, dst: Path, title="", author="", subject="", keywords="", clear=False) -> Path:
    pdf = open_pike(src)
    if clear:
        pdf.docinfo = pdf.make_indirect(pikepdf.Dictionary())
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        if title:
            meta["dc:title"] = title
        if author:
            meta["dc:creator"] = [author]
        if subject:
            meta["dc:description"] = subject
        if keywords:
            meta["pdf:Keywords"] = keywords
    for key, val in (("/Title", title), ("/Author", author), ("/Subject", subject), ("/Keywords", keywords)):
        if val:
            pdf.docinfo[key] = val
    pdf.save(dst)
    pdf.close()
    return dst


# --------------------------------------------------------------------------- compare

def compare(a: Path, b: Path, dst: Path) -> tuple[Path, str]:
    """Side-by-side report: removed words highlighted red on the left, added words green on the right."""
    docs = [raster.open_doc(a), raster.open_doc(b)]
    pdfs = [open_pike(a), open_pike(b)]
    try:
        word_lists = []
        for doc in docs:
            ws = []
            for i in range(len(doc)):
                ws += raster.words(doc[i], i)
            word_lists.append(ws)
        wa, wb = word_lists
        if not wa and not wb:
            raise ToolError("Neither document contains selectable text. Run OCR on them first.")
        sm = difflib.SequenceMatcher(None, [w.text for w in wa], [w.text for w in wb], autojunk=False)
        marks: list[dict[int, list]] = [{}, {}]
        removed = added = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("replace", "delete"):
                for w in wa[i1:i2]:
                    marks[0].setdefault(w.page, []).append(w.box)
                removed += i2 - i1
            if tag in ("replace", "insert"):
                for w in wb[j1:j2]:
                    marks[1].setdefault(w.page, []).append(w.box)
                added += j2 - j1

        out = pikepdf.new()
        st = Stamper(out)
        head, gap = 30.0, 24.0
        n = max(len(pdfs[0].pages), len(pdfs[1].pages))
        for i in range(n):
            geos = [g.PageGeometry.of(p.pages[min(i, len(p.pages) - 1)]) for p in pdfs]
            wa_, wb_ = geos[0].width, geos[1].width
            H = max(geos[0].height, geos[1].height) + head
            W = wa_ + gap + wb_
            out.add_blank_page(page_size=(W, H))
            page = out.pages[-1]
            rects = []
            labels = [(10, 19, f"Original - page {i + 1}", (0.62, 0.1, 0.1), 10),
                      (wa_ + gap + 10, 19, f"Changed - page {i + 1}", (0.05, 0.45, 0.2), 10)]
            for side, (pdf, geo, xoff, rgb) in enumerate(((pdfs[0], geos[0], 0.0, (1, 0.3, 0.3)),
                                                          (pdfs[1], geos[1], wa_ + gap, (0.2, 0.8, 0.35)))):
                if i >= len(pdf.pages):
                    continue
                top = H - head
                _place_page(out, page, pdf.pages[i], (xoff, top - geo.height, xoff + geo.width, top), expand=False)
                for box in marks[side].get(i, []):
                    u0, v0, u1, v1 = geo.user_rect_to_view(box)
                    rects.append((xoff + u0, head + v0, u1 - u0, v1 - v0, rgb, 0.38))
            rects.append((wa_ + gap / 2 - 0.5, 0, 1, H, (0.8, 0.8, 0.8), 1))
            overlay = rect_overlay(W, H, rects, labels)
            st.place(page, overlay, (W / 2, H / 2), W)
        out.save(dst)
    finally:
        for d in docs:
            d.close()
        for p in pdfs:
            p.close()
    ratio = sm.ratio() * 100
    if removed == 0 and added == 0:
        return dst, "The documents contain identical text."
    return dst, f"{removed} word(s) removed, {added} word(s) added — {ratio:.0f}% similar."
