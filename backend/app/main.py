"""HTTP API, SEO-rendered pages and the static web app."""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile

from . import formats as F
from . import ops, seo
from .config import (BRAND_NAME, JOB_TTL_SECONDS, MAX_FILE_MB, MAX_FILES, MAX_TOTAL_MB, RATE_LIMIT_PER_MINUTE,
                     REPO_URL, SITE_URL, STATIC_DIR, TRUST_PROXY, VERSION)
from .jobs import Job, JobStore
from .tools import CATEGORIES, TOOLS, TOOLS_BY_ID, InputFile, coerce_options
from .util import ext_of, safe_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title=f"{BRAND_NAME} API", version=VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json",
              description=f"Programmatic access to every {BRAND_NAME} tool. Create a job, poll it, download the result.")
store = JobStore()
_hits: dict[str, deque] = defaultdict(deque)
_langs_cache: list[str] = []

LANG_NAMES = {
    "eng": "English", "hin": "Hindi", "ben": "Bengali", "tam": "Tamil", "tel": "Telugu", "mar": "Marathi", "guj": "Gujarati",
    "kan": "Kannada", "mal": "Malayalam", "pan": "Punjabi", "urd": "Urdu", "fra": "French", "deu": "German", "spa": "Spanish",
    "por": "Portuguese", "ita": "Italian", "nld": "Dutch", "rus": "Russian", "ukr": "Ukrainian", "pol": "Polish", "tur": "Turkish",
    "ara": "Arabic", "chi_sim": "Chinese (Simplified)", "chi_tra": "Chinese (Traditional)", "jpn": "Japanese", "kor": "Korean",
    "vie": "Vietnamese", "tha": "Thai", "ind": "Indonesian", "msa": "Malay", "swe": "Swedish", "ell": "Greek", "heb": "Hebrew",
    "ces": "Czech", "ron": "Romanian", "hun": "Hungarian", "nep": "Nepali", "san": "Sanskrit", "fas": "Persian",
}

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
       "script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob: data:; "
       "media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), interest-cohort=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not request.url.path.startswith("/api/docs"):
        h.setdefault("Content-Security-Policy", CSP)
    if SITE_URL.startswith("https://"):
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/assets/") and resp.status_code == 200:
        h["Cache-Control"] = "public, max-age=31536000, immutable"  # file names are content-hashed
    return resp


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_limit(request: Request) -> None:
    now = time.time()
    q = _hits[_client_ip(request)]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)
    if len(_hits) > 50_000:  # forget idle clients
        for k in [k for k, v in _hits.items() if not v or v[-1] < now - 60][:10_000]:
            _hits.pop(k, None)


@app.get("/api/health", tags=["system"])
def health():
    return {"ok": True, "version": VERSION, "jobs": store.stats()}


@app.get("/api/tools", tags=["tools"])
def list_tools():
    global _langs_cache
    if not _langs_cache:
        _langs_cache = ops.ocr_languages()
    langs = [{"value": l, "label": LANG_NAMES.get(l, l)} for l in _langs_cache]
    langs.sort(key=lambda c: (c["value"] != "eng", c["label"]))
    tools = []
    for t in TOOLS:
        d = t.public()
        for o in d["options"]:
            if o["id"] == "languages":
                o["choices"] = langs
        d["seo"] = seo.tool_seo(t)
        tools.append(d)
    return {
        "brand": BRAND_NAME, "version": VERSION, "repo": REPO_URL, "site": SITE_URL,
        "categories": CATEGORIES, "tools": tools,
        "formats": {k: {"label": v[0], "category": v[1]} for k, v in F.FORMATS.items()},
        "targets": F.TARGETS,
        "input_categories": {e: F.category(f"x.{e}") for e in sorted(F.all_input_ext())},
        "pairs": seo.pairs_public(),
        "ocr_languages": langs,
        "limits": {"max_file_mb": MAX_FILE_MB, "max_total_mb": MAX_TOTAL_MB, "max_files": MAX_FILES, "ttl_seconds": JOB_TTL_SECONDS},
    }


async def _save_upload(up: UploadFile, dest: Path, budget: list[int]) -> int:
    size = 0
    limit = MAX_FILE_MB * 1024 * 1024
    with dest.open("wb") as fh:
        while chunk := await up.read(1024 * 1024):
            size += len(chunk)
            budget[0] -= len(chunk)
            if size > limit:
                raise HTTPException(413, f"'{up.filename}' is larger than {MAX_FILE_MB} MB.")
            if budget[0] < 0:
                raise HTTPException(413, f"Total upload is larger than {MAX_TOTAL_MB} MB.")
            fh.write(chunk)
    return size


def _accepts(tool, name: str) -> bool:
    return "*" in tool.accept or ext_of(name) in tool.accept


@app.post("/api/jobs", tags=["jobs"])
async def create_job(request: Request):
    """Multipart form: ``tool`` (id), ``options`` (JSON), ``files`` (one or more), optional ``extra_<id>`` files."""
    _rate_limit(request)
    form = await request.form(max_files=MAX_FILES + 5, max_fields=50, max_part_size=1024 * 1024)
    tool = TOOLS_BY_ID.get(str(form.get("tool", "")))
    if not tool:
        raise HTTPException(400, "Unknown tool.")
    try:
        raw_opts = json.loads(str(form.get("options") or "{}"))
        if not isinstance(raw_opts, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Invalid options.") from None

    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    if len(uploads) > MAX_FILES:
        raise HTTPException(400, f"You can process up to {MAX_FILES} files at once.")
    if len(uploads) < tool.min_files:
        raise HTTPException(400, f"Please add at least {tool.min_files} file(s).")
    if tool.max_files and len(uploads) > tool.max_files:
        raise HTTPException(400, f"This tool accepts at most {tool.max_files} files.")
    for up in uploads:
        if not _accepts(tool, up.filename or ""):
            raise HTTPException(400, f"'{up.filename}' is not a supported file type for {tool.name}.")

    jid, jdir = store.new_dir()
    budget = [MAX_TOTAL_MB * 1024 * 1024]
    inputs: list[InputFile] = []
    extras: dict[str, InputFile] = {}
    total = 0
    try:
        for i, up in enumerate(uploads):
            name = safe_name(up.filename or f"file{i}")
            dest = jdir / "in" / f"{i:03d}_{name}"
            total += await _save_upload(up, dest, budget)
            inputs.append(InputFile(dest, name))
        for ex in tool.extra_files:
            up = form.get(f"extra_{ex.id}")
            if isinstance(up, UploadFile) and up.filename:
                name = safe_name(up.filename)
                dest = jdir / "in" / f"extra_{ex.id}_{name}"
                await _save_upload(up, dest, budget)
                extras[ex.id] = InputFile(dest, name)
    except HTTPException:
        shutil.rmtree(jdir, ignore_errors=True)
        raise

    job = Job(jid, tool.id, jdir, inputs, extras, coerce_options(tool, raw_opts), input_bytes=total)
    store.submit(job)
    return job.public()


@app.get("/api/jobs/{jid}", tags=["jobs"])
def job_status(jid: str):
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "This job has expired or does not exist.")
    return job.public()


def _ascii_name(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r'[^\w.\- ()]+', "_", plain).strip() or "download"


@app.get("/api/jobs/{jid}/download", tags=["jobs"])
def job_download(jid: str, inline: bool = False):
    job = store.get(jid)
    if not job or job.status != "done" or not job.result or not job.result.exists():
        raise HTTPException(404, "File not available. It may have expired.")
    name = job.result.name
    disp = "inline" if inline else "attachment"
    return FileResponse(job.result, headers={
        "Content-Disposition": f"{disp}; filename=\"{_ascii_name(name)}\"; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "no-store"})


@app.delete("/api/jobs/{jid}", tags=["jobs"])
def job_delete(jid: str):
    store.delete(jid)
    return {"deleted": True}


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap():
    return Response(seo.sitemap_xml(), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse(seo.robots_txt(), headers={"Cache-Control": "public, max-age=3600"})


# ---------------------------------------------------------------- web app with server-rendered SEO
_template: str | None = None


def _render(path: str) -> HTMLResponse:
    global _template
    if _template is None:
        _template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    meta = seo.page_meta(path)
    status = 200
    if meta is None:
        status = 404
        meta = {"title": f"Page not found — {BRAND_NAME}", "description": seo.HOME_DESC, "h1": "Page not found",
                "intro": "This page doesn't exist. Find every tool on the home page.", "canonical": SITE_URL.rstrip("/") + "/",
                "steps": [], "faqs": [], "kind": "page"}
    page = re.sub(r"<title>.*?</title>", "", _template, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>', "", page, count=1)
    page = page.replace("<!--seo-head-->", seo.head_html(meta)).replace("<!--seo-body-->", seo.body_html(meta))
    headers = {"Cache-Control": "no-cache"}
    if status == 404:
        headers["X-Robots-Tag"] = "noindex"
    return HTMLResponse(page, status_code=status, headers=headers)


if (STATIC_DIR / "index.html").exists():
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        target = (STATIC_DIR / path).resolve()
        if path and target.is_file() and STATIC_DIR.resolve() in target.parents:
            # un-hashed public files (theme.js, icons, manifest) must pick up new releases quickly
            return FileResponse(target, headers={"Cache-Control": "public, max-age=600, must-revalidate"})
        return _render(path)
