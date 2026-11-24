"""Document conversion.

PDF is the hub format for documents: every document input is normalised to
PDF (``to_pdf``) and every document output is produced from PDF
(``from_pdf``).  That is what lets a user merge a Word file, a photo and a
spreadsheet and get back a PowerPoint.  Images, audio, video and data files
have their own direct converters in ``media`` and ``data``.
"""
from __future__ import annotations

import email
import email.policy
import html
import io
import ipaddress
import shutil
import socket
from pathlib import Path
from collections.abc import Callable
from urllib.parse import urlparse

import httpx
import pikepdf

from . import formats as F
from .config import CONVERTER_URL
from .engine import export, raster
from .util import ToolError, ext_of, run, stem, zip_files

Progress = Callable[[float, str], None]

DOC_CSS = """
body{font-family:'Inter','Segoe UI','Noto Sans','DejaVu Sans',Arial,sans-serif;font-size:11pt;line-height:1.55;color:#1a1a1a;max-width:100%;margin:0}
h1,h2,h3,h4{line-height:1.25;margin:1.2em 0 .5em}h1{font-size:22pt}h2{font-size:17pt}h3{font-size:14pt}
img,svg{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;margin:1em 0;font-size:10pt}
td,th{border:1px solid #cfd4dc;padding:5px 8px;vertical-align:top}th{background:#f2f4f7;text-align:left}
pre,code{font-family:'JetBrains Mono','DejaVu Sans Mono',Consolas,monospace;font-size:9pt}
pre{background:#f6f8fa;border:1px solid #e3e7ed;border-radius:6px;padding:10px;white-space:pre-wrap;word-break:break-word}
blockquote{border-left:4px solid #d0d7e2;margin:1em 0;padding:.2em 1em;color:#4a5363}a{color:#0f766e}
@page{size:A4;margin:18mm 16mm}
"""


# --------------------------------------------------------------------------- conversion service client

def _service(route: str, files: list, data: dict | None, timeout: float = 600) -> bytes:
    # The service only accepts multipart/form-data, so send form fields as multipart parts too.
    parts = list(files) + [(k, (None, str(v))) for k, v in (data or {}).items()]
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=10)) as client:
            resp = client.post(f"{CONVERTER_URL}{route}", files=parts)
    except httpx.HTTPError as exc:
        raise ToolError("The conversion service is unavailable. Please try again in a moment.") from exc
    if resp.status_code != 200:
        msg = resp.text.strip()[:300] or f"HTTP {resp.status_code}"
        raise ToolError(f"Conversion failed: {msg}")
    return resp.content


def office_to_pdf(src: Path, dst: Path, landscape: bool = False) -> Path:
    data = {"landscape": "true"} if landscape else {}
    dst.write_bytes(_service("/forms/libreoffice/convert", [("files", (src.name, src.read_bytes(), "application/octet-stream"))], data))
    return dst


def _paper(opts: dict) -> dict:
    size = (opts.get("page_size") or "A4").upper()
    sizes = {"A4": ("8.27in", "11.7in"), "LETTER": ("8.5in", "11in"), "LEGAL": ("8.5in", "14in"), "A3": ("11.7in", "16.54in")}
    data: dict[str, str] = {"printBackground": "true"}
    if size == "FIT":
        data["singlePage"] = "true"
    else:
        w, h = sizes.get(size, sizes["A4"])
        data.update(paperWidth=w, paperHeight=h)
    margin = {"none": "0", "small": "0.4in", "normal": "0.75in"}.get(opts.get("margin", "small"), "0.4in")
    for side in ("marginTop", "marginBottom", "marginLeft", "marginRight"):
        data[side] = margin
    if opts.get("landscape"):
        data["landscape"] = "true"
    if opts.get("screen_css", True):
        data["emulatedMediaType"] = "screen"
    return data


def html_to_pdf(index_html: Path, dst: Path, assets: list[Path] | None = None, opts: dict | None = None) -> Path:
    from .security import sanitize_html

    files = [("files", ("index.html", sanitize_html(index_html.read_bytes()).encode("utf-8"), "text/html"))]
    for a in assets or []:
        files.append(("files", (a.name, a.read_bytes(), "application/octet-stream")))
    dst.write_bytes(_service("/forms/chromium/convert/html", files, _paper(opts or {"margin": "none", "screen_css": False})))
    return dst


def check_public_url(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    host = urlparse(url).hostname
    if not host:
        raise ToolError("Please enter a valid web address.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ToolError(f"Could not find the website '{host}'.") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ToolError("That address points to a private network and cannot be converted.")
    return url


def url_to_pdf(url: str, dst: Path, opts: dict) -> Path:
    data = _paper(opts)
    data["url"] = check_public_url(url)
    data["waitDelay"] = "1s"
    dst.write_bytes(_service("/forms/chromium/convert/url", [], data))
    return dst


def url_to_image(url: str | None, html_file: Path | None, dst: Path, fmt: str = "png", width: int = 1440,
                 full_page: bool = True, quality: int = 90) -> Path:
    data = {"format": "jpeg" if fmt in ("jpg", "jpeg") else fmt, "width": str(width), "height": "900",
            "clip": "false" if full_page else "true", "waitDelay": "1s"}
    if fmt in ("jpg", "jpeg", "webp"):
        data["quality"] = str(quality)
    if url:
        data["url"] = check_public_url(url)
        content = _service("/forms/chromium/screenshot/url", [], data)
    else:
        from .security import sanitize_html

        page = sanitize_html(html_file.read_bytes()).encode("utf-8")
        content = _service("/forms/chromium/screenshot/html", [("files", ("index.html", page, "text/html"))], data)
    dst.write_bytes(content)
    return dst


def browser_text_pdf(labels: list[str], font_size: float, color: str, opacity: float, bold: bool) -> pikepdf.Pdf:
    """Typeset labels in any script with the browser engine; one tightly-cropped page per label."""
    from .engine.stamp import label_html

    content = _service("/forms/chromium/convert/html",
                       [("files", ("index.html", label_html(labels, font_size, color, opacity, bold).encode(), "text/html"))],
                       {"preferCssPageSize": "true", "printBackground": "true"}, timeout=120)
    doc = raster.open_doc(content)
    boxes = []
    for i in range(len(doc)):
        tp = doc[i].get_textpage()
        rects = [tp.get_rect(k) for k in range(tp.count_rects())]
        tp.close()
        boxes.append(raster.union(rects) if rects else None)
    doc.close()
    pdf = pikepdf.open(io.BytesIO(content))
    keep = []
    for i, page in enumerate(pdf.pages):
        if i >= len(labels):
            break
        b = boxes[i]
        if b is None:
            b = (0, 0, 10, 10)
        pad = font_size * 0.15
        page.obj["/MediaBox"] = pikepdf.Array([max(0, b[0] - pad), b[1] - pad, b[2] + pad, b[3] + pad])
        if "/CropBox" in page.obj:
            del page.obj["/CropBox"]
        keep.append(i)
    while len(pdf.pages) > len(keep):
        del pdf.pages[-1]
    if len(pdf.pages) != len(labels):
        raise ToolError("Could not typeset the text. Try shorter text.")
    return pdf


# --------------------------------------------------------------------------- inputs -> PDF

def images_to_pdf(images: list[Path], dst: Path, page_size: str = "fit", orientation: str = "auto", margin: str = "none") -> Path:
    import img2pdf
    from PIL import Image

    from .media import open_image

    prepared: list[bytes] = []
    for p in images:
        e = ext_of(p.name)
        if e == "svg":
            from .media import svg_to_png

            prepared.append(svg_to_png(p.read_bytes(), 2000))
            continue
        if e in ("jpg", "jpeg", "jfif"):
            with Image.open(p) as im:
                if (im.getexif() or {}).get(274, 1) in (1, None) and im.mode in ("RGB", "L", "CMYK"):
                    prepared.append(p.read_bytes())  # embedded losslessly
                    continue
        for frame in open_image(p, all_frames=e in ("tif", "tiff")):
            if frame.mode in ("RGBA", "LA", "P", "PA"):
                frame = frame.convert("RGBA")
                bg = Image.new("RGB", frame.size, "white")
                bg.paste(frame, mask=frame.getchannel("A"))
                frame = bg
            elif frame.mode not in ("RGB", "L"):
                frame = frame.convert("RGB")
            buf = io.BytesIO()
            if e in ("png", "gif", "bmp", "tif", "tiff", "ico"):
                frame.save(buf, format="PNG", optimize=True)
            else:
                frame.save(buf, format="JPEG", quality=92)
            prepared.append(buf.getvalue())

    mm = img2pdf.mm_to_pt
    sizes = {"a4": (mm(210), mm(297)), "letter": (img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11)), "legal": (img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(14))}
    border = {"none": 0, "small": mm(10), "big": mm(25)}.get(margin, 0)
    layout = None
    if page_size in sizes:
        w, h = sizes[page_size]
        if orientation == "landscape":
            w, h = h, w
        layout = img2pdf.get_layout_fun((w, h), border=(border, border) if border else None, fit=img2pdf.FitMode.into,
                                        auto_orient=orientation == "auto")
    try:
        dst.write_bytes(img2pdf.convert(prepared, layout_fun=layout) if layout else img2pdf.convert(prepared))
    except Exception as exc:
        raise ToolError(f"Could not read one of the images: {exc}") from exc
    return dst


def _pandoc_to_html(src: Path, fmt: str, dst: Path) -> Path:
    # --sandbox: the document can't make pandoc read other files or fetch URLs (include directives, images…)
    run(["pandoc", "--sandbox", str(src), "-f", fmt, "-t", "html5", "-s", "--embed-resources",
         "--metadata", f"pagetitle={stem(src.name)}", "-o", str(dst)], timeout=300)
    page = dst.read_text(encoding="utf-8", errors="replace")
    page = page.replace("</head>", f"<style>{DOC_CSS}</style></head>", 1) if "</head>" in page else f"<style>{DOC_CSS}</style>{page}"
    dst.write_text(page, encoding="utf-8")
    return dst


def _text_to_html(src: Path, dst: Path) -> Path:
    raw = src.read_bytes()
    text = raw.decode("latin-1")
    for enc in ("utf-8", "utf-16", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    dst.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(src.name)}</title><style>{DOC_CSS}"
        "pre{background:none;border:0;padding:0;font-size:8.5pt}</style></head><body>"
        f"<h3>{html.escape(src.name)}</h3><pre>{html.escape(text)}</pre></body></html>",
        encoding="utf-8",
    )
    return dst


def _eml_to_html(src: Path, dst: Path) -> Path:
    msg = email.message_from_bytes(src.read_bytes(), policy=email.policy.default)
    body = msg.get_body(preferencelist=("html", "plain"))
    content = body.get_content() if body else ""
    if body is not None and body.get_content_type() == "text/plain":
        content = f"<pre>{html.escape(content)}</pre>"
    head = "".join(
        f"<tr><th style='width:90px'>{h}</th><td>{html.escape(str(msg.get(h, '')))}</td></tr>"
        for h in ("From", "To", "Cc", "Date", "Subject") if msg.get(h)
    )
    attachments = [html.escape(a.get_filename() or "attachment") for a in msg.iter_attachments()]
    att_html = f"<p><b>Attachments:</b> {', '.join(attachments)}</p>" if attachments else ""
    dst.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{DOC_CSS}</style></head><body>"
                   f"<table>{head}</table>{att_html}<hr>{content}</body></html>", encoding="utf-8")
    return dst


def to_pdf(src: Path, workdir: Path, original_name: str | None = None) -> Path:
    """Convert any supported document, image or data file into a PDF inside ``workdir``."""
    name = original_name or src.name
    e = ext_of(name)
    out = workdir / f"{src.stem}.__pdf__.pdf"
    cat = F.category(name)
    if e == "pdf":
        return src
    if cat in ("audio", "video"):
        raise ToolError(f"'{name}' is an audio/video file. Use the Media Converter for it.")
    if e == "svg":
        import cairosvg

        cairosvg.svg2pdf(bytestring=src.read_bytes(), write_to=str(out), unsafe=False)
        return out
    if cat == "image":
        return images_to_pdf([src], out)
    if cat == "data":
        from .data import read_table, table_to_html

        page = workdir / f"{src.stem}.table.html"
        page.write_text(table_to_html(read_table(src, name), title=stem(name), css=DOC_CSS), encoding="utf-8")
        return html_to_pdf(page, out, opts={"margin": "small", "screen_css": False})
    if e in F.PANDOC_EXT:
        return html_to_pdf(_pandoc_to_html(src, F.PANDOC_EXT[e], workdir / f"{src.stem}.html"), out, opts={"margin": "normal", "screen_css": False})
    if e in F.HTML_EXT:
        return html_to_pdf(src, out, opts={"margin": "small", "screen_css": False})
    if e == "eml":
        return html_to_pdf(_eml_to_html(src, workdir / f"{src.stem}.mail.html"), out, opts={"margin": "normal", "screen_css": False})
    if e in F.CODE_EXT:
        return html_to_pdf(_text_to_html(src, workdir / f"{src.stem}.code.html"), out, opts={"margin": "normal", "screen_css": False})
    if e in F.OFFICE_EXT or e in F.SHEET_EXT or not e:
        named = src if src.name.lower().endswith(f".{e}") else src.with_name(f"{src.stem}.{e or 'txt'}")
        if named != src:
            shutil.copyfile(src, named)
        return office_to_pdf(named, out)
    try:
        src.read_bytes()[:4096].decode("utf-8")
        return html_to_pdf(_text_to_html(src, workdir / f"{src.stem}.code.html"), out, opts={"margin": "normal", "screen_css": False})
    except UnicodeDecodeError:
        raise ToolError(f"'{name}' is a file type we can't convert yet (.{e}).") from None


# --------------------------------------------------------------------------- PDF -> outputs

def pdf_to_images(pdf: Path, outdir: Path, fmt: str = "jpg", dpi: int = 150, pages: list[int] | None = None, base: str = "page") -> list[Path]:
    doc = raster.open_doc(pdf)
    out = []
    try:
        idx = pages if pages is not None else range(len(doc))
        for i in idx:
            img = raster.render(doc[i], dpi)
            p = outdir / f"{base}-{i + 1:03d}.{fmt}"
            if fmt in ("jpg", "jpeg"):
                img.save(p, format="JPEG", quality=90, optimize=True, dpi=(dpi, dpi))
            elif fmt == "png":
                img.save(p, format="PNG", optimize=True, dpi=(dpi, dpi))
            elif fmt == "webp":
                img.save(p, format="WEBP", quality=88)
            else:
                img.save(p, format=fmt.upper())
            out.append(p)
    finally:
        doc.close()
    return out


def pdf_to_tiff(pdf: Path, dst: Path, dpi: int = 200) -> Path:
    doc = raster.open_doc(pdf)
    try:
        frames = [raster.render(doc[i], dpi) for i in range(len(doc))]
    finally:
        doc.close()
    frames[0].save(dst, save_all=True, append_images=frames[1:], compression="tiff_deflate", dpi=(dpi, dpi))
    return dst


def pdf_to_svg(pdf: Path, outdir: Path, base: str) -> list[Path]:
    """Vector SVG per page (text and shapes stay crisp at any zoom)."""
    doc = raster.open_doc(pdf)
    n = len(doc)
    doc.close()
    out = []
    for i in range(n):
        dst = outdir / f"{base}-{i + 1:03d}.svg" if n > 1 else outdir / f"{base}.svg"
        run(["pdftocairo", "-svg", "-f", str(i + 1), "-l", str(i + 1), str(pdf), str(dst)], timeout=300)
        out.append(dst)
    return out


def extract_images(pdf: Path, outdir: Path, min_size: int = 32) -> list[Path]:
    doc = raster.open_doc(pdf)
    out: list[Path] = []
    try:
        for pno in range(len(doc)):
            for k, img in enumerate(raster.iter_images(doc[pno])):
                try:
                    w, h = img.get_px_size()
                except Exception:
                    continue
                if w < min_size or h < min_size:
                    continue
                stem_path = outdir / f"image-p{pno + 1:03d}-{k + 1:03d}"
                try:
                    img.extract(str(stem_path), fb_format="png")
                except Exception:
                    try:
                        img.get_bitmap(render=True).to_pil().save(str(stem_path) + ".png")
                    except Exception:
                        continue
                out.extend(sorted(outdir.glob(stem_path.name + ".*")))
    finally:
        doc.close()
    if not out:
        raise ToolError("No embedded images were found in this PDF.")
    return out


def pdf_to_text(pdf: Path, dst: Path) -> Path:
    doc = raster.open_doc(pdf)
    try:
        parts = [f"--- Page {i + 1} ---\n" + raster.page_text(doc[i]).strip() for i in range(len(doc))]
    finally:
        doc.close()
    dst.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return dst


def from_pdf(pdf: Path, fmt: str, workdir: Path, base: str, opts: dict | None = None, progress: Progress | None = None) -> list[Path]:
    """Convert a PDF into ``fmt``. Returns one or more output files."""
    opts = opts or {}
    fmt = fmt.lower()
    o = workdir / base
    if fmt == "pdf":
        dst = o.with_suffix(".pdf")
        if pdf != dst:
            shutil.copyfile(pdf, dst)
        return [dst]
    if fmt == "pdfa":
        from .ops import to_pdfa

        return [to_pdfa(pdf, o.with_name(base + "-pdfa.pdf"), str(opts.get("pdfa_level", "2")))]
    if fmt == "docx":
        return [export.to_docx(pdf, o.with_suffix(".docx"), workdir, progress)]
    if fmt in ("odt", "rtf"):
        docx = export.to_docx(pdf, workdir / f"{base}.__tmp__.docx", workdir, progress)
        dst = o.with_suffix(f".{fmt}")
        run(["pandoc", str(docx), "-f", "docx", "-t", fmt, "-s", "-o", str(dst)], timeout=300)
        return [dst]
    if fmt == "pptx":
        return [export.to_pptx(pdf, o.with_suffix(".pptx"), workdir, editable=opts.get("editable", True), progress=progress)]
    if fmt == "xlsx":
        return [export.to_xlsx(pdf, o.with_suffix(".xlsx"), progress)]
    if fmt == "csv":
        return export.to_csv(pdf, workdir, base)
    if fmt == "json":
        from .data import pdf_tables_json

        return [pdf_tables_json(pdf, o.with_suffix(".json"))]
    if fmt in ("jpg", "jpeg", "png", "webp"):
        imgdir = workdir / f"{base}-images"
        imgdir.mkdir(exist_ok=True)
        return pdf_to_images(pdf, imgdir, "jpg" if fmt == "jpeg" else fmt, int(opts.get("dpi", 150) or 150), base=base)
    if fmt in ("tiff", "tif"):
        return [pdf_to_tiff(pdf, o.with_suffix(".tiff"), int(opts.get("dpi", 200) or 200))]
    if fmt == "svg":
        svgdir = workdir / f"{base}-svg"
        svgdir.mkdir(exist_ok=True)
        return pdf_to_svg(pdf, svgdir, base)
    if fmt == "txt":
        return [pdf_to_text(pdf, o.with_suffix(".txt"))]
    if fmt == "md":
        md, _ = export.to_markdown(pdf, workdir, progress=progress)
        dst = o.with_suffix(".md")
        dst.write_text(md, encoding="utf-8")
        return [dst]
    if fmt in ("html", "epub"):
        md, img_dir = export.to_markdown(pdf, workdir, include_images=True, progress=progress)
        md_path = workdir / f"{base}.__tmp__.md"
        md_path.write_text(md, encoding="utf-8")
        css = workdir / "doc.css"
        css.write_text(DOC_CSS, encoding="utf-8")
        dst = o.with_suffix(f".{fmt}")
        args = ["pandoc", str(md_path), "-f", "markdown", "-t", "html5" if fmt == "html" else "epub3", "-s",
                "--resource-path", str(img_dir), "--metadata", f"title={base}", "-o", str(dst)]
        args += ["--embed-resources", "-c", str(css)] if fmt == "html" else ["--css", str(css)]
        run(args, timeout=300)
        return [dst]
    raise ToolError(f"PDF can't be converted to {fmt.upper()}.")


def bundle(outputs: list[Path], workdir: Path, zip_name: str) -> Path:
    if len(outputs) == 1:
        return outputs[0]
    return zip_files([(p, p.name) for p in outputs], workdir / zip_name)
