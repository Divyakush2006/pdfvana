# Security architecture & threat model

PDFVana accepts arbitrary files from anonymous users and processes them with powerful document, image and media engines.
This document lists the threats considered and the control in the code that addresses each one. Every control below is
covered by an automated test in [`tests/test_security.py`](../tests/test_security.py) or [`tests/test_unit.py`](../tests/test_unit.py).

## Trust boundaries

```
Internet ──► Reverse proxy (TLS) ──► API (FastAPI) ──► isolated job process ──► local tools (Ghostscript, ffmpeg, …)
                                                   └──► conversion service (internal network only)
```

The API never trusts file names, file contents, option values or headers. The conversion service is never reachable from
the internet and only ever receives sanitised input.

## Threats and controls

| Threat | Control | Where |
|---|---|---|
| SQL / NoSQL injection | No database exists; state is in memory and in per-job temporary folders | — |
| OS command injection | Tools are invoked with argument lists, never a shell; no user string is ever a command | `util.run` |
| Argument injection | Paths are absolute and internally generated; times, formats, languages and page ranges are validated; options are coerced to the declared type, clamped and restricted to allowed choices; unknown options are dropped | `security.media_time`, `tools.coerce_options`, `util.parse_pages` |
| Path traversal | File names are normalised and stripped of directories; job ids must be 32 hex chars; static files are resolved inside the web root only | `util.safe_name`, `main._job`, `main.spa` |
| Malicious PDF / PostScript | Uploads must start with `%PDF-`; PostScript is refused everywhere; Ghostscript runs with `-dSAFER` | `security.check_upload`, `ops` |
| Disguised Office files | OOXML/ODF must be ZIP containers, legacy Office must be OLE | `security.check_upload` |
| Malicious media (HLS/concat SSRF & file read) | `ffprobe` demuxer allowlist; `-protocol_whitelist file`; strict time format; duration limit; GIF length cap | `media.probe`, `media.convert_media` |
| HTML: local file disclosure via `file://`, scripts, frames, meta refresh, CSS imports | Server-side sanitiser removes active content and dangerous URL schemes before rendering | `security.sanitize_html`, `convert.html_to_pdf` |
| Markup includes (Pandoc) | Pandoc runs with `--sandbox` (no file or network access) for user documents | `convert._pandoc_to_html`, `tools.convert_any` |
| XXE / billion laughs | `defusedxml` for spreadsheets; Word/PowerPoint parsers disable entity resolution; SVG parsed with `unsafe=False` | requirements, `media.svg_to_png` |
| Decompression bombs | Pillow pixel limit; render-size cap for PDFs; per-job memory ceiling | `media`, `engine.raster.render`, `worker` |
| SSRF (URL → PDF / screenshot) | Host resolved and every address must be public; schemes limited to http(s); the conversion service denies private IPs with DNS pinning | `convert.check_public_url`, compose config |
| Stored XSS via results | Only passive formats may be displayed inline; everything else is a forced download with a `sandbox` CSP and `nosniff` | `main.job_download` |
| Cross-site request forgery / drive-by abuse | Browser requests from other origins cannot create or delete jobs | `main._same_origin` |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `main.security_headers` |
| Resource exhaustion (CPU / memory) | Each job in its own process: memory ceiling, output-size limit, wall-clock timeout, process-group kill | `worker` |
| Upload flooding | Streaming body limit before buffering (incl. chunked uploads); per-file and total size limits; concurrent-upload cap | `main.BodyLimit`, `main._save_upload` |
| Request flooding | Per-client sliding-window limits for jobs and all API calls; per-client active-job cap; global backlog cap; uvicorn connection limits | `security.SlidingWindow`, `jobs.check_capacity` |
| Disk exhaustion | Free-space guard before accepting jobs; per-job output cap; automatic deletion | `main._admit`, `worker`, `jobs._janitor` |
| Information disclosure | Generic error messages to users, details only in server logs; no server banner; no stack traces in responses | `jobs`, Dockerfile |
| Container escape / lateral movement | Non-root user, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, pids and memory limits | Dockerfile, compose files |
| Supply chain | Checksum-verified Pandoc download; Dependabot; pip-audit & npm audit; Trivy image scan; CodeQL; OpenSSF Scorecard; protected `main` with required checks | `.github/` |
| Data retention | Inputs deleted when processing ends, results after `JOB_TTL_SECONDS`, everything wiped on start | `jobs` |

## Operating securely

- Run behind a TLS reverse proxy (see `deploy/`) and set `SITE_URL` to the `https://` address and `TRUST_PROXY=true`.
- Tune limits with environment variables: `RATE_LIMIT_PER_MINUTE`, `API_RATE_LIMIT_PER_MINUTE`, `MAX_ACTIVE_JOBS_PER_CLIENT`,
  `MAX_QUEUED_JOBS`, `JOB_TIMEOUT_SECONDS`, `JOB_MEMORY_MB`, `MAX_FILE_MB`, `MAX_TOTAL_MB`, `MIN_FREE_DISK_MB`, `MAX_MEDIA_MINUTES`.
- For very large public deployments add a network-level DDoS shield in front (any CDN with free DDoS protection works); the
  application-level limits above handle abuse from individual clients.
- Keep images updated — Dependabot and the scheduled security workflow flag outdated or vulnerable components.
