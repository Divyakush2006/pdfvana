# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-11-24

### Security
- Every job runs in an isolated process with memory, output-size and wall-clock limits; the whole process tree is killed on timeout.
- Streaming upload limit enforced before buffering; per-client job and API rate limits; per-client and global job caps;
  concurrent-upload cap; free-disk guard; render-size and media-length caps.
- Uploads are content-verified (PostScript disguised as PDF and fake Office files are refused); ffmpeg only opens real local media.
- Uploaded HTML is sanitised before rendering; Pandoc runs in sandbox mode; XML parsing is hardened.
- Cross-site job submission refused; active result types are never rendered inline and downloads are sandboxed.
- Read-only containers with all capabilities dropped; checksum-verified build downloads.
- CodeQL, dependency audit, container scanning and OpenSSF Scorecard workflows; 29 new security tests; threat model docs.

### Changed
- Upgraded to React 19, React Router 7, pdf.js 6, Vite 8, TypeScript 7 and the latest Python libraries; web app built on Node 26.

## [1.0.0] — 2026-11-24

First public release.

### Added
- 49 tools across workflows, PDF organisation, optimisation, conversion, editing, security, images and audio/video.
- **Document Studio**: merge any mix of files, apply steps (compress, OCR, watermark, page numbers, header/footer, rotate,
  remove pages, grayscale, flatten, sanitize, password) and export to any document format.
- **Universal Converter** with 2,600+ format combinations across documents, images, audio, video and data, plus dedicated
  landing pages for popular conversions.
- PDF engine with rotation-aware stamping, layout analysis and native Word, PowerPoint, Excel and Markdown writers.
- Image tools: converter (incl. HEIC, AVIF, ICO, SVG tracing), compression to an exact size, resize/rotate, favicon generator,
  metadata removal, website screenshots.
- Audio & video: converters, video to GIF, video compression, trimming.
- Permanent redaction with automatic detection of e-mails, phone, card, Aadhaar and PAN numbers.
- OCR in 28 languages including major Indian scripts.
- Server-rendered SEO pages, structured data, sitemap and robots.txt.
- REST API with OpenAPI docs, Docker images and a production deployment with automatic HTTPS.
