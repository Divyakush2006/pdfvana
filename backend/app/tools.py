"""Tool registry: every tool's metadata, option schema and handler.

The frontend renders tool pages entirely from this registry (GET /api/tools),
so adding a tool here is all it takes to ship it.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Callable

from . import convert as cv
from . import data as datamod
from . import formats as F
from . import media, ops
from .engine import raster
from .util import ToolError, ext_of, parse_pages, parse_ranges, run, stem, zip_files


# --------------------------------------------------------------------------- schema

@dataclass
class Option:
    id: str
    label: str
    type: str  # select | number | text | password | checkbox | range | color | textarea | multiselect | position | pages
    default: Any = None
    choices: list[dict] | None = None
    help: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    placeholder: str | None = None
    show_if: dict[str, list] | None = None


@dataclass
class ExtraFile:
    id: str
    label: str
    accept: list[str]
    required: bool = True


@dataclass
class InputFile:
    path: Path
    name: str


@dataclass
class Ctx:
    inputs: list[InputFile]
    extras: dict[str, InputFile]
    options: dict[str, Any]
    workdir: Path
    progress: Callable[[float, str], None]
    message: str = ""

    def out(self, name: str) -> Path:
        return self.workdir / name

    def pdfs(self, lo: float = 0.0, hi: float = 0.5) -> list[tuple[Path, str]]:
        """Every input normalised to PDF, keeping the original names."""
        result = []
        n = len(self.inputs)
        for i, f in enumerate(self.inputs):
            self.progress(lo + (hi - lo) * i / max(n, 1), f"Preparing {f.name}")
            result.append((cv.to_pdf(f.path, self.workdir, f.name), f.name))
        self.progress(hi, "Processing")
        return result

    @property
    def first(self) -> InputFile:
        return self.inputs[0]

    def first_pdf(self) -> Path:
        return self.pdfs(0, 0.2)[0][0]


@dataclass
class Tool:
    id: str
    name: str
    description: str
    category: str
    icon: str
    handler: Callable[[Ctx], Path]
    accept: list[str] = field(default_factory=lambda: ["pdf"])
    multiple: bool = False
    min_files: int = 1
    max_files: int | None = None
    options: list[Option] = field(default_factory=list)
    extra_files: list[ExtraFile] = field(default_factory=list)
    cta: str = "Process"
    ui: str | None = None  # special screens: organize | sign | compare | url | studio
    badge: str | None = None
    keywords: str = ""

    def public(self) -> dict:
        d = asdict(self)
        d.pop("handler")
        return d


CATEGORIES = [
    {"id": "workflow", "name": "Workflows"},
    {"id": "organize", "name": "Organize PDF"},
    {"id": "optimize", "name": "Optimize PDF"},
    {"id": "to-pdf", "name": "Convert to PDF"},
    {"id": "from-pdf", "name": "Convert from PDF"},
    {"id": "image", "name": "Image tools"},
    {"id": "media", "name": "Audio & video"},
    {"id": "edit", "name": "Edit PDF"},
    {"id": "security", "name": "PDF Security"},
    {"id": "intelligence", "name": "PDF Intelligence"},
]

PDF = ["pdf"]
ANY = ["*"]
IMAGES = sorted(F.IMAGE_EXT)
RASTER = sorted(F.IMAGE_EXT - {"svg"})
AUDIO = sorted(F.AUDIO_EXT)
VIDEO = sorted(F.VIDEO_EXT)
MEDIA = sorted(F.AUDIO_EXT | F.VIDEO_EXT | {"gif"})
TABLES = sorted(F.DATA_EXT | {"xlsx", "xlsm"})
WORD = ["doc", "docx", "docm", "dot", "dotx", "odt", "ott", "rtf", "txt", "pages", "wpd", "wps"]
PPT = ["ppt", "pptx", "pptm", "pps", "ppsx", "pot", "potx", "odp", "key"]
EXCEL = ["xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "ods", "csv", "numbers"]

POSITION_CHOICES = [{"value": p, "label": p.replace("-", " ").title()} for p in ops.POSITIONS]
FORMAT_CHOICES = [{"value": k, "label": v[0]} for k, v in F.FORMATS.items()]
DOC_FORMAT_CHOICES = [{"value": k, "label": F.FORMATS[k][0]} for k in F.DOC_TARGETS]
QUALITY = ["high", "High", "medium", "Balanced", "low", "Small file"]
RESOLUTION = ["", "Keep original", "2160", "4K (2160p)", "1440", "1440p", "1080", "Full HD (1080p)", "720", "HD (720p)",
              "480", "480p", "360", "360p"]

PANDOC_IN = {"docx": "docx", "odt": "odt", "md": "markdown", "markdown": "markdown", "html": "html", "htm": "html",
             "epub": "epub", "rst": "rst", "tex": "latex", "latex": "latex", "org": "org", "rtf": "rtf", "ipynb": "ipynb",
             "fb2": "fb2", "textile": "textile"}
PANDOC_OUT = {"docx": "docx", "odt": "odt", "md": "gfm", "html": "html5", "epub": "epub3", "rtf": "rtf", "txt": "plain"}


def convert_any(path: Path, name: str, fmt: str, workdir: Path, opts: dict, progress=None) -> list[Path]:
    """Route one file to the best converter for (its category, target format)."""
    cat = F.category(name)
    fmt = fmt.lower()
    tcat = "document" if fmt == "pdfa" else F.FORMATS.get(fmt, ("", ""))[1]
    base = stem(name)
    e = ext_of(name)
    if not tcat:
        raise ToolError(f"Unknown output format: {fmt}")
    if fmt not in F.TARGETS.get(cat, []):
        raise ToolError(f"{e.upper() or 'This file'} can't be converted to {fmt.upper()}. "
                        f"Choose one of: {', '.join(x.upper() for x in F.TARGETS.get(cat, []))}.")
    if cat == "animation":
        cat = "video" if tcat == "video" else "image"
    if cat in ("audio", "video"):
        mo = dict(opts)
        mo["quality"] = opts.get("quality_av") or (opts.get("quality") if isinstance(opts.get("quality"), str) else "medium")
        return [media.convert_media(path, workdir, base, fmt, mo)]
    if cat == "image" and (tcat == "image" or fmt == "pdf"):
        return media.convert_image(path, workdir, base, fmt, opts)
    if cat in ("data", "spreadsheet") and fmt in ("xlsx", "csv", "json", "html", "md") and e in F.DATA_EXT | {"xlsx", "xlsm"}:
        if e == fmt:
            raise ToolError(f"The file is already {fmt.upper()}.")
        return [datamod.convert_table(path, name, workdir, fmt)]
    if e in PANDOC_IN and fmt in PANDOC_OUT and e != fmt and not (e in ("html", "htm") and fmt == "html"):
        dst = workdir / f"{base}.{fmt}"
        args = ["pandoc", "--sandbox", str(path), "-f", PANDOC_IN[e], "-t", PANDOC_OUT[fmt], "-s", "-o", str(dst)]
        if fmt == "html":
            args += ["--embed-resources", "--metadata", f"pagetitle={base}"]
        run(args, timeout=300)
        return [dst]
    # Everything else goes through PDF.
    pdf = cv.to_pdf(path, workdir, name)
    if fmt in ("docx", "odt", "rtf", "xlsx", "csv", "json", "txt", "md", "html", "epub") and opts.get("auto_ocr", True) \
            and raster.is_scanned(pdf):
        if progress:
            progress(0.3, "Recognising text")
        ocred = workdir / f"{base}.__ocr__.pdf"
        ops.ocr(pdf, ocred, opts.get("ocr_lang", "eng"), "skip")
        pdf = ocred
    return cv.from_pdf(pdf, fmt, workdir, base, opts, progress)


def ch(*pairs: str) -> list[dict]:
    return [{"value": pairs[i], "label": pairs[i + 1]} for i in range(0, len(pairs), 2)]


def _single_or_zip(ctx: Ctx, outputs: list[Path], zip_name: str) -> Path:
    if len(outputs) == 1:
        return outputs[0]
    return zip_files([(p, p.name) for p in outputs], ctx.out(zip_name))


def _per_pdf(ctx: Ctx, fn: Callable[[Path, Path, str], Path], suffix: str, zip_name: str) -> Path:
    """Apply a PDF->PDF function to every input; zip when there are several."""
    outputs = []
    pdfs = ctx.pdfs(0, 0.3)
    for i, (pdf, name) in enumerate(pdfs):
        ctx.progress(0.3 + 0.65 * i / len(pdfs), f"Processing {name}")
        outputs.append(fn(pdf, ctx.out(f"{stem(name)}{suffix}.pdf"), name))
    return _single_or_zip(ctx, outputs, zip_name)


# --------------------------------------------------------------------------- handlers: organise

def h_merge(ctx: Ctx) -> Path:
    pdfs = ctx.pdfs(0, 0.7)
    o = ctx.options
    dst = ctx.out("merged.pdf")
    ops.merge([(p, stem(n)) for p, n in pdfs], dst, bookmarks=o.get("bookmarks", True), normalize=o.get("normalize", "none"))
    ctx.message = f"Merged {len(pdfs)} files into {ops.page_count(dst)} pages."
    return dst


def h_split(ctx: Ctx) -> Path:
    pdf = ctx.first_pdf()
    base = stem(ctx.first.name)
    total = ops.page_count(pdf)
    o = ctx.options
    mode = o.get("mode", "ranges")
    if mode == "ranges":
        groups = parse_ranges(o.get("ranges", ""), total)
    elif mode == "every":
        n = max(1, int(o.get("every", 1)))
        groups = [list(range(i, min(i + n, total))) for i in range(0, total, n)]
    else:  # all
        groups = [[i] for i in range(total)]
    if o.get("merge_output") and mode == "ranges":
        dst = ctx.out(f"{base}_extracted.pdf")
        return ops.select_pages(pdf, dst, [i for g in groups for i in g])
    outputs = []
    for g in groups:
        label = f"{g[0] + 1}" if len(g) == 1 else f"{g[0] + 1}-{g[-1] + 1}"
        outputs.append(ops.select_pages(pdf, ctx.out(f"{base}_pages_{label}.pdf"), g))
    ctx.message = f"Created {len(outputs)} PDF file(s)."
    return _single_or_zip(ctx, outputs, f"{base}_split.zip")


def h_remove_pages(ctx: Ctx) -> Path:
    pdf = ctx.first_pdf()
    total = ops.page_count(pdf)
    remove = set(parse_pages(ctx.options.get("pages", ""), total))
    keep = [i for i in range(total) if i not in remove]
    if not keep:
        raise ToolError("You can't remove every page.")
    ctx.message = f"Removed {len(remove)} page(s); {len(keep)} remain."
    return ops.select_pages(pdf, ctx.out(f"{stem(ctx.first.name)}_edited.pdf"), keep)


def h_extract_pages(ctx: Ctx) -> Path:
    pdf = ctx.first_pdf()
    idx = parse_pages(ctx.options.get("pages", ""), ops.page_count(pdf))
    if ctx.options.get("separate"):
        outs = [ops.select_pages(pdf, ctx.out(f"{stem(ctx.first.name)}_page_{i + 1}.pdf"), [i]) for i in idx]
        return _single_or_zip(ctx, outs, f"{stem(ctx.first.name)}_pages.zip")
    return ops.select_pages(pdf, ctx.out(f"{stem(ctx.first.name)}_extracted.pdf"), idx)


def h_organize(ctx: Ctx) -> Path:
    pdf = ctx.first_pdf()
    raw = ctx.options.get("layout") or "[]"
    try:
        layout = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ToolError("Invalid page layout.") from exc
    if not layout:
        layout = [{"p": i, "r": 0} for i in range(ops.page_count(pdf))]
    return ops.organize(pdf, ctx.out(f"{stem(ctx.first.name)}_organized.pdf"), layout)


def h_rotate(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.rotate(p, d, int(o.get("angle", 90)), o.get("pages", "all")), "_rotated", "rotated.zip")


# --------------------------------------------------------------------------- handlers: optimise

def h_compress(ctx: Ctx) -> Path:
    o = ctx.options
    notes = []
    outputs = []
    pdfs = ctx.pdfs(0, 0.1)
    for i, (pdf, name) in enumerate(pdfs):
        def prog(f, m, i=i):
            ctx.progress(0.1 + 0.85 * (i + f) / len(pdfs), m)
        target = float(o.get("target_mb") or 0) if o.get("level") == "target" else 0
        dst, note = ops.compress(pdf, ctx.out(f"{stem(name)}_compressed.pdf"), o.get("level", "recommended"),
                                 target, bool(o.get("grayscale")), prog)
        outputs.append(dst)
        notes.append(note if len(pdfs) == 1 else f"{name}: {note}")
    ctx.message = " ".join(notes)
    return _single_or_zip(ctx, outputs, "compressed.zip")


def h_repair(ctx: Ctx) -> Path:
    notes = []

    def fn(p, d, n):
        out, note = ops.repair(p, d)
        notes.append(note)
        return out
    out = _per_pdf(ctx, fn, "_repaired", "repaired.zip")
    ctx.message = " ".join(notes)
    return out


def h_ocr(ctx: Ctx) -> Path:
    o = ctx.options
    langs = o.get("languages") or ["eng"]
    outputs = []
    pdfs = ctx.pdfs(0, 0.15)
    for i, (pdf, name) in enumerate(pdfs):
        ctx.progress(0.15 + 0.8 * i / len(pdfs), f"Recognising text in {name}")
        dst = ctx.out(f"{stem(name)}_ocr.pdf")
        side = ctx.out(f"{stem(name)}_ocr.txt") if o.get("output") == "txt" else None
        ops.ocr(pdf, dst, langs, o.get("mode", "skip"), o.get("deskew", True), o.get("rotate_pages", True),
                o.get("clean", False), o.get("output") == "pdfa", side)
        outputs.append(side or dst)
    return _single_or_zip(ctx, outputs, "ocr.zip")


def h_pdfa(ctx: Ctx) -> Path:
    lvl = ctx.options.get("level", "2")
    return _per_pdf(ctx, lambda p, d, n: ops.to_pdfa(p, d, lvl), "_pdfa", "pdfa.zip")


# --------------------------------------------------------------------------- handlers: convert

def h_to_pdf(ctx: Ctx) -> Path:
    pdfs = ctx.pdfs(0, 0.9)
    if ctx.options.get("merge") and len(pdfs) > 1:
        dst = ctx.out("combined.pdf")
        ops.merge([(p, stem(n)) for p, n in pdfs], dst)
        return dst
    outputs = []
    for p, n in pdfs:
        dst = ctx.out(f"{stem(n)}.pdf")
        if p != dst:
            shutil.copyfile(p, dst)
        outputs.append(dst)
    return _single_or_zip(ctx, outputs, "converted.zip")


def h_images_to_pdf(ctx: Ctx) -> Path:
    o = ctx.options
    imgs = [f for f in ctx.inputs if ext_of(f.name) in F.IMAGE_EXT and ext_of(f.name) != "svg"]
    others = [f for f in ctx.inputs if f not in imgs]
    if o.get("merge", True):
        ctx.progress(0.3, "Building PDF")
        dst = ctx.out(f"{stem(ctx.first.name)}.pdf" if len(ctx.inputs) == 1 else "images.pdf")
        parts: list[tuple[Path, str]] = []
        if imgs:
            ip = cv.images_to_pdf([f.path for f in imgs], ctx.out("_images.pdf"), o.get("page_size", "fit"),
                                  o.get("orientation", "auto"), o.get("margin", "none"))
            parts.append((ip, "Images"))
        for f in others:
            parts.append((cv.to_pdf(f.path, ctx.workdir, f.name), stem(f.name)))
        if len(parts) == 1:
            shutil.move(str(parts[0][0]), dst)
        else:
            ops.merge(parts, dst, bookmarks=False)
        return dst
    outputs = []
    for f in ctx.inputs:
        outputs.append(cv.images_to_pdf([f.path], ctx.out(f"{stem(f.name)}.pdf"), o.get("page_size", "fit"),
                                        o.get("orientation", "auto"), o.get("margin", "none")))
    return _single_or_zip(ctx, outputs, "images.zip")


def h_html_to_pdf(ctx: Ctx) -> Path:
    o = ctx.options
    url = (o.get("url") or "").strip()
    if url:
        ctx.progress(0.2, "Loading web page")
        from urllib.parse import urlparse

        host = urlparse(url if "://" in url else "https://" + url).hostname or "webpage"
        return cv.url_to_pdf(url, ctx.out(f"{host}.pdf"), o)
    if not ctx.inputs:
        raise ToolError("Enter a web address or upload an HTML file.")
    return cv.html_to_pdf(ctx.first.path, ctx.out(f"{stem(ctx.first.name)}.pdf"), opts=o)


def _from_pdf_tool(fmt_key: str | None = None):
    def handler(ctx: Ctx) -> Path:
        o = ctx.options
        fmt = fmt_key or o.get("format", "docx")
        if fmt == "image":
            fmt = o.get("image_format", "jpg")
        outputs: list[Path] = []
        pdfs = ctx.pdfs(0, 0.1)
        for i, (pdf, name) in enumerate(pdfs):
            if o.get("auto_ocr", True) and fmt in ("docx", "odt", "rtf", "xlsx", "csv", "txt", "md", "html", "epub") and raster.is_scanned(pdf):
                ctx.progress(0.12, f"Scanned document detected — recognising text in {name}")
                ocred = ctx.out(f"{stem(name)}.__ocr__.pdf")
                ops.ocr(pdf, ocred, o.get("ocr_lang", "eng"), "skip")
                pdf = ocred

            def prog(f, m, i=i):
                ctx.progress(0.2 + 0.75 * (i + f) / len(pdfs), m)
            outputs += cv.from_pdf(pdf, fmt, ctx.workdir, stem(name), o, prog)
        zip_name = f"{stem(ctx.first.name) if len(pdfs) == 1 else 'converted'}_{fmt}.zip"
        return _single_or_zip(ctx, outputs, zip_name)
    return handler


def h_pdf_to_images(ctx: Ctx) -> Path:
    o = ctx.options
    if o.get("mode") == "extract":
        pdf = ctx.first_pdf()
        d = ctx.out("images")
        d.mkdir(exist_ok=True)
        outs = cv.extract_images(pdf, d)
        ctx.message = f"Extracted {len(outs)} image(s)."
        return _single_or_zip(ctx, outs, f"{stem(ctx.first.name)}_images.zip")
    return _from_pdf_tool("image")(ctx)


def h_universal(ctx: Ctx) -> Path:
    """Any file(s) -> any format: documents, images, audio, video and data."""
    o = ctx.options
    fmt = str(o.get("format", "pdf")).lower()
    items = [(f.path, f.name) for f in ctx.inputs]
    if o.get("merge") and len(items) > 1:
        if any(F.category(n) in ("audio", "video") for _, n in items):
            raise ToolError("Audio and video files can't be combined. Untick “Combine all files”.")
        pdfs = ctx.pdfs(0, 0.4)
        merged = ctx.out("combined.pdf")
        ops.merge([(p, stem(n)) for p, n in pdfs], merged)
        items = [(merged, "combined.pdf")]
    outputs: list[Path] = []
    for i, (path, name) in enumerate(items):
        def prog(f, m, i=i):
            ctx.progress(0.1 + 0.85 * (i + f) / len(items), m)
        ctx.progress(0.1 + 0.85 * i / len(items), f"Converting {name}")
        outputs += convert_any(path, name, fmt, ctx.workdir, o, prog)
    return _single_or_zip(ctx, outputs, f"{stem(items[0][1]) if len(items) == 1 else 'converted'}_{fmt}.zip")


# --------------------------------------------------------------------------- handlers: images

def h_image_convert(ctx: Ctx) -> Path:
    o = ctx.options
    fmt = o.get("format", "png")
    outs: list[Path] = []
    for i, f in enumerate(ctx.inputs):
        ctx.progress(0.1 + 0.85 * i / len(ctx.inputs), f"Converting {f.name}")
        outs += media.convert_image(f.path, ctx.workdir, stem(f.name), fmt, o)
    return _single_or_zip(ctx, outs, f"images_{fmt}.zip")


def h_image_compress(ctx: Ctx) -> Path:
    o = ctx.options
    outs, notes = [], []
    for i, f in enumerate(ctx.inputs):
        ctx.progress(0.1 + 0.85 * i / len(ctx.inputs), f"Compressing {f.name}")
        target = float(o.get("target_kb") or 0) if o.get("mode") == "target" else 0
        dst, note = media.compress_image(f.path, ctx.workdir, stem(f.name), int(o.get("quality", 75)), target,
                                         int(o.get("max_side") or 0), o.get("output", "same"))
        outs.append(dst)
        notes.append(note if len(ctx.inputs) == 1 else f"{f.name}: {note}")
    ctx.message = " ".join(notes)
    return _single_or_zip(ctx, outs, "compressed_images.zip")


def h_image_edit(ctx: Ctx) -> Path:
    o = ctx.options
    mode = o.get("resize_mode", "none")
    outs = [media.edit_image(f.path, ctx.workdir, stem(f.name), int(o.get("rotate", 0) or 0), o.get("flip", "none"),
                             int(o.get("width") or 0) if mode == "pixels" else 0,
                             int(o.get("height") or 0) if mode == "pixels" else 0,
                             float(o.get("percent") or 0) if mode == "percent" else 0, o.get("fit", "contain"),
                             bool(o.get("grayscale"))) for f in ctx.inputs]
    return _single_or_zip(ctx, outs, "edited_images.zip")


def h_image_svg(ctx: Ctx) -> Path:
    o = ctx.options
    outs = [media.image_to_svg(f.path, ctx.out(f"{stem(f.name)}.svg"), o.get("svg_mode", "trace"),
                               o.get("svg_colors", "color"), o.get("svg_detail", "medium")) for f in ctx.inputs]
    return _single_or_zip(ctx, outs, "vectors_svg.zip")


def h_favicon(ctx: Ctx) -> Path:
    o = ctx.options
    files = media.favicon_pack(ctx.first.path, ctx.workdir, o.get("site_name") or "My Site", o.get("color", "#0f766e"))
    ctx.message = "Unzip into your website's root folder and paste the lines from install.html into your <head>."
    return zip_files([(p, p.name) for p in files], ctx.out("favicon-package.zip"))


def h_strip_exif(ctx: Ctx) -> Path:
    outs = [media.edit_image(f.path, ctx.workdir, stem(f.name)) for f in ctx.inputs]
    ctx.message = "Location, camera and date information has been removed."
    return _single_or_zip(ctx, outs, "clean_images.zip")


def h_html_to_image(ctx: Ctx) -> Path:
    o = ctx.options
    fmt = o.get("format", "png")
    url = (o.get("url") or "").strip()
    if not url and not ctx.inputs:
        raise ToolError("Enter a web address or upload an HTML file.")
    from urllib.parse import urlparse

    name = (urlparse(url if "://" in url else "https://" + url).hostname or "webpage") if url else stem(ctx.first.name)
    return cv.url_to_image(url or None, None if url else ctx.first.path, ctx.out(f"{name}.{fmt}"), fmt,
                           int(o.get("width") or 1440), bool(o.get("full_page", True)))


# --------------------------------------------------------------------------- handlers: audio & video

def _media_tool(fmt_option: str = "format", fixed: str | None = None):
    def handler(ctx: Ctx) -> Path:
        o = ctx.options
        fmt = fixed or o.get(fmt_option, "mp4")
        outs = []
        for i, f in enumerate(ctx.inputs):
            ctx.progress(0.1 + 0.85 * i / len(ctx.inputs), f"Converting {f.name}")
            outs.append(media.convert_media(f.path, ctx.workdir, stem(f.name), fmt, o))
        return _single_or_zip(ctx, outs, f"converted_{fmt}.zip")
    return handler


def h_compress_video(ctx: Ctx) -> Path:
    o = ctx.options
    outs, notes = [], []
    for i, f in enumerate(ctx.inputs):
        ctx.progress(0.1 + 0.85 * i / len(ctx.inputs), f"Compressing {f.name}")
        dst, note = media.compress_video(f.path, ctx.workdir, stem(f.name), o.get("level", "medium"), o.get("resolution", ""))
        outs.append(dst)
        notes.append(note)
    ctx.message = " ".join(notes)
    return _single_or_zip(ctx, outs, "compressed_videos.zip")


def h_data_convert(ctx: Ctx) -> Path:
    fmt = ctx.options.get("format", "xlsx")
    outs = [convert_any(f.path, f.name, fmt, ctx.workdir, ctx.options) for f in ctx.inputs]
    return _single_or_zip(ctx, [p for group in outs for p in group], f"converted_{fmt}.zip")


# --------------------------------------------------------------------------- handlers: edit & security

def h_watermark(ctx: Ctx) -> Path:
    o = ctx.options
    img = ctx.extras.get("image")
    use_img = o.get("kind") == "image"
    if use_img and not img:
        raise ToolError("Choose an image for the watermark.")
    return _per_pdf(ctx, lambda p, d, n: ops.watermark(
        p, d, text=o.get("text", ""), image=img.path if (use_img and img) else None, font_size=int(o.get("font_size", 48)),
        opacity=float(o.get("opacity", 0.3)), rotation=int(o.get("rotation", 45)), position=o.get("position", "center"),
        color=o.get("color", "#d32f2f"), pages=o.get("pages", "all"), mosaic=bool(o.get("mosaic")),
        image_scale=float(o.get("image_scale", 0.4)), layer=o.get("layer", "over")), "_watermarked", "watermarked.zip")


def h_page_numbers(ctx: Ctx) -> Path:
    o = ctx.options
    fmt = {"n": "{n}", "page_n": "Page {n}", "n_of_total": "{n} / {total}", "page_n_of_total": "Page {n} of {total}"}.get(
        o.get("format", "n"), "{n}")
    if o.get("format") == "custom":
        fmt = o.get("custom") or "{n}"
    return _per_pdf(ctx, lambda p, d, n: ops.page_numbers(
        p, d, o.get("position", "bottom-center"), fmt, int(o.get("start", 1)), int(o.get("font_size", 11)),
        int(o.get("margin", 28)), o.get("pages", "all"), bool(o.get("skip_first")), o.get("color", "#333333")),
        "_numbered", "numbered.zip")


def h_header_footer(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.header_footer(
        p, d, o.get("header", ""), o.get("footer", ""), int(o.get("font_size", 10)), o.get("color", "#444444"),
        o.get("align", "center")), "_header", "header_footer.zip")


def h_sign(ctx: Ctx) -> Path:
    o = ctx.options
    sig = ctx.extras.get("signature")
    if not sig:
        raise ToolError("Create or upload your signature first.")
    pdf = ctx.first_pdf()
    return ops.stamp_image(pdf, ctx.out(f"{stem(ctx.first.name)}_signed.pdf"), sig.path, o.get("pages", "last"),
                           float(o.get("x", 0.62)), float(o.get("y", 0.82)), float(o.get("width", 0.28)))


def h_crop(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.crop(
        p, d, o.get("mode", "auto"), float(o.get("top", 10)), float(o.get("right", 10)), float(o.get("bottom", 10)),
        float(o.get("left", 10)), o.get("pages", "all")), "_cropped", "cropped.zip")


def h_flatten(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.flatten(p, d, o.get("mode") == "rasterize", int(o.get("dpi", 200))),
                    "_flattened", "flattened.zip")


def h_metadata(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.set_metadata(
        p, d, o.get("title", ""), o.get("author", ""), o.get("subject", ""), o.get("keywords", ""), bool(o.get("clear"))),
        "_metadata", "metadata.zip")


def h_protect(ctx: Ctx) -> Path:
    o = ctx.options
    if o.get("password") != o.get("confirm"):
        raise ToolError("The passwords don't match.")
    return _per_pdf(ctx, lambda p, d, n: ops.protect(
        p, d, o.get("password", ""), o.get("owner_password", ""), o.get("allow_print", True), o.get("allow_copy", True),
        o.get("allow_modify", False)), "_protected", "protected.zip")


def h_unlock(ctx: Ctx) -> Path:
    o = ctx.options
    outs = []
    for f in ctx.inputs:
        outs.append(ops.unlock(f.path, ctx.out(f"{stem(f.name)}_unlocked.pdf"), o.get("password", "")))
    return _single_or_zip(ctx, outs, "unlocked.zip")


def h_redact(ctx: Ctx) -> Path:
    o = ctx.options
    notes = []

    def fn(p, d, n):
        out, note = ops.redact(p, d, o.get("terms", ""), o.get("patterns") or [], bool(o.get("case_sensitive")),
                               o.get("color", "#000000"), keep_searchable=bool(o.get("keep_searchable", True)))
        notes.append(note)
        return out
    out = _per_pdf(ctx, fn, "_redacted", "redacted.zip")
    ctx.message = " ".join(notes)
    return out


def h_sanitize(ctx: Ctx) -> Path:
    o = ctx.options
    return _per_pdf(ctx, lambda p, d, n: ops.sanitize(
        p, d, o.get("metadata", True), o.get("javascript", True), o.get("attachments", True), o.get("links", False),
        o.get("forms", False), o.get("hidden_text", False)), "_sanitized", "sanitized.zip")


def h_compare(ctx: Ctx) -> Path:
    if len(ctx.inputs) != 2:
        raise ToolError("Upload exactly two documents to compare.")
    pdfs = ctx.pdfs(0, 0.4)
    dst, note = ops.compare(pdfs[0][0], pdfs[1][0], ctx.out("comparison.pdf"))
    ctx.message = note
    return dst


# --------------------------------------------------------------------------- Studio: the multi-step workflow

STUDIO_STEPS = {"compress", "ocr", "rotate", "watermark", "page_numbers", "header_footer", "flatten", "sanitize",
                "grayscale", "remove_pages", "protect"}


def h_studio(ctx: Ctx) -> Path:
    o = ctx.options
    raw = o.get("steps") or "[]"
    steps = json.loads(raw) if isinstance(raw, str) else raw
    fmt = o.get("format", "pdf")
    pdfs = ctx.pdfs(0, 0.35)
    if o.get("merge", True) and len(pdfs) > 1:
        merged = ctx.out("merged.__studio__.pdf")
        ops.merge([(p, stem(n)) for p, n in pdfs], merged, bookmarks=True, normalize=o.get("normalize", "none"))
        name = (o.get("output_name") or "merged").strip() or "merged"
        pdfs = [(merged, name)]
    outputs: list[Path] = []
    notes: list[str] = []
    for fi, (pdf, name) in enumerate(pdfs):
        cur = pdf
        base = stem(name) if not (o.get("output_name") and len(pdfs) == 1) else stem(o["output_name"] + ".x")
        protect_step = None
        for si, step in enumerate(steps):
            op = step.get("op")
            if op not in STUDIO_STEPS:
                continue
            ctx.progress(0.35 + 0.45 * (fi + si / max(len(steps), 1)) / len(pdfs), f"{op.replace('_', ' ').title()}")
            nxt = ctx.out(f"step-{fi}-{si}-{op}.pdf")
            if op == "compress":
                target = float(step.get("target_mb") or 0) if step.get("level") == "target" else 0
                _, note = ops.compress(cur, nxt, step.get("level", "recommended"), target, False)
                notes.append(note if fmt in ("pdf", "pdfa") else f"Compression step: {note}")
            elif op == "grayscale":
                ops._gs_compress(cur, nxt, 300, 0.2, grayscale=True)
            elif op == "ocr":
                ops.ocr(cur, nxt, step.get("languages") or ["eng"], "skip")
            elif op == "rotate":
                ops.rotate(cur, nxt, int(step.get("angle", 90)), step.get("pages", "all"))
            elif op == "watermark":
                ops.watermark(cur, nxt, text=step.get("text", "CONFIDENTIAL"), opacity=float(step.get("opacity", 0.2)),
                              font_size=int(step.get("font_size", 48)), rotation=int(step.get("rotation", 45)),
                              color=step.get("color", "#d32f2f"), mosaic=bool(step.get("mosaic")))
            elif op == "page_numbers":
                ops.page_numbers(cur, nxt, step.get("position", "bottom-center"), step.get("format", "Page {n} of {total}"))
            elif op == "header_footer":
                ops.header_footer(cur, nxt, step.get("header", ""), step.get("footer", ""))
            elif op == "remove_pages":
                total = ops.page_count(cur)
                remove = set(parse_pages(step.get("pages", ""), total))
                ops.select_pages(cur, nxt, [i for i in range(total) if i not in remove] or [0])
            elif op == "flatten":
                ops.flatten(cur, nxt)
            elif op == "sanitize":
                ops.sanitize(cur, nxt)
            elif op == "protect":
                protect_step = step
                continue
            cur = nxt
        ctx.progress(0.82, f"Exporting {F.FORMATS.get(fmt, (fmt,))[0]}")
        produced = cv.from_pdf(cur, fmt, ctx.workdir, base, o)
        if protect_step and fmt in ("pdf", "pdfa"):
            locked = ctx.out(f"{base}_protected.pdf")
            ops.protect(produced[0], locked, protect_step.get("password", ""))
            produced = [locked]
        elif protect_step:
            notes.append("Password protection applies to PDF output only and was skipped.")
        outputs += produced
    ctx.message = " ".join(dict.fromkeys(n for n in notes if n))
    return _single_or_zip(ctx, outputs, f"{stem(pdfs[0][1])}_{fmt}.zip")


# --------------------------------------------------------------------------- registry

PAGES_HELP = "Examples: 1-3, 5, 8-last · odd · even"

TOOLS: list[Tool] = [
    Tool("studio", "Document Studio", "Drop in any mix of documents, merge them in your order, apply steps like compression, OCR or watermarking, and export to the format you need.",
         "workflow", "workflow", h_studio, accept=ANY, multiple=True, ui="studio", cta="Run workflow", badge="Flagship",
         keywords="workflow pipeline merge convert compress any batch automate",
         options=[
             Option("merge", "Merge into one document", "checkbox", True),
             Option("format", "Output format", "select", "pdf", DOC_FORMAT_CHOICES),
             Option("output_name", "Output file name", "text", "", placeholder="merged"),
             Option("normalize", "Page size", "select", "none", ch("none", "Keep original sizes", "a4", "Make all A4", "letter", "Make all Letter", "first", "Match first page")),
             Option("steps", "Steps", "text", "[]"),
             Option("dpi", "Image resolution (DPI)", "number", 150, min=72, max=600, show_if={"format": ["jpg", "png", "webp", "tiff"]}),
         ]),
    Tool("convert", "Universal Converter", "Convert anything to anything: documents, PDFs, images (JPG, PNG, WebP, HEIC, SVG, ICO…), audio, video and data files — 175 formats, 2,600+ combinations.",
         "workflow", "convert", h_universal, accept=ANY, multiple=True, cta="Convert", badge="New", ui="convert",
         keywords="any to any convert format docx pptx xlsx epub markdown html jpg png webp svg ico heic mp4 mp3 gif csv json",
         options=[
             Option("format", "Convert to", "select", "pdf", FORMAT_CHOICES),
             Option("merge", "Combine all files into one output", "checkbox", False),
             Option("quality", "Quality", "range", 88, min=30, max=100, step=1,
                    show_if={"format": ["jpg", "webp", "avif"]}),
             Option("width", "Resize width (px, optional)", "number", None, min=1, max=20000,
                    show_if={"format": ["jpg", "png", "webp", "avif", "gif", "bmp", "tiff"]}),
             Option("svg_mode", "SVG method", "select", "trace", ch("trace", "Trace into vector paths", "embed", "Wrap image (exact pixels)"),
                    show_if={"format": ["svg"]}),
             Option("svg_detail", "Trace detail", "select", "medium", ch("low", "Low", "medium", "Medium", "high", "High"),
                    show_if={"svg_mode": ["trace"], "format": ["svg"]}),
             Option("dpi", "Page image resolution (DPI)", "number", 150, min=72, max=600, show_if={"format": ["jpg", "png", "webp", "tiff"]}),
             Option("quality_av", "Media quality", "select", "medium", ch(*QUALITY),
                    show_if={"format": ["mp4", "webm", "mov", "mkv", "avi", "mp3", "ogg", "opus", "m4a"]}),
             Option("auto_ocr", "Recognise text in scanned pages", "checkbox", True,
                    show_if={"format": ["docx", "odt", "rtf", "xlsx", "csv", "txt", "md", "html", "epub"]}),
         ]),

    # Organise
    Tool("merge-pdf", "Merge PDF", "Combine PDFs — and Word, Excel, PowerPoint or image files — into one PDF, in the order you want.",
         "organize", "merge", h_merge, accept=ANY, multiple=True, min_files=2, cta="Merge files", keywords="combine join append",
         options=[
             Option("bookmarks", "Add a bookmark for each file", "checkbox", True),
             Option("normalize", "Page size", "select", "none", ch("none", "Keep original sizes", "a4", "Make all A4", "letter", "Make all Letter", "first", "Match first page")),
         ]),
    Tool("split-pdf", "Split PDF", "Separate one page or a whole set into independent PDF files.", "organize", "split", h_split,
         cta="Split PDF", keywords="separate divide break",
         options=[
             Option("mode", "Split mode", "select", "ranges", ch("ranges", "By page ranges", "every", "Every N pages", "all", "Every page")),
             Option("ranges", "Page ranges", "text", "1-1", placeholder="1-3, 4-6, 7-last", help="One PDF per range.", show_if={"mode": ["ranges"]}),
             Option("merge_output", "Merge all ranges into one PDF", "checkbox", False, show_if={"mode": ["ranges"]}),
             Option("every", "Pages per file", "number", 1, min=1, max=1000, show_if={"mode": ["every"]}),
         ]),
    Tool("remove-pages", "Remove Pages", "Delete the pages you don't need from a PDF.", "organize", "remove", h_remove_pages,
         cta="Remove pages", keywords="delete pages", options=[Option("pages", "Pages to remove", "pages", "", help=PAGES_HELP, placeholder="2, 5-7")]),
    Tool("extract-pages", "Extract Pages", "Pull selected pages out into a new PDF.", "organize", "extract", h_extract_pages,
         cta="Extract pages", options=[
             Option("pages", "Pages to extract", "pages", "1", help=PAGES_HELP, placeholder="1-3, 8"),
             Option("separate", "Save each page as a separate PDF", "checkbox", False)]),
    Tool("organize-pdf", "Organize PDF", "Drag to reorder pages, rotate, delete or add blank pages — visually.", "organize", "organize",
         h_organize, ui="organize", cta="Save changes", keywords="reorder sort rearrange pages delete insert blank",
         options=[Option("layout", "Layout", "text", "")]),
    Tool("rotate-pdf", "Rotate PDF", "Rotate all or selected pages. Rotate many PDFs at once.", "organize", "rotate", h_rotate,
         multiple=True, cta="Rotate", options=[
             Option("angle", "Rotation", "select", "90", ch("90", "90° clockwise", "180", "180°", "270", "90° counter-clockwise")),
             Option("pages", "Pages", "pages", "all", help=PAGES_HELP)]),

    # Optimise
    Tool("compress-pdf", "Compress PDF", "Reduce file size while keeping the best possible quality — or hit an exact target size.",
         "optimize", "compress", h_compress, multiple=True, cta="Compress", keywords="reduce shrink smaller size optimize",
         options=[
             Option("level", "Compression", "select", "recommended", ch(
                 "light", "Light — best quality", "recommended", "Recommended — great quality, small size",
                 "strong", "Strong — smaller file", "extreme", "Extreme — smallest file", "target", "Target size (MB)")),
             Option("target_mb", "Target size in MB", "number", 1, min=0.05, max=500, step=0.05, show_if={"level": ["target"]},
                    help="Great for upload limits on job portals and government forms."),
             Option("grayscale", "Convert to grayscale", "checkbox", False),
         ]),
    Tool("repair-pdf", "Repair PDF", "Recover data from damaged or corrupt PDF files.", "optimize", "repair", h_repair, multiple=True, cta="Repair"),
    Tool("ocr-pdf", "OCR PDF", "Turn scanned PDFs and photos into searchable, selectable documents — 28 languages including Hindi, Tamil, Bengali and other Indian scripts.", "optimize", "ocr",
         h_ocr, accept=PDF + IMAGES, multiple=True, cta="Recognise text", keywords="scan text recognition searchable",
         options=[
             Option("languages", "Document languages", "multiselect", ["eng"], []),
             Option("mode", "Pages that already have text", "select", "skip", ch("skip", "Skip them", "force", "Re-OCR everything (rasterise)", "redo", "Replace old OCR layer")),
             Option("deskew", "Straighten crooked scans", "checkbox", True),
             Option("rotate_pages", "Fix upside-down pages", "checkbox", True),
             Option("clean", "Clean scan noise", "checkbox", False),
             Option("output", "Output", "select", "pdf", ch("pdf", "Searchable PDF", "pdfa", "Searchable PDF/A", "txt", "Plain text (.txt)")),
         ]),
    Tool("pdf-to-pdfa", "PDF to PDF/A", "Convert to PDF/A, the ISO standard for long-term archiving.", "optimize", "archive", h_pdfa,
         multiple=True, cta="Convert to PDF/A", options=[Option("level", "Conformance", "select", "2", ch("1", "PDF/A-1b", "2", "PDF/A-2b (recommended)", "3", "PDF/A-3b"))]),

    # Convert to PDF
    Tool("word-to-pdf", "Word to PDF", "Convert DOC, DOCX, ODT, RTF, TXT and Pages files to PDF.", "to-pdf", "word", h_to_pdf,
         accept=WORD, multiple=True, cta="Convert to PDF", options=[Option("merge", "Combine into one PDF", "checkbox", False)]),
    Tool("powerpoint-to-pdf", "PowerPoint to PDF", "Convert PPT, PPTX, ODP and Keynote presentations to PDF.", "to-pdf", "powerpoint",
         h_to_pdf, accept=PPT, multiple=True, cta="Convert to PDF", options=[Option("merge", "Combine into one PDF", "checkbox", False)]),
    Tool("excel-to-pdf", "Excel to PDF", "Convert XLS, XLSX, ODS, CSV and Numbers spreadsheets to PDF.", "to-pdf", "excel", h_to_pdf,
         accept=EXCEL, multiple=True, cta="Convert to PDF", options=[Option("merge", "Combine into one PDF", "checkbox", False)]),
    Tool("jpg-to-pdf", "Image to PDF", "Convert JPG, PNG, HEIC (iPhone), WebP, TIFF and more to PDF. Adjust orientation and margins.",
         "to-pdf", "image", h_images_to_pdf, accept=IMAGES, multiple=True, cta="Convert to PDF", keywords="jpg png heic photo picture scan",
         options=[
             Option("page_size", "Page size", "select", "fit", ch("fit", "Same as image", "a4", "A4", "letter", "US Letter", "legal", "Legal")),
             Option("orientation", "Orientation", "select", "auto", ch("auto", "Automatic", "portrait", "Portrait", "landscape", "Landscape"), show_if={"page_size": ["a4", "letter", "legal"]}),
             Option("margin", "Margin", "select", "none", ch("none", "No margin", "small", "Small", "big", "Big"), show_if={"page_size": ["a4", "letter", "legal"]}),
             Option("merge", "Put all images in one PDF", "checkbox", True),
         ]),
    Tool("html-to-pdf", "HTML to PDF", "Convert any web page (by URL) or HTML file to a pixel-perfect PDF.", "to-pdf", "html", h_html_to_pdf,
         accept=["html", "htm"], ui="url", min_files=0, cta="Convert to PDF", keywords="web page url website",
         options=[
             Option("url", "Web address", "text", "", placeholder="https://example.com"),
             Option("page_size", "Page size", "select", "A4", ch("A4", "A4", "LETTER", "US Letter", "A3", "A3", "FIT", "One long page")),
             Option("landscape", "Landscape", "checkbox", False),
             Option("margin", "Margin", "select", "small", ch("none", "None", "small", "Small", "normal", "Normal")),
             Option("screen_css", "Use screen layout (as seen in browser)", "checkbox", True),
         ]),
    Tool("any-to-pdf", "Anything to PDF", "Markdown, e-books (EPUB), e-mails (EML), code, SVG, Visio, Publisher, Apple iWork… if it's a document, it becomes a PDF.",
         "to-pdf", "file", h_to_pdf, accept=ANY, multiple=True, cta="Convert to PDF", keywords="markdown epub eml email code svg visio",
         options=[Option("merge", "Combine into one PDF", "checkbox", False)]),

    # Convert from PDF
    Tool("pdf-to-word", "PDF to Word", "Convert PDFs to editable DOCX documents with layout, tables and images preserved.", "from-pdf", "word",
         _from_pdf_tool("docx"), multiple=True, cta="Convert to Word", options=[
             Option("auto_ocr", "Recognise text in scanned pages", "checkbox", True)]),
    Tool("pdf-to-powerpoint", "PDF to PowerPoint", "Turn PDFs into PPTX slideshows with editable text.", "from-pdf", "powerpoint",
         _from_pdf_tool("pptx"), multiple=True, cta="Convert to PowerPoint", options=[
             Option("editable", "Editable text (uncheck for exact images)", "checkbox", True)]),
    Tool("pdf-to-excel", "PDF to Excel", "Pull tables straight from PDFs into Excel spreadsheets.", "from-pdf", "excel",
         _from_pdf_tool(None), multiple=True, cta="Convert to Excel", options=[
             Option("format", "Format", "select", "xlsx", ch("xlsx", "Excel workbook (.xlsx)", "csv", "CSV (one file per table)")),
             Option("auto_ocr", "Recognise text in scanned pages", "checkbox", True)]),
    Tool("pdf-to-jpg", "PDF to Image", "Convert each page to JPG, PNG or WebP, or extract all images inside a PDF.", "from-pdf", "image",
         h_pdf_to_images, multiple=True, cta="Convert to images", keywords="jpg png webp tiff picture",
         options=[
             Option("mode", "Mode", "select", "pages", ch("pages", "Convert every page", "extract", "Extract embedded images")),
             Option("image_format", "Image format", "select", "jpg", ch("jpg", "JPG", "png", "PNG", "webp", "WebP", "tiff", "Multi-page TIFF"), show_if={"mode": ["pages"]}),
             Option("dpi", "Quality", "select", "150", ch("72", "Low (72 DPI)", "150", "Normal (150 DPI)", "300", "High (300 DPI)", "600", "Print (600 DPI)"), show_if={"mode": ["pages"]}),
         ]),
    Tool("pdf-to-text", "PDF to Text", "Extract all text from a PDF to a plain-text, Markdown, HTML or EPUB file.", "from-pdf", "text",
         _from_pdf_tool(None), multiple=True, cta="Extract text", keywords="txt markdown html epub",
         options=[
             Option("format", "Format", "select", "txt", ch("txt", "Plain text (.txt)", "md", "Markdown (.md)", "html", "HTML page", "epub", "EPUB e-book", "odt", "OpenDocument (.odt)", "rtf", "Rich text (.rtf)")),
             Option("auto_ocr", "Recognise text in scanned pages", "checkbox", True)]),
    Tool("pdf-to-svg", "PDF to SVG", "Turn every PDF page into a crisp, scalable SVG vector graphic.", "from-pdf", "vector",
         _from_pdf_tool("svg"), multiple=True, cta="Convert to SVG", keywords="vector svg illustrator figma"),

    # Images
    Tool("image-converter", "Image Converter", "Convert between JPG, PNG, WebP, AVIF, HEIC, GIF, BMP, TIFF, ICO and SVG — in bulk, with optional resizing.",
         "image", "image", h_image_convert, accept=IMAGES, multiple=True, cta="Convert images", badge="New",
         keywords="jpg png webp avif heic gif bmp tiff ico svg convert photo",
         options=[
             Option("format", "Convert to", "select", "png", [c for c in FORMAT_CHOICES if F.FORMATS[c["value"]][1] == "image"] + [{"value": "pdf", "label": "PDF"}]),
             Option("quality", "Quality", "range", 88, min=30, max=100, step=1, show_if={"format": ["jpg", "webp", "avif"]}),
             Option("width", "Width (px, optional)", "number", None, min=1, max=20000, show_if={"format": ["jpg", "png", "webp", "avif", "gif", "bmp", "tiff"]}),
             Option("height", "Height (px, optional)", "number", None, min=1, max=20000, show_if={"format": ["jpg", "png", "webp", "avif", "gif", "bmp", "tiff"]}),
             Option("background", "Background for transparent areas", "color", "#ffffff", show_if={"format": ["jpg", "bmp"]}),
             Option("ico_sizes", "Icon sizes", "multiselect", ["16", "32", "48", "64", "128", "256"], ch("16", "16", "24", "24", "32", "32", "48", "48", "64", "64", "128", "128", "256", "256"), show_if={"format": ["ico"]}),
             Option("svg_mode", "SVG method", "select", "trace", ch("trace", "Trace into vector paths", "embed", "Wrap image (exact pixels)"), show_if={"format": ["svg"]}),
             Option("svg_detail", "Trace detail", "select", "medium", ch("low", "Low", "medium", "Medium", "high", "High"), show_if={"svg_mode": ["trace"], "format": ["svg"]}),
         ]),
    Tool("compress-image", "Compress Image", "Shrink JPG, PNG, WebP and HEIC photos — or hit an exact size like 50 KB or 200 KB for forms and portals.",
         "image", "compress", h_image_compress, accept=RASTER, multiple=True, cta="Compress images",
         keywords="reduce image size kb photo compress jpg png 50kb 100kb 200kb",
         options=[
             Option("mode", "Mode", "select", "quality", ch("quality", "By quality", "target", "Target size (KB)")),
             Option("quality", "Quality", "range", 75, min=10, max=95, step=1, show_if={"mode": ["quality"]}),
             Option("target_kb", "Target size in KB", "number", 200, min=5, max=50000, show_if={"mode": ["target"]}),
             Option("max_side", "Limit longest side (px, optional)", "number", None, min=16, max=20000),
             Option("output", "Output format", "select", "same", ch("same", "Keep format", "jpg", "JPG", "webp", "WebP", "png", "PNG", "avif", "AVIF")),
         ]),
    Tool("resize-image", "Resize & Rotate Image", "Resize by pixels or percentage, rotate, flip or make images grayscale — many at once.",
         "image", "resize", h_image_edit, accept=RASTER, multiple=True, cta="Apply", keywords="resize scale rotate flip grayscale dimensions",
         options=[
             Option("resize_mode", "Resize", "select", "pixels", ch("none", "Don't resize", "pixels", "By pixels", "percent", "By percentage")),
             Option("width", "Width (px)", "number", 1280, min=1, max=20000, show_if={"resize_mode": ["pixels"]}),
             Option("height", "Height (px, optional)", "number", None, min=1, max=20000, show_if={"resize_mode": ["pixels"]}),
             Option("fit", "Fit", "select", "contain", ch("contain", "Keep aspect ratio", "cover", "Fill and crop", "stretch", "Stretch"), show_if={"resize_mode": ["pixels"]}),
             Option("percent", "Percentage", "number", 50, min=1, max=1000, show_if={"resize_mode": ["percent"]}),
             Option("rotate", "Rotate", "select", "0", ch("0", "No rotation", "90", "90° clockwise", "180", "180°", "270", "90° counter-clockwise")),
             Option("flip", "Flip", "select", "none", ch("none", "No flip", "horizontal", "Horizontal", "vertical", "Vertical")),
             Option("grayscale", "Convert to grayscale", "checkbox", False),
         ]),
    Tool("image-to-svg", "Image to SVG", "Vectorise logos, icons and drawings into clean, scalable SVG paths.", "image", "vector",
         h_image_svg, accept=RASTER, multiple=True, cta="Vectorise", keywords="vectorize trace svg logo png to svg jpg to svg",
         options=[
             Option("svg_colors", "Colours", "select", "color", ch("color", "Full colour", "bw", "Black & white")),
             Option("svg_detail", "Detail", "select", "medium", ch("low", "Low (smallest file)", "medium", "Medium", "high", "High (most detail)")),
         ]),
    Tool("favicon-generator", "Favicon Generator", "Create favicon.ico, Apple and Android icons and a web manifest from any logo.",
         "image", "favicon", h_favicon, accept=IMAGES, cta="Generate favicons", keywords="favicon ico apple touch icon manifest website",
         options=[Option("site_name", "Website name", "text", "", placeholder="My Site"),
                  Option("color", "Theme colour", "color", "#0f766e")]),
    Tool("remove-image-metadata", "Remove Photo Metadata", "Strip GPS location, camera and date details (EXIF) from photos before you share them.",
         "image", "shield", h_strip_exif, accept=RASTER, multiple=True, cta="Clean photos", keywords="exif gps location privacy metadata"),
    Tool("html-to-image", "Website Screenshot", "Capture any web page or HTML file as a full-length PNG, JPG or WebP image.",
         "image", "screenshot", h_html_to_image, accept=["html", "htm"], ui="url", min_files=0, cta="Capture",
         keywords="screenshot website capture url to image html to png",
         options=[
             Option("url", "Web address", "text", "", placeholder="https://example.com"),
             Option("format", "Format", "select", "png", ch("png", "PNG", "jpg", "JPG", "webp", "WebP")),
             Option("width", "Browser width (px)", "number", 1440, min=320, max=3840),
             Option("full_page", "Capture the full page", "checkbox", True),
         ]),

    # Audio & video
    Tool("video-converter", "Video Converter", "Convert MP4, MOV, MKV, WebM, AVI and more — change resolution, trim, or mute.",
         "media", "video", _media_tool(), accept=VIDEO + ["gif"], multiple=True, cta="Convert video",
         keywords="mp4 mov mkv webm avi convert video",
         options=[
             Option("format", "Convert to", "select", "mp4", ch("mp4", "MP4 (H.264)", "webm", "WebM (VP9)", "mov", "MOV", "mkv", "MKV", "avi", "AVI", "gif", "Animated GIF")),
             Option("resolution", "Resolution", "select", "", ch(*RESOLUTION), show_if={"format": ["mp4", "webm", "mov", "mkv", "avi"]}),
             Option("quality", "Quality", "select", "medium", ch(*QUALITY), show_if={"format": ["mp4", "webm", "mov", "mkv", "avi"]}),
             Option("start", "Start time (optional)", "text", "", placeholder="00:00:05"),
             Option("end", "End time (optional)", "text", "", placeholder="00:01:30"),
             Option("mute", "Remove audio", "checkbox", False, show_if={"format": ["mp4", "webm", "mov", "mkv", "avi"]}),
         ]),
    Tool("audio-converter", "Audio Converter", "Convert MP3, WAV, FLAC, OGG, M4A, Opus and more, or pull the audio out of a video.",
         "media", "audio", _media_tool(), accept=AUDIO + VIDEO, multiple=True, cta="Convert audio",
         keywords="mp3 wav flac ogg m4a aac opus convert audio extract",
         options=[
             Option("format", "Convert to", "select", "mp3", ch("mp3", "MP3", "wav", "WAV", "flac", "FLAC (lossless)", "m4a", "M4A (AAC)", "ogg", "OGG Vorbis", "opus", "Opus")),
             Option("quality", "Quality", "select", "medium", ch(*QUALITY), show_if={"format": ["mp3", "m4a", "ogg", "opus"]}),
             Option("start", "Start time (optional)", "text", "", placeholder="00:00:00"),
             Option("end", "End time (optional)", "text", "", placeholder="00:03:00"),
         ]),
    Tool("video-to-gif", "Video to GIF", "Turn a video clip into a smooth, optimised animated GIF.", "media", "gif",
         _media_tool(fixed="gif"), accept=VIDEO, cta="Make GIF", keywords="gif maker video to gif mp4 to gif",
         options=[
             Option("start", "Start time", "text", "00:00:00", placeholder="00:00:00"),
             Option("end", "End time", "text", "00:00:05", placeholder="00:00:05"),
             Option("fps", "Frames per second", "number", 12, min=1, max=30),
             Option("gif_width", "Width (px)", "number", 480, min=80, max=1280),
         ]),
    Tool("compress-video", "Compress Video", "Make videos much smaller for WhatsApp, e-mail and uploads while keeping them sharp.",
         "media", "compress", h_compress_video, accept=VIDEO, multiple=True, cta="Compress video",
         keywords="reduce video size compress mp4 whatsapp email",
         options=[
             Option("level", "Compression", "select", "medium", ch("light", "Light — best quality", "medium", "Balanced", "strong", "Strong — smallest file")),
             Option("resolution", "Resolution", "select", "", ch(*RESOLUTION)),
         ]),
    Tool("data-converter", "CSV / Excel / JSON Converter", "Convert spreadsheets and data between CSV, Excel, JSON, HTML and Markdown tables.",
         "to-pdf", "data", h_data_convert, accept=TABLES, multiple=True, cta="Convert data", keywords="csv xlsx json excel table convert",
         options=[Option("format", "Convert to", "select", "xlsx", ch("xlsx", "Excel (.xlsx)", "csv", "CSV", "json", "JSON", "html", "HTML table", "md", "Markdown table", "pdf", "PDF"))]),

    # Edit
    Tool("add-watermark", "Watermark", "Stamp text or an image over your PDF. Choose font, transparency, angle and position.", "edit",
         "watermark", h_watermark, multiple=True, cta="Add watermark",
         extra_files=[ExtraFile("image", "Watermark image", IMAGES, required=False)],
         options=[
             Option("kind", "Type", "select", "text", ch("text", "Text", "image", "Image")),
             Option("text", "Text", "text", "CONFIDENTIAL", show_if={"kind": ["text"]}),
             Option("font_size", "Font size", "number", 48, min=6, max=300, show_if={"kind": ["text"]}),
             Option("color", "Colour", "color", "#d32f2f", show_if={"kind": ["text"]}),
             Option("image_scale", "Image size (fraction of page width)", "range", 0.4, min=0.05, max=1, step=0.05, show_if={"kind": ["image"]}),
             Option("opacity", "Transparency", "range", 0.3, min=0.05, max=1, step=0.05),
             Option("rotation", "Rotation (degrees)", "number", 45, min=-180, max=180),
             Option("position", "Position", "position", "center", POSITION_CHOICES),
             Option("mosaic", "Repeat across the page (mosaic)", "checkbox", False),
             Option("layer", "Layer", "select", "over", ch("over", "Over the content", "under", "Behind the content")),
             Option("pages", "Pages", "pages", "all", help=PAGES_HELP),
         ]),
    Tool("page-numbers", "Page Numbers", "Add page numbers with your choice of position, format and typography.", "edit", "numbers",
         h_page_numbers, multiple=True, cta="Add page numbers",
         options=[
             Option("position", "Position", "position", "bottom-center", POSITION_CHOICES),
             Option("format", "Format", "select", "n", ch("n", "1", "page_n", "Page 1", "n_of_total", "1 / 10", "page_n_of_total", "Page 1 of 10", "custom", "Custom")),
             Option("custom", "Custom text", "text", "{n}", help="Use {n} for the page number and {total} for the page count.", show_if={"format": ["custom"]}),
             Option("start", "First number", "number", 1, min=0, max=100000),
             Option("font_size", "Font size", "number", 11, min=5, max=72),
             Option("color", "Colour", "color", "#333333"),
             Option("margin", "Distance from edge (pt)", "number", 28, min=0, max=200),
             Option("skip_first", "Don't number the first page (cover)", "checkbox", False),
             Option("pages", "Pages", "pages", "all", help=PAGES_HELP),
         ]),
    Tool("header-footer", "Header & Footer", "Add a header and footer text to every page.", "edit", "header", h_header_footer, multiple=True,
         cta="Apply", options=[
             Option("header", "Header", "text", "", placeholder="Company — Confidential"),
             Option("footer", "Footer", "text", "Page {n} of {total}"),
             Option("align", "Alignment", "select", "center", ch("left", "Left", "center", "Centre", "right", "Right")),
             Option("font_size", "Font size", "number", 10, min=5, max=48),
             Option("color", "Colour", "color", "#444444")]),
    Tool("sign-pdf", "Sign PDF", "Draw, type or upload your signature and place it exactly where it belongs.", "edit", "sign", h_sign,
         ui="sign", cta="Sign document", keywords="signature esign",
         extra_files=[ExtraFile("signature", "Signature", ["png", "jpg", "jpeg", "webp"], required=True)],
         options=[
             Option("pages", "Pages", "pages", "last", help="first, last, all, or e.g. 1-3"),
             Option("x", "X", "number", 0.62), Option("y", "Y", "number", 0.82), Option("width", "Width", "number", 0.28)]),
    Tool("crop-pdf", "Crop PDF", "Trim white margins automatically or crop to exact measurements.", "edit", "crop", h_crop,
         multiple=True, cta="Crop", options=[
             Option("mode", "Mode", "select", "auto", ch("auto", "Auto-trim white margins", "manual", "Custom margins (mm)")),
             Option("top", "Top (mm)", "number", 10, min=0, max=500, show_if={"mode": ["manual"]}),
             Option("right", "Right (mm)", "number", 10, min=0, max=500, show_if={"mode": ["manual"]}),
             Option("bottom", "Bottom (mm)", "number", 10, min=0, max=500, show_if={"mode": ["manual"]}),
             Option("left", "Left (mm)", "number", 10, min=0, max=500, show_if={"mode": ["manual"]}),
             Option("pages", "Pages", "pages", "all", help=PAGES_HELP)]),
    Tool("flatten-pdf", "Flatten PDF", "Make form fields and annotations a permanent part of the page.", "edit", "flatten", h_flatten,
         multiple=True, cta="Flatten", options=[
             Option("mode", "Method", "select", "forms", ch("forms", "Flatten forms & annotations (keeps text)", "rasterize", "Print as image (nothing editable)")),
             Option("dpi", "Image quality (DPI)", "number", 200, min=72, max=600, show_if={"mode": ["rasterize"]})]),
    Tool("edit-metadata", "Edit Metadata", "Change or remove the title, author, subject and keywords.", "edit", "info", h_metadata,
         multiple=True, cta="Save metadata", options=[
             Option("title", "Title", "text", ""), Option("author", "Author", "text", ""),
             Option("subject", "Subject", "text", ""), Option("keywords", "Keywords", "text", ""),
             Option("clear", "Remove all existing metadata first", "checkbox", False)]),

    # Security
    Tool("protect-pdf", "Protect PDF", "Encrypt your PDF with a password using AES-256 and control printing and copying.", "security",
         "lock", h_protect, multiple=True, cta="Protect PDF", keywords="password encrypt",
         options=[
             Option("password", "Password", "password", ""), Option("confirm", "Repeat password", "password", ""),
             Option("allow_print", "Allow printing", "checkbox", True), Option("allow_copy", "Allow copying text", "checkbox", True),
             Option("allow_modify", "Allow editing", "checkbox", False),
             Option("owner_password", "Owner password (optional)", "password", "", help="Lets you change permissions later.")]),
    Tool("unlock-pdf", "Unlock PDF", "Remove password protection and restrictions from PDFs you own.", "security", "unlock", h_unlock,
         multiple=True, cta="Unlock PDF", keywords="remove password decrypt",
         options=[Option("password", "Password (if the PDF needs one to open)", "password", "")]),
    Tool("redact-pdf", "Redact PDF", "Permanently remove sensitive text — names, e-mails, phone numbers, card, Aadhaar and PAN numbers.",
         "security", "redact", h_redact, multiple=True, cta="Redact", keywords="black out censor remove sensitive gdpr",
         options=[
             Option("terms", "Words or phrases", "textarea", "", placeholder="One per line or comma-separated"),
             Option("patterns", "Also find", "multiselect", [], ch("email", "E-mail addresses", "phone", "Phone numbers", "card", "Card numbers",
                                                                 "url", "Web links", "date", "Dates", "iban", "IBAN", "ssn", "US SSN",
                                                                 "aadhaar", "Aadhaar numbers", "pan", "PAN numbers")),
             Option("case_sensitive", "Match case", "checkbox", False),
             Option("keep_searchable", "Keep the rest of the page searchable (OCR)", "checkbox", True),
             Option("color", "Box colour", "color", "#000000")]),
    Tool("sanitize-pdf", "Sanitize PDF", "Strip hidden metadata, JavaScript, attachments and other risky content before sharing.",
         "security", "shield", h_sanitize, multiple=True, cta="Sanitize", keywords="clean metadata privacy javascript",
         options=[
             Option("metadata", "Remove metadata", "checkbox", True), Option("javascript", "Remove JavaScript", "checkbox", True),
             Option("attachments", "Remove attachments", "checkbox", True), Option("links", "Remove links", "checkbox", False),
             Option("forms", "Reset form fields", "checkbox", False), Option("hidden_text", "Remove hidden text", "checkbox", False)]),

    # Intelligence
    Tool("compare-pdf", "Compare PDF", "See a side-by-side comparison with every added and removed word highlighted.", "intelligence",
         "compare", h_compare, accept=ANY, multiple=True, min_files=2, max_files=2, ui="compare", cta="Compare", keywords="diff difference versions"),
    Tool("pdf-to-markdown", "PDF to Markdown", "Turn PDFs into clean Markdown — headings, lists and tables preserved. Perfect for notes and AI tools.",
         "intelligence", "markdown", _from_pdf_tool("md"), multiple=True, cta="Convert to Markdown", badge="New",
         keywords="llm ai chatgpt md", options=[Option("auto_ocr", "Recognise text in scanned pages", "checkbox", True)]),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}


TEXT_LIMITS = {"text": 2000, "textarea": 20000, "password": 256, "pages": 500, "color": 9, "position": 20}
MAX_STEPS, MAX_LAYOUT = 25, 20000


def _json_list(value: Any, limit: int, label: str) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        if len(value) > 1_000_000:
            raise ToolError(f"The {label} is too large.")
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ToolError(f"The {label} is not valid.") from exc
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, dict) for v in value):
        raise ToolError(f"The {label} is not valid.")
    return value


def coerce_options(tool: Tool, raw: dict) -> dict:
    """Validate user options strictly against the tool schema: known keys only, values of the declared type,
    numbers clamped to their range, choices restricted to the allowed list, text length-limited."""
    out: dict[str, Any] = {}
    for opt in tool.options:
        val = raw.get(opt.id, opt.default)
        allowed = {str(c["value"]) for c in opt.choices} if opt.choices else None
        try:
            if opt.id in ("steps", "layout"):
                val = json.dumps(_json_list(val, MAX_STEPS if opt.id == "steps" else MAX_LAYOUT, opt.id))
            elif opt.type == "checkbox":
                val = val if isinstance(val, bool) else str(val).lower() in ("1", "true", "on", "yes")
            elif opt.type in ("number", "range"):
                val = float(val) if val not in (None, "") else opt.default
                if val is not None:
                    if val != val or val in (float("inf"), float("-inf")):  # NaN / infinity
                        val = opt.default
                    else:
                        if opt.min is not None:
                            val = max(opt.min, val)
                        if opt.max is not None:
                            val = min(opt.max, val)
            elif opt.type == "multiselect":
                items = val if isinstance(val, list) else [v for v in str(val or "").split(",") if v]
                items = [str(v)[:40] for v in items][:100]
                val = [v for v in items if v in allowed] if allowed else items
            elif opt.type in ("select", "position"):
                val = "" if val is None else str(val)
                if allowed is not None and val not in allowed:
                    val = opt.default
            else:
                val = "" if val is None else str(val)[: TEXT_LIMITS.get(opt.type, 2000)]
        except (TypeError, ValueError):
            val = opt.default
        out[opt.id] = val
    return out
