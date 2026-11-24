# Architecture

PDFVana is two containers: the **engine** (this repository) and an internal **conversion service** for office documents and
web pages. The engine also serves the web app.

```
┌────────────── Browser ──────────────┐
│ React + TypeScript + Tailwind        │  page previews rendered locally, drag & drop,
│ (server-rendered first paint + SEO)  │  visual page organiser, signature editor
└──────────────┬──────────────────────┘
               │ POST /api/jobs (multipart) → poll /api/jobs/{id} → GET …/download
┌──────────────▼──────────────────────────────────────────────┐
│ Engine — Python 3.12, FastAPI                                │
│                                                              │
│ main.py     HTTP API, limits, rate limiting, security headers│
│ jobs.py     thread-pool job queue, progress, auto-deletion   │
│ tools.py    registry of all tools (drives the UI)            │
│ convert.py  documents: anything → PDF → anything             │
│ media.py    images, audio, video                             │
│ data.py     CSV / JSON / Excel tables                        │
│ ops.py      PDF operations (merge, compress, OCR, redact…)   │
│ engine/     geometry · raster · stamp · layout · export      │
│ seo.py      titles, structured data, sitemap                 │
└──────────────┬──────────────────────────────────────────────┘
               │ internal HTTP
┌──────────────▼───────────────┐
│ Conversion service            │  office documents and HTML → PDF,
│ (never exposed publicly)      │  complex-script text typesetting, screenshots
└──────────────────────────────┘
```

## Design principles

**PDF is the hub format for documents.** Every document input is normalised to PDF, every operation is PDF → PDF and every
document output is produced from PDF. This is what makes "merge a Word file, a photo and a spreadsheet, then export a
PowerPoint" a single click. Images, audio, video and tabular data have direct converters instead.

**View space vs. user space.** `engine/geometry.py` maps between what a reader sees (top-left origin, after rotation and
crop box) and the PDF's own coordinate system. Every stamp, crop, highlight and redaction is computed in view space, so
rotated pages and offset crop boxes behave correctly everywhere.

**Vector stamps.** Watermarks, page numbers, headers, signatures and comparison highlights are small one-page PDFs placed as
Form XObjects with an exact matrix. Latin text is typeset locally; any other script is shaped by the browser engine, so
Devanagari, Arabic, CJK and Tamil render correctly.

**Layout analysis.** `engine/layout.py` rebuilds reading order (including two-column pages), paragraphs, headings, lists,
tables and images from PDF pages. The Word, Markdown, HTML and EPUB writers consume that model; the PowerPoint writer places
editable text boxes over a text-free rendering of each page.

**True redaction.** Pages containing matches are re-rendered with the boxes burned in, so nothing underneath survives, then
re-recognised with OCR so the rest of the page stays searchable.

## Job lifecycle

1. Upload is streamed to `DATA_DIR/<job>/in` with per-file and total size limits.
2. The job runs in a worker thread with progress updates; inputs are deleted as soon as it finishes.
3. The result is kept for `JOB_TTL_SECONDS`, then deleted by the janitor. `DELETE /api/jobs/{id}` removes it immediately.
4. On start-up the data directory is wiped — nothing persists across restarts.

## Scaling

The job store is in memory, so run one engine replica per host and scale vertically (CPU count = parallel jobs). For
horizontal scaling, put a shared queue (e.g. Redis) and shared temporary storage in front of several engine replicas, and
run several conversion-service replicas behind a load balancer.
