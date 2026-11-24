<div align="center">

<img src="frontend/public/favicon.svg" width="88" alt="PDFVana logo" />

# PDFVana

### Free & open-source PDF tools and universal file converter

*Vana (वन) is Sanskrit for "forest" — PDFVana is a forest of free tools for every document, image and media file.*

**Merge, split, compress, sign, protect and OCR PDFs — and convert anything to anything:**
Word, PowerPoint, Excel, images (JPG, PNG, WebP, HEIC, AVIF, SVG, ICO), audio and video.
No sign-up. No watermarks. No limits. Self-host it in one command.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-4f46e5.svg)](LICENSE)
[![CI](https://github.com/divyakush2006/pdfvana/actions/workflows/ci.yml/badge.svg)](https://github.com/divyakush2006/pdfvana/actions/workflows/ci.yml)
[![Docker image](https://img.shields.io/badge/docker-ghcr.io%2Fdivyakush2006%2Fpdfvana-2496ED?logo=docker&logoColor=white)](https://github.com/divyakush2006/pdfvana/pkgs/container/pdfvana)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-7c3aed.svg)](CONTRIBUTING.md)

[Features](#-features) · [Quick start](#-quick-start) · [Deploy](#-deploy-to-production) · [API](#-rest-api) · [Contributing](CONTRIBUTING.md)

<img src="docs/assets/home.jpg" alt="PDFVana home page with all PDF, image and media tools" width="100%" />

</div>

---

## Why PDFVana?

Most "free" PDF websites limit how many files you can process, add watermarks, push a paid plan, and keep your documents on
their servers. PDFVana is a complete, **free alternative to iLovePDF, Smallpdf and online-convert style services** that you
can use online or run on your own servers:

- **Everything is free** — no daily task limits, no file-count caps, no premium tier.
- **Private by design** — no account, no trackers, no third-party requests. Files are processed in isolation and deleted
  automatically after one hour (or instantly with *Delete now*).
- **Professional output** — true redaction, AES-256 encryption, PDF/A archiving, searchable OCR in 28 languages
  (including Hindi, Bengali, Tamil, Telugu and other Indian scripts), editable Word/PowerPoint export.
- **One tool for every file** — documents, PDFs, images, audio, video and data, with 2,600+ format combinations.
- **Enterprise-ready** — runs anywhere Docker runs, keeps data inside your network, Apache-2.0 licensed.

## ✨ Features

**49 tools**, **175 input formats** (2,600+ format combinations) and **77 dedicated conversion pages** (e.g. `/heic-to-jpg`, `/png-to-ico`, `/mp4-to-mp3`).

| Category | Tools |
|---|---|
| **Workflows** | **Document Studio** (merge any files → apply steps → export any format), **Universal Converter** (anything → anything) |
| **Organize PDF** | Merge (PDF + Word/Excel/PowerPoint/images), Split, Remove pages, Extract pages, Visual organizer (drag, rotate, delete, insert blank), Rotate |
| **Optimize PDF** | Compress (4 levels **or exact target size in MB**), Repair, OCR (28 languages), PDF/A |
| **Convert to PDF** | Word, PowerPoint, Excel, images (incl. HEIC & SVG), HTML/web pages, Markdown, EPUB, e-mail (EML), code, CSV/JSON/Excel data |
| **Convert from PDF** | Word (layout, tables & images), editable PowerPoint, Excel/CSV, JPG/PNG/WebP/TIFF, SVG, Text/Markdown/HTML/EPUB/ODT/RTF |
| **Image tools** | Image converter (JPG, PNG, WebP, AVIF, HEIC, GIF, BMP, TIFF, ICO, SVG), Compress image (**exact KB target**), Resize/rotate/flip, Image → SVG vectoriser, Favicon generator, Remove photo metadata, Website screenshot |
| **Audio & video** | Video converter (MP4, MOV, MKV, WebM, AVI, trim, resize, mute), Audio converter (MP3, WAV, FLAC, M4A, OGG, Opus), Video → GIF, Compress video |
| **Edit PDF** | Watermark (text in any script or image, mosaic, behind content), Page numbers, Header & footer, Sign (draw/type/upload, drag to place), Crop (auto-trim), Flatten, Edit metadata |
| **Security** | Protect (AES-256 + permissions), Unlock, Redact (permanent, with e-mail/phone/card/Aadhaar/PAN detection), Sanitize |
| **Intelligence** | Compare (side-by-side diff), PDF → Markdown for AI tools |

<table>
<tr>
<td width="50%"><img src="docs/assets/converter.jpg" alt="Universal converter showing the formats a video can be converted to" /></td>
<td width="50%"><img src="docs/assets/result.jpg" alt="Result page with download, preview and continue-with suggestions" /></td>
</tr>
</table>

## 🚀 Quick start

Requirements: [Docker](https://docs.docker.com/get-docker/) with Compose, ~4 GB RAM.

```bash
git clone https://github.com/divyakush2006/pdfvana.git
cd pdfvana
docker compose up -d --build
```

Open **http://localhost:8080**. That's it.

## 🌍 Deploy to production

A ready-made stack with automatic HTTPS is in [`deploy/`](deploy):

```bash
export DOMAIN=pdf.example.com          # DNS must point at the server
docker compose -f deploy/docker-compose.prod.yml up -d
```

See [docs/deployment.md](docs/deployment.md) for sizing, scaling, security hardening and SEO setup.

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `SITE_URL` | `http://localhost:8080` | Public URL — used for canonical links, sitemap and social cards |
| `JOB_TTL_SECONDS` | `3600` | Files are permanently deleted after this many seconds |
| `MAX_FILE_MB` / `MAX_TOTAL_MB` / `MAX_FILES` | `200` / `500` / `60` | Upload limits |
| `RATE_LIMIT_PER_MINUTE` | `40` | Jobs per client IP per minute |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For` (enable only behind your own reverse proxy) |
| `WORKERS` | CPU count | Parallel jobs |
| `BRAND_NAME` | `PDFVana` | Product name shown in the interface |

## 🔌 REST API

Every tool is available over HTTP. Interactive docs live at `/api/docs`.

```bash
# 1. create a job
curl -F tool=compress-pdf -F 'options={"level":"recommended"}' -F files=@report.pdf http://localhost:8080/api/jobs
# 2. poll it
curl http://localhost:8080/api/jobs/<id>
# 3. download the result
curl -OJ http://localhost:8080/api/jobs/<id>/download
```

See [docs/api.md](docs/api.md) for every tool id and option.

## 🏗️ Architecture

```
Browser (React · TypeScript · Tailwind · in-browser PDF previews)
   │  HTTPS: upload → job id → poll → download
   ▼
PDFVana engine (Python · FastAPI)                         Conversion service (internal)
  • job queue, progress, automatic deletion       ───►    office documents & web pages → PDF
  • PDF engine: geometry, stamping, layout analysis,
    Word/PowerPoint/Excel/Markdown writers, redaction
  • image, audio/video and data converters
  • OCR, compression, PDF/A
  • server-rendered SEO pages, sitemap.xml
```

More in [docs/architecture.md](docs/architecture.md).

## 🧪 Development

```bash
# backend with live reload of the mounted code
docker compose up -d converter
docker build --target engine -t pdfvana-engine .
docker run --rm -p 8080:8000 --network pdfvana_default -e CONVERTER_URL=http://converter:3000 \
  -v "$PWD/backend/app:/app/app" pdfvana-engine

# frontend with hot reload (proxies /api to :8080)
cd frontend && npm install && npm run dev        # http://localhost:5173

# full test suite (90+ end-to-end tests) against a running stack
docker build --target test -t pdfvana-test .
docker run --rm --network pdfvana_default -e BASE_URL=http://app:8000 pdfvana-test
```

## 🤝 Contributing

Contributions are welcome — bug reports, new tools, translations and docs. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get
started and [SECURITY.md](SECURITY.md) to report vulnerabilities privately.

## 📄 License

PDFVana is licensed under the [Apache License 2.0](LICENSE). Copyright © 2026 Divyakush (divyakush2006).

<div align="center">

**If PDFVana saves you time, please ⭐ star the repository — it helps others find it.**

</div>
