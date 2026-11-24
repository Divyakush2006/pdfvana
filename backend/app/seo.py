"""Search-engine optimisation: per-page titles, descriptions, FAQs, structured
data, server-rendered content, sitemap.xml and robots.txt."""
from __future__ import annotations

import html
import json
from datetime import date
from functools import lru_cache

from . import formats as F
from .config import BRAND_NAME, SITE_URL, JOB_TTL_SECONDS
from .tools import CATEGORIES, TOOLS, TOOLS_BY_ID

TAGLINE = "Free PDF, image, video & document converter"
HOME_TITLE = f"{BRAND_NAME} — Free PDF Tools & Universal File Converter (No Sign-up)"
HOME_DESC = ("Merge, split, compress and convert PDF, Word, Excel, PowerPoint, images, audio and video. 100% free, "
             "no sign-up, no watermarks, no limits. Files are deleted automatically.")
LABELS = {"jpg": "JPG", "jpeg": "JPG", "heic": "HEIC", "md": "Markdown", "pdf": "PDF", "svg": "SVG", "ico": "ICO",
          "csv": "CSV", "json": "JSON", "xlsx": "Excel", "docx": "Word", "pptx": "PowerPoint", "odt": "ODT",
          "epub": "EPUB", "txt": "Text", "html": "HTML", "rtf": "RTF", "tiff": "TIFF", "webp": "WebP", "avif": "AVIF"}


def label(ext: str) -> str:
    return LABELS.get(ext, ext.upper())


def _minutes() -> int:
    return max(1, round(JOB_TTL_SECONDS / 60))


def tool_seo(tool) -> dict:
    name = tool.name
    title = f"{name} Online — Free, Fast & Secure | {BRAND_NAME}"
    desc = f"{tool.description} Free, no sign-up, no watermarks. Files deleted after {_minutes()} minutes."
    noun = "files" if tool.multiple else "file"
    steps = [
        f"Upload your {noun} — drag and drop or click “Select {noun}”.",
        "Adjust the options if you like; the defaults give great results.",
        f"Click “{tool.cta}” and download your result in seconds.",
    ]
    faqs = [
        (f"Is {name} really free?", f"Yes. {BRAND_NAME} is free and open source, with no sign-up, no watermarks and no daily limits."),
        ("Are my files safe?", f"Files are processed in isolation, never shared and permanently deleted after {_minutes()} minutes — "
                               "or instantly with “Delete now”. The source code is public, so anyone can verify it."),
        ("Do I need to install anything?", f"No. {name} works in any modern browser on Windows, macOS, Linux, Android and iPhone."),
        ("Which file types are supported?", "Any: " if "*" in tool.accept else
         "This tool accepts " + ", ".join(sorted({label(a) for a in tool.accept})[:18]) + "."),
    ]
    if "*" in tool.accept:
        faqs[3] = ("Which file types are supported?", "PDF, Word, Excel, PowerPoint, OpenDocument, Pages, Keynote, images "
                   "(JPG, PNG, WebP, HEIC, SVG and more), e-books, Markdown, HTML, e-mails, audio and video.")
    return {"title": title, "description": _clip(desc), "h1": name, "intro": tool.description, "steps": steps,
            "faqs": [{"q": q, "a": a} for q, a in faqs]}


# Conversion pages name the exact file format people search for ("docx to pdf"); tool pages use the friendly name.
PAIR_LABELS = {"docx": "DOCX", "doc": "DOC", "pptx": "PPTX", "ppt": "PPT"}
FRIENDLY = {"docx": "Microsoft Word", "doc": "Word 97–2003", "pptx": "PowerPoint", "ppt": "PowerPoint 97–2003",
            "odt": "OpenDocument Text"}
WORD_LIKE = {"docx", "doc", "odt", "rtf", "txt"}
SLIDES_LIKE = {"pptx", "ppt", "odp"}
EDITABLE = {"docx", "pptx", "odt", "rtf"}


def pair_label(ext: str) -> str:
    return PAIR_LABELS.get(ext) or label(ext)


def _named(ext: str) -> str:
    """'DOCX (Microsoft Word)' for formats whose extension alone may not ring a bell."""
    return f"{pair_label(ext)} ({FRIENDLY[ext]})" if ext in FRIENDLY else pair_label(ext)


def related_tool(src: str, dst: str) -> str | None:
    """The dedicated tool with more options for this conversion, linked from the conversion page."""
    if dst == "pdf":
        if src in WORD_LIKE:
            return "word-to-pdf"
        if src in SLIDES_LIKE:
            return "powerpoint-to-pdf"
        if src in F.SHEET_EXT | F.DATA_EXT:
            return "excel-to-pdf"
        if src in F.IMAGE_EXT:
            return "jpg-to-pdf"
        return "any-to-pdf"
    if src == "pdf":
        return {"docx": "pdf-to-word", "pptx": "pdf-to-powerpoint", "xlsx": "pdf-to-excel", "png": "pdf-to-jpg",
                "jpg": "pdf-to-jpg", "tiff": "pdf-to-jpg", "txt": "pdf-to-text", "html": "pdf-to-text",
                "epub": "pdf-to-text", "md": "pdf-to-markdown", "svg": "pdf-to-svg"}.get(dst)
    return None


def _document_pair(src: str, dst: str) -> dict | None:
    """Copy for Office <-> PDF pages, which need different answers than image or media conversions."""
    a, b = pair_label(src), pair_label(dst)
    to_pdf = dst == "pdf" and (src in WORD_LIKE or src in SLIDES_LIKE)
    from_pdf = src == "pdf" and dst in EDITABLE
    if not (to_pdf or from_pdf):
        return None
    slides = src in SLIDES_LIKE or dst in SLIDES_LIKE
    unit = "presentations" if slides else "documents"
    if to_pdf:
        intro = (f"Turn {_named(src)} {unit} into PDF files that look the same on every device — "
                 "free, private and with no watermark.")
        desc = (f"Convert {a} to PDF online for free. Fonts, images, tables and page layout are kept exactly. "
                f"Batch conversion, no sign-up, no watermark; files deleted after {_minutes()} minutes.")
        faqs = [
            (f"How do I convert {a} to PDF?", f"Upload your {a} file, keep PDF selected as the output and click Convert. "
                                              "The PDF is ready to download in seconds."),
            ("Will my formatting stay the same?",
             ("Yes. Every slide becomes one PDF page with its images, shapes, charts and text in place."
              if slides else
              "Yes. Fonts, images, tables, headers, footers and page breaks are kept. Common Microsoft fonts are replaced "
              "with metric-compatible fonts, so lines and pages break in the same places.")),
            (f"Can I convert several {a} files at once?", "Yes. Add as many as you like; you get one PDF per file, "
                                                          "downloaded together as a ZIP."),
            (f"Is the {a} to PDF converter free?", "Yes — completely free and open source, with no sign-up, "
                                                   "no watermarks and no daily limits."),
            ("Are my files private?", f"Yes. Files are processed in isolation, never shared and permanently deleted "
                                      f"after {_minutes()} minutes."),
        ]
    else:
        what = "editable slides with real text boxes" if dst == "pptx" else "an editable document"
        intro = f"Turn PDFs into {what} you can change in {FRIENDLY.get(dst, b)} — free, private and with no watermark."
        desc = (f"Convert PDF to {a} online for free: editable text with layout, tables and images preserved. "
                f"No sign-up, no watermark; files deleted after {_minutes()} minutes.")
        scanned = ("Scanned pages are kept as images on each slide, so they look exactly like the original."
                   if dst == "pptx" else
                   "Scanned pages are detected automatically and run through text recognition (OCR) first, "
                   "so their text is editable too.")
        faqs = [
            (f"How do I convert PDF to {a}?", f"Upload the PDF, keep {a} selected as the output and click Convert. "
                                              f"Open the {a} file in {FRIENDLY.get(dst, b)}, Google "
                                              f"{'Slides' if dst == 'pptx' else 'Docs'} or LibreOffice."),
            ("Can I edit the converted file?", f"Yes. Text comes out as real, editable "
                                               f"{'text boxes' if dst == 'pptx' else 'paragraphs'}, with headings, "
                                               "tables and images kept in place."),
            ("What about scanned PDFs?", scanned),
            (f"Is the PDF to {a} converter free?", "Yes — completely free and open source, with no sign-up, "
                                                   "no watermarks and no daily limits."),
            ("Are my files private?", f"Yes. Files are processed in isolation, never shared and permanently deleted "
                                      f"after {_minutes()} minutes."),
        ]
    steps = [f"Upload your {a} files — add several to convert them in one go.",
             f"{b} is already selected as the output format.",
             f"Click “Convert” and download your {b} file (or a ZIP when you convert several)."]
    return {"title": f"{a} to {b} Converter — Free, Accurate, No Sign-up | {BRAND_NAME}", "description": _clip(desc),
            "h1": f"{a} to {b} Converter", "intro": intro, "steps": steps,
            "faqs": [{"q": q, "a": x} for q, x in faqs]}


def pair_seo(src: str, dst: str) -> dict:
    doc = _document_pair(src, dst)
    if doc:
        return doc
    a, b = pair_label(src), pair_label(dst)
    title = f"{a} to {b} Converter — Free, Unlimited, No Sign-up | {BRAND_NAME}"
    desc = (f"Convert {a} to {b} online for free. High quality, batch conversion, no watermarks and no sign-up. "
            f"Files are deleted automatically after {_minutes()} minutes.")
    steps = [f"Upload your {a} files (you can add several at once).",
             f"{b} is already selected — adjust quality or size if you want.",
             f"Click “Convert” and download your {b} files."]
    faqs = [
        (f"How do I convert {a} to {b}?", f"Upload the {a} file, keep {b} selected as the output and click Convert. "
                                          "The result is ready in seconds."),
        (f"Is the {a} to {b} converter free?", "Yes — completely free, with no sign-up, no watermarks and no daily limits."),
        (f"Will the quality of my {a} change?", "We use high-quality settings by default and keep the original resolution "
                                                 "unless you choose to resize or compress."),
        ("Can I convert many files at once?", "Yes. Add as many files as you like; they are converted together and "
                                               "downloaded as one ZIP."),
        ("Are my files private?", f"Yes. Files are never shared and are permanently deleted after {_minutes()} minutes."),
    ]
    return {"title": title, "description": _clip(desc), "h1": f"{a} to {b} Converter",
            "intro": f"Convert {a} files to {b} in seconds — free, private and unlimited.", "steps": steps,
            "faqs": [{"q": q, "a": x} for q, x in faqs]}


def _clip(s: str, n: int = 158) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


@lru_cache(maxsize=1)
def pairs_public() -> list[dict]:
    out = []
    for a, b in F.PAIRS:
        rel = related_tool(a, b)
        out.append({"slug": F.pair_slug(a, b), "from": a, "to": b, "accept": F.pair_accept(a), **pair_seo(a, b),
                    "related": {"slug": rel, "name": TOOLS_BY_ID[rel].name} if rel in TOOLS_BY_ID else None})
    return out


def page_meta(path: str) -> dict | None:
    """SEO data for a URL path, or None for an unknown page (served as 404)."""
    slug = path.strip("/").split("?")[0]
    base = SITE_URL.rstrip("/")
    if slug == "":
        return {"title": HOME_TITLE, "description": HOME_DESC, "h1": "Every PDF, image, video and document tool — free.",
                "intro": HOME_DESC, "canonical": base + "/", "steps": [], "faqs": [], "kind": "home"}
    if slug == "privacy":
        return {"title": f"Privacy & Security — {BRAND_NAME}", "description": f"How {BRAND_NAME} protects your files: no "
                "account, automatic deletion, isolated processing, no trackers, open source.", "h1": "Privacy & security",
                "intro": "", "canonical": f"{base}/privacy", "steps": [], "faqs": [], "kind": "page"}
    if slug in TOOLS_BY_ID:
        m = tool_seo(TOOLS_BY_ID[slug])
        m.update(canonical=f"{base}/{slug}", kind="tool", tool=slug)
        return m
    for p in pairs_public():
        if p["slug"] == slug:
            return {**p, "canonical": f"{base}/{slug}", "kind": "pair", "tool": "convert"}
    return None


def jsonld(meta: dict) -> str:
    base = SITE_URL.rstrip("/")
    graph: list[dict] = [{
        "@type": "WebApplication", "name": meta["h1"] if meta["kind"] != "home" else BRAND_NAME,
        "url": meta["canonical"], "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any",
        "browserRequirements": "Requires JavaScript", "isAccessibleForFree": True, "description": meta["description"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "publisher": {"@type": "Organization", "name": BRAND_NAME, "url": base + "/"},
    }]
    if meta["kind"] == "home":
        graph.append({"@type": "WebSite", "name": BRAND_NAME, "url": base + "/",
                      "potentialAction": {"@type": "SearchAction", "target": base + "/?q={search_term_string}",
                                          "query-input": "required name=search_term_string"}})
    else:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": BRAND_NAME, "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": meta["h1"], "item": meta["canonical"]}]})
    if meta.get("faqs"):
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in meta["faqs"]]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")


def head_html(meta: dict) -> str:
    e = html.escape
    t, d, c = e(meta["title"]), e(meta["description"]), e(meta["canonical"])
    img = e(SITE_URL.rstrip("/") + "/og-image.png")
    return (
        f"<title>{t}</title>\n<meta name=\"description\" content=\"{d}\" />\n<link rel=\"canonical\" href=\"{c}\" />\n"
        f"<meta property=\"og:type\" content=\"website\" />\n<meta property=\"og:site_name\" content=\"{e(BRAND_NAME)}\" />\n"
        f"<meta property=\"og:title\" content=\"{t}\" />\n<meta property=\"og:description\" content=\"{d}\" />\n"
        f"<meta property=\"og:url\" content=\"{c}\" />\n<meta property=\"og:image\" content=\"{img}\" />\n"
        f"<meta name=\"twitter:card\" content=\"summary_large_image\" />\n<meta name=\"twitter:title\" content=\"{t}\" />\n"
        f"<meta name=\"twitter:description\" content=\"{d}\" />\n<meta name=\"twitter:image\" content=\"{img}\" />\n"
        f"<script type=\"application/ld+json\">{jsonld(meta)}</script>"
    )


def body_html(meta: dict) -> str:
    """Readable content for crawlers and for the first paint; React replaces it once loaded."""
    e = html.escape
    parts = [f"<main class=\"ssr\"><h1>{e(meta['h1'])}</h1><p>{e(meta['intro'])}</p>"]
    if meta["kind"] == "home":
        for cat in CATEGORIES:
            items = [t for t in TOOLS if t.category == cat["id"]]
            if items:
                parts.append(f"<h2>{e(cat['name'])}</h2><ul>" + "".join(
                    f"<li><a href=\"/{t.id}\">{e(t.name)}</a> — {e(t.description)}</li>" for t in items) + "</ul>")
        parts.append("<h2>Popular conversions</h2><ul>" + "".join(
            f"<li><a href=\"/{p['slug']}\">{e(p['h1'])}</a></li>" for p in pairs_public()) + "</ul>")
    if meta.get("steps"):
        parts.append("<h2>How it works</h2><ol>" + "".join(f"<li>{e(s)}</li>" for s in meta["steps"]) + "</ol>")
    if meta.get("faqs"):
        parts.append("<h2>Frequently asked questions</h2>" + "".join(
            f"<h3>{e(f['q'])}</h3><p>{e(f['a'])}</p>" for f in meta["faqs"]))
    if meta.get("related"):
        r = meta["related"]
        parts.append(f"<p>Need more options? Try <a href=\"/{e(r['slug'])}\">{e(r['name'])}</a>.</p>")
    parts.append(f"<p class=\"ssr-loading\">Loading {e(BRAND_NAME)}…</p></main>")
    return "".join(parts)


def sitemap_xml() -> str:
    base = SITE_URL.rstrip("/")
    today = date.today().isoformat()
    urls = [("/", "1.0", "daily")] + [(f"/{t.id}", "0.9", "weekly") for t in TOOLS] + \
           [(f"/{p['slug']}", "0.8", "weekly") for p in pairs_public()] + [("/privacy", "0.3", "yearly")]
    body = "".join(f"<url><loc>{base}{u}</loc><lastmod>{today}</lastmod><changefreq>{f}</changefreq><priority>{p}</priority></url>"
                   for u, p, f in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'


def robots_txt() -> str:
    return f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {SITE_URL.rstrip('/')}/sitemap.xml\n"
