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


def pair_seo(src: str, dst: str) -> dict:
    a, b = label(src), label(dst)
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
    return [{"slug": F.pair_slug(a, b), "from": a, "to": b, "accept": F.pair_accept(a), **pair_seo(a, b)} for a, b in F.PAIRS]


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
