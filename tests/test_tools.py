"""End-to-end tests: every tool through the public HTTP API, with output verification."""
from __future__ import annotations

import io
import json
import zipfile

import pikepdf
import pytest
from PIL import Image

from conftest import pdf_pages, pdf_text, zip_names


def ok(result):
    status, data = result
    assert status["status"] == "done", status.get("error")
    assert data
    return status, data


def ooxml(data: bytes) -> None:
    assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None


# --------------------------------------------------------------------------- organise

def test_merge_mixed_files(api):
    s, d = ok(api.run("merge-pdf", ["a.pdf", "report.docx", "photo.jpg", "data.xlsx", "deck.pptx"]))
    assert pdf_pages(d) >= 7
    assert "Merged 5 files" in s["message"]


def test_merge_normalized_a4(api):
    _, d = ok(api.run("merge-pdf", ["a.pdf", "rotated.pdf"], {"normalize": "a4"}))
    pdf = pikepdf.open(io.BytesIO(d))
    assert len(pdf.pages) == 4
    assert round(float(pdf.pages[0].mediabox[2])) == 595


def test_split_ranges(api):
    _, d = ok(api.run("split-pdf", ["a.pdf"], {"mode": "ranges", "ranges": "1-2, 3"}))
    assert len(zip_names(d)) == 2


def test_split_every_page(api):
    _, d = ok(api.run("split-pdf", ["a.pdf"], {"mode": "all"}))
    assert len(zip_names(d)) == 3


def test_remove_and_extract(api):
    _, d = ok(api.run("remove-pages", ["a.pdf"], {"pages": "2"}))
    assert pdf_pages(d) == 2
    _, d = ok(api.run("extract-pages", ["a.pdf"], {"pages": "1,3"}))
    assert pdf_pages(d) == 2


def test_organize(api):
    layout = json.dumps([{"p": 2, "r": 90}, {"p": -1, "r": 0}, {"p": 0, "r": 0}])
    _, d = ok(api.run("organize-pdf", ["a.pdf"], {"layout": layout}))
    pdf = pikepdf.open(io.BytesIO(d))
    assert len(pdf.pages) == 3
    assert int(pdf.pages[0].obj.get("/Rotate", 0)) == 90


def test_rotate_many(api):
    _, d = ok(api.run("rotate-pdf", ["a.pdf", "b.pdf"], {"angle": "180"}))
    assert len(zip_names(d)) == 2


# --------------------------------------------------------------------------- optimise

def test_compress(api, samples):
    s, d = ok(api.run("compress-pdf", ["a.pdf"], {"level": "recommended"}))
    assert len(d) < (samples / "a.pdf").stat().st_size
    assert "smaller" in s["message"] or "optimised" in s["message"]


def test_compress_target(api):
    s, d = ok(api.run("compress-pdf", ["a.pdf"], {"level": "target", "target_mb": 0.05}))
    assert pdf_pages(d) == 3


def test_repair(api):
    ok(api.run("repair-pdf", ["a.pdf"]))


def test_ocr_scanned_pdf(api):
    _, d = ok(api.run("ocr-pdf", ["scanned.pdf"], {"languages": ["eng"]}))
    assert "INVOICE" in pdf_text(d)


def test_ocr_image_to_text(api):
    _, d = ok(api.run("ocr-pdf", ["scan.png"], {"output": "txt"}))
    assert b"INVOICE" in d


def test_pdfa(api):
    _, d = ok(api.run("pdf-to-pdfa", ["a.pdf"]))
    assert b"pdfaid" in d


# --------------------------------------------------------------------------- convert to PDF

@pytest.mark.parametrize("tool,file", [("word-to-pdf", "report.docx"), ("powerpoint-to-pdf", "deck.pptx"),
                                       ("excel-to-pdf", "data.xlsx")])
def test_office_to_pdf(api, tool, file):
    _, d = ok(api.run(tool, [file]))
    assert pdf_pages(d) >= 1


def test_images_to_pdf(api):
    _, d = ok(api.run("jpg-to-pdf", ["photo.jpg", "logo.png", "scan.webp"], {"page_size": "a4", "margin": "small"}))
    assert pdf_pages(d) == 3


def test_html_file_to_pdf(api):
    _, d = ok(api.run("html-to-pdf", ["page.html"]))
    assert "HTML page" in pdf_text(d)


def test_url_blocks_private_network(api):
    s, _ = api.run("html-to-pdf", [], {"url": "http://169.254.169.254/latest/meta-data"})
    assert s["status"] == "error" and "private" in s["error"]


def test_anything_to_pdf(api):
    _, d = ok(api.run("any-to-pdf", ["notes.md", "script.py", "mail.eml", "data.csv", "icon.svg"], {"merge": True}))
    assert pdf_pages(d) >= 5


# --------------------------------------------------------------------------- convert from PDF

def test_pdf_to_word_keeps_text_and_table(api):
    from docx import Document

    _, d = ok(api.run("pdf-to-word", ["a.pdf"]))
    doc = Document(io.BytesIO(d))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Document A" in text and "Quarterly revenue" in text
    assert len(doc.tables) >= 1


def test_scanned_pdf_to_word_uses_ocr(api):
    from docx import Document

    _, d = ok(api.run("pdf-to-word", ["scanned.pdf"]))
    assert "INVOICE" in "\n".join(p.text for p in Document(io.BytesIO(d)).paragraphs)


def test_pdf_to_powerpoint(api):
    from pptx import Presentation

    _, d = ok(api.run("pdf-to-powerpoint", ["a.pdf"]))
    prs = Presentation(io.BytesIO(d))
    assert len(prs.slides) == 3
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert any("Document A" in t for t in texts)


def test_pdf_to_excel(api):
    from openpyxl import load_workbook

    _, d = ok(api.run("pdf-to-excel", ["a.pdf"], {"format": "xlsx"}))
    ws = load_workbook(io.BytesIO(d)).worksheets[0]
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Item" in values and 40 in values


def test_pdf_to_csv(api):
    _, d = ok(api.run("pdf-to-excel", ["a.pdf"], {"format": "csv"}))
    assert d[:3] == b"\xef\xbb\xbf" or zip_names(d)


def test_pdf_to_images(api):
    _, d = ok(api.run("pdf-to-jpg", ["a.pdf"], {"image_format": "png", "dpi": "72"}))
    assert len(zip_names(d)) == 3


def test_extract_images(api):
    s, d = ok(api.run("pdf-to-jpg", ["a.pdf"], {"mode": "extract"}))
    assert "Extracted" in s["message"]


def test_pdf_to_markdown(api):
    _, d = ok(api.run("pdf-to-markdown", ["a.pdf"]))
    md = d.decode()
    assert md.startswith("# Document A") and "| Item |" in md


def test_pdf_to_svg(api):
    _, d = ok(api.run("pdf-to-svg", ["b.pdf"]))
    assert len(zip_names(d)) == 2


@pytest.mark.parametrize("fmt", ["epub", "html", "odt"])
def test_pdf_to_text_formats(api, fmt):
    ok(api.run("pdf-to-text", ["a.pdf"], {"format": fmt}))


# --------------------------------------------------------------------------- edit

def test_watermark_text(api):
    _, d = ok(api.run("add-watermark", ["a.pdf", "rotated.pdf"], {"text": "CONFIDENTIAL"}))
    assert len(zip_names(d)) == 2


def test_watermark_unicode_and_image(api):
    _, d = ok(api.run("add-watermark", ["a.pdf"], {"text": "गोपनीय — DRAFT", "mosaic": True}))
    assert "DRAFT" in pdf_text(d)
    ok(api.run("add-watermark", ["a.pdf"], {"kind": "image", "layer": "under"}, extras={"image": "logo.png"}))


def test_page_numbers(api):
    _, d = ok(api.run("page-numbers", ["a.pdf"], {"format": "page_n_of_total"}))
    assert "Page 3 of 3" in pdf_text(d)


def test_header_footer(api):
    _, d = ok(api.run("header-footer", ["rotated.pdf"], {"header": "ACME Internal", "footer": "Page {n} of {total}"}))
    assert "ACME Internal" in pdf_text(d)


def test_sign(api):
    ok(api.run("sign-pdf", ["a.pdf"], {"pages": "last", "x": 0.6, "y": 0.8, "width": 0.3}, extras={"signature": "sig.png"}))


def test_crop(api):
    _, d = ok(api.run("crop-pdf", ["a.pdf"], {"mode": "auto"}))
    pdf = pikepdf.open(io.BytesIO(d))
    assert "/CropBox" in pdf.pages[0].obj


def test_flatten_and_metadata(api):
    ok(api.run("flatten-pdf", ["a.pdf"], {"mode": "rasterize", "dpi": 100}))
    _, d = ok(api.run("edit-metadata", ["a.pdf"], {"title": "New title", "author": "Me"}))
    assert str(pikepdf.open(io.BytesIO(d)).docinfo.get("/Title")) == "New title"


# --------------------------------------------------------------------------- security

def test_protect_and_unlock(api):
    _, d = ok(api.run("protect-pdf", ["a.pdf"], {"password": "pw123", "confirm": "pw123"}))
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(d))
    _, d = ok(api.run("unlock-pdf", ["locked.pdf"], {"password": "secret"}))
    assert len(pikepdf.open(io.BytesIO(d)).pages) == 2
    s, _ = api.run("unlock-pdf", ["locked.pdf"], {"password": "wrong"})
    assert s["status"] == "error" and "Wrong password" in s["error"]


def test_redact_removes_text(api):
    s, d = ok(api.run("redact-pdf", ["a.pdf"], {"terms": "Lorem", "patterns": ["email", "pan"]}))
    text = pdf_text(d)
    assert "jane.doe@example.com" not in text and "ABCDE1234F" not in text and "Lorem" not in text
    assert "Quarterly revenue" in text  # rest of the page stays searchable
    assert "Permanently removed" in s["message"]


def test_sanitize(api):
    ok(api.run("sanitize-pdf", ["a.pdf"]))


def test_compare(api):
    s, d = ok(api.run("compare-pdf", ["a.pdf", "b.pdf"]))
    assert pdf_pages(d) == 3 and "similar" in s["message"]


# --------------------------------------------------------------------------- universal converter

@pytest.mark.parametrize("src,fmt", [
    ("report.docx", "pptx"), ("report.docx", "md"), ("report.docx", "odt"), ("notes.md", "docx"),
    ("a.pdf", "html"), ("a.pdf", "tiff"), ("a.pdf", "json"), ("deck.pptx", "png"),
    ("photo.jpg", "png"), ("photo.jpg", "webp"), ("photo.jpg", "avif"), ("logo.png", "ico"), ("logo.png", "svg"),
    ("icon.svg", "png"), ("anim.gif", "webp"), ("scan.png", "docx"), ("logo.png", "pdf"),
    ("data.csv", "xlsx"), ("data.json", "csv"), ("data.xlsx", "json"), ("data.csv", "pdf"),
    ("clip.mp4", "mp3"), ("clip.mp4", "gif"), ("clip.mp4", "webm"), ("tone.wav", "mp3"), ("anim.gif", "mp4"),
])
def test_universal_converter(api, src, fmt):
    s, d = ok(api.run("convert", [src], {"format": fmt}))
    assert s["result"]["name"].endswith((f".{fmt}", ".zip"))


def test_docx_to_pdf_page_keeps_content(api):
    """/docx-to-pdf runs the Universal Converter with PDF preselected."""
    s, d = ok(api.run("convert", ["report.docx"], {"format": "pdf"}))
    assert s["result"]["name"] == "report.pdf"
    text = pdf_text(d)
    assert "Quarterly report" in text and "Revenue grew 24%" in text and "R2C2" in text


def test_pptx_to_pdf_page_one_page_per_slide(api):
    s, d = ok(api.run("convert", ["deck.pptx"], {"format": "pdf"}))
    assert s["result"]["name"] == "deck.pdf"
    assert pdf_pages(d) == 1 and "Roadmap 2027" in pdf_text(d)


def test_pdf_to_docx_page_is_editable(api):
    from docx import Document

    s, d = ok(api.run("convert", ["a.pdf"], {"format": "docx"}))
    assert s["result"]["name"] == "a.docx"
    doc = Document(io.BytesIO(d))
    assert "Document A" in "\n".join(p.text for p in doc.paragraphs) and doc.tables


def test_universal_rejects_impossible(api):
    s, _ = api.run("convert", ["tone.wav"], {"format": "docx"})
    assert s["status"] == "error"


# --------------------------------------------------------------------------- images & media

def test_image_converter_ico_sizes(api):
    _, d = ok(api.run("image-converter", ["logo.png"], {"format": "ico", "ico_sizes": ["16", "32", "48"]}))
    im = Image.open(io.BytesIO(d))
    assert im.format == "ICO" and (48, 48) in im.info["sizes"]


def test_image_to_svg_trace(api):
    _, d = ok(api.run("image-to-svg", ["logo.png"]))
    assert b"<svg" in d and b"<path" in d


def test_compress_image_target(api):
    s, d = ok(api.run("compress-image", ["photo.jpg"], {"mode": "target", "target_kb": 10}))
    assert len(d) <= 10 * 1024


def test_resize_image(api):
    _, d = ok(api.run("resize-image", ["photo.jpg"], {"resize_mode": "pixels", "width": 300, "rotate": "90"}))
    assert Image.open(io.BytesIO(d)).size == (200, 300)


def test_favicon_pack(api):
    _, d = ok(api.run("favicon-generator", ["logo.png"]))
    names = zip_names(d)
    assert "favicon.ico" in names and "site.webmanifest" in names


def test_strip_exif(api):
    ok(api.run("remove-image-metadata", ["photo.jpg"]))


def test_video_tools(api):
    ok(api.run("video-converter", ["clip.mp4"], {"format": "mov", "resolution": "240"}))
    ok(api.run("video-to-gif", ["clip.mp4"], {"start": "0", "end": "1"}))
    ok(api.run("compress-video", ["clip.mp4"]))
    _, d = ok(api.run("audio-converter", ["clip.mp4"], {"format": "m4a"}))
    assert len(d) > 1000


def test_data_converter(api):
    _, d = ok(api.run("data-converter", ["data.json"], {"format": "xlsx"}))
    ooxml(d)


# --------------------------------------------------------------------------- studio

def test_studio_pipeline_protected_pdf(api):
    steps = [{"op": "page_numbers", "format": "Page {n} of {total}"}, {"op": "watermark", "text": "DRAFT"},
             {"op": "compress", "level": "recommended"}, {"op": "protect", "password": "abc"}]
    s, d = ok(api.run("studio", ["report.docx", "a.pdf", "photo.jpg", "notes.md"],
                      {"merge": True, "format": "pdf", "output_name": "Board pack", "steps": json.dumps(steps)}))
    assert s["result"]["name"].startswith("Board pack")
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(d))


def test_studio_to_powerpoint(api):
    _, d = ok(api.run("studio", ["report.docx", "deck.pptx", "data.xlsx"], {"merge": True, "format": "pptx"}))
    ooxml(d)
