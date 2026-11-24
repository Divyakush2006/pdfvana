"""Shared fixtures: a realistic set of sample documents, images and media, plus an API client.

The end-to-end tests run against a live instance (``BASE_URL``, default
http://127.0.0.1:8000), e.g. the docker compose stack.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

import httpx
import pikepdf
import pytest
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _pdf(path: Path, pages: int, title: str, table: bool = False, image: bool = False, rotate: int = 0) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    for i in range(pages):
        c.setFont("Helvetica-Bold", 22)
        c.drawString(72, h - 80, f"{title} - page {i + 1}")
        c.setFont("Helvetica", 11)
        c.drawString(72, h - 110, "Contact: jane.doe@example.com, phone +91 98765 43210, PAN ABCDE1234F")
        text = c.beginText(72, h - 140)
        for line in ["Quarterly revenue grew strongly across every region this year.",
                     "The board approved the new roadmap and hiring plan for next year.",
                     "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod."]:
            text.textLine(line)
        c.drawText(text)
        if table:
            x0, y0 = 72, h - 330
            for r in range(5):
                for col in range(4):
                    c.rect(x0 + col * 110, y0 - r * 22, 110, 22)
                    label = ("Item", "Q1", "Q2", "Q3")[col] if r == 0 else (f"Row {r}" if col == 0 else str(r * col * 10))
                    c.drawString(x0 + col * 110 + 5, y0 - r * 22 + 7, label)
        if image:
            img = Image.new("RGB", (1200, 700), (30, 120, 200))
            ImageDraw.Draw(img).ellipse((150, 120, 1050, 580), fill=(240, 200, 40))
            c.drawImage(ImageReader(img), 72, 120, 440, 256)
        c.showPage()
    c.save()
    if rotate:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for p in pdf.pages:
                p.rotate(rotate, relative=False)
            pdf.save(path)
    return path


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("samples")
    _pdf(d / "a.pdf", 3, "Document A", table=True, image=True)
    _pdf(d / "b.pdf", 2, "Document B")
    _pdf(d / "rotated.pdf", 1, "Rotated page", rotate=90)
    # scanned page (image only)
    img = Image.new("L", (1700, 2200), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 52)
    for i, line in enumerate(["INVOICE 2026-117", "Scanned document test", "Total amount due 4250.00"]):
        draw.text((150, 220 + i * 130), line, fill=0, font=font)
    img.save(d / "scan.png")
    import img2pdf

    (d / "scanned.pdf").write_bytes(img2pdf.convert(str(d / "scan.png"), layout_fun=img2pdf.get_fixed_dpi_layout_fun((200, 200))))
    with pikepdf.open(d / "b.pdf") as pdf:
        pdf.save(d / "locked.pdf", encryption=pikepdf.Encryption(user="secret", owner="own", R=6))
    # office documents
    from docx import Document

    doc = Document()
    doc.add_heading("Quarterly report", 0)
    doc.add_paragraph("Revenue grew 24% this quarter. " * 15)
    t = doc.add_table(rows=3, cols=3)
    t.style = "Table Grid"
    for r in range(3):
        for c in range(3):
            t.cell(r, c).text = f"R{r}C{c}"
    doc.save(d / "report.docx")
    from pptx import Presentation

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Roadmap 2027"
    s.placeholders[1].text = "Launch\nScale\nExpand"
    prs.save(d / "deck.pptx")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Units", "Price"])
    for r in range(1, 11):
        ws.append([f"Item {r}", r, r * 2.5])
    wb.save(d / "data.xlsx")
    (d / "data.csv").write_text("name,units,price\nAlpha,3,9.99\nBeta,5,19.5\n", encoding="utf-8")
    (d / "data.json").write_text(json.dumps([{"name": "Alpha", "units": 3, "meta": {"tag": "x"}}, {"name": "Beta", "units": 5}]))
    (d / "notes.md").write_text("# Meeting notes\n\n- Item **one**\n- Item two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    (d / "page.html").write_text("<html><body><h1 style='color:#0f766e'>HTML page</h1><p>Rendered by the browser engine.</p></body></html>")
    (d / "script.py").write_text("def hello():\n    return 'world'\n" * 10)
    (d / "mail.eml").write_text("From: a@example.com\nTo: b@example.com\nSubject: Hello\nContent-Type: text/plain\n\nE-mail body.\n")
    # images
    Image.new("RGB", (1200, 800), (200, 60, 60)).save(d / "photo.jpg", quality=92)
    logo = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    ImageDraw.Draw(logo).ellipse((80, 80, 520, 520), fill=(15, 118, 110, 255))
    ImageDraw.Draw(logo).rectangle((250, 160, 350, 440), fill=(255, 255, 255, 255))
    logo.save(d / "logo.png")
    Image.new("RGB", (900, 1200), (240, 240, 240)).save(d / "scan.webp")
    sig = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(sig).line([(20, 150), (200, 40), (380, 160), (580, 50)], fill=(10, 20, 120, 255), width=8)
    sig.save(d / "sig.png")
    frames = [Image.new("RGB", (120, 80), (i * 40, 100, 200 - i * 40)) for i in range(5)]
    frames[0].save(d / "anim.gif", save_all=True, append_images=frames[1:], duration=120, loop=0)
    (d / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="28" fill="#0f766e"/></svg>')
    # media
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", "-pix_fmt", "yuv420p", str(d / "clip.mp4")], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=660:duration=2", str(d / "tone.wav")], check=True)
    return d


class Api:
    def __init__(self, samples: Path):
        self.samples = samples
        self.client = httpx.Client(base_url=BASE_URL, timeout=180)

    def run(self, tool: str, files: list[str], options: dict | None = None, extras: dict | None = None):
        parts = [("files", (f, (self.samples / f).read_bytes())) for f in files]
        for k, f in (extras or {}).items():
            parts.append((f"extra_{k}", (f, (self.samples / f).read_bytes())))
        r = self.client.post("/api/jobs", data={"tool": tool, "options": json.dumps(options or {})}, files=parts or None)
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        deadline = time.time() + 300
        while time.time() < deadline:
            s = self.client.get(f"/api/jobs/{jid}").json()
            if s["status"] in ("done", "error"):
                break
            time.sleep(0.4)
        if s["status"] == "error":
            return s, None
        data = self.client.get(f"/api/jobs/{jid}/download").content
        return s, data


@pytest.fixture(scope="session")
def api(samples) -> Api:
    for _ in range(60):
        try:
            if httpx.get(f"{BASE_URL}/api/health", timeout=3).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(1)
    return Api(samples)


def pdf_pages(data: bytes) -> int:
    return len(pikepdf.open(io.BytesIO(data)).pages)


def pdf_text(data: bytes) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def zip_names(data: bytes) -> list[str]:
    return zipfile.ZipFile(io.BytesIO(data)).namelist()
