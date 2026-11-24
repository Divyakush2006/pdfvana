"""Security controls shared by the API and the processing engine.

* ``sanitize_html``   – neutralises uploaded HTML before the browser engine renders it
                        (no scripts, frames, refreshes, ``file:``/``javascript:`` URLs).
* ``check_upload``    – content sniffing so a file is what its extension claims
                        (e.g. a ".pdf" that is really PostScript is rejected).
* ``SlidingWindow``   – per-client rate limiting without external services.
* validators          – strict formats for user-supplied values passed to tools.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from .util import ToolError, ext_of

# --------------------------------------------------------------------------- HTML

_DANGEROUS_TAGS = {"script", "iframe", "frame", "frameset", "object", "embed", "applet", "base", "portal",
                   "noscript", "template"}
_URL_ATTRS = {"href", "src", "srcset", "action", "formaction", "data", "poster", "background", "cite",
              "longdesc", "lowsrc", "dynsrc", "manifest", "ping", "xlink:href", "{http://www.w3.org/1999/xlink}href"}
_BAD_SCHEME = re.compile(r"^\s*(javascript|vbscript|file|filesystem|blob|data\s*:\s*text/html)\s*:", re.I)
_CSS_FILE_URL = re.compile(r"""url\(\s*(['"]?)\s*(file|javascript|vbscript):[^)]*\)""", re.I)
_CSS_IMPORT_FILE = re.compile(r"""@import\s+(url\()?\s*['"]?\s*file:[^;]*;?""", re.I)


def _clean_css(css: str) -> str:
    css = _CSS_IMPORT_FILE.sub("", css)
    css = _CSS_FILE_URL.sub("url(about:blank)", css)
    return css.replace("expression(", "blocked(")


def sanitize_html(markup: str | bytes) -> str:
    """Remove active content from an HTML document while keeping its layout and styling.

    Uploaded HTML is rendered from a ``file://`` origin, where scripts, frames or meta refreshes
    could navigate to other local files. This strips every way of doing that.
    """
    import lxml.html
    from lxml import etree

    if isinstance(markup, bytes):
        text = None
        for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
            try:
                text = markup.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        markup = text or ""
    if not markup.strip():
        return "<!doctype html><html><body></body></html>"
    try:
        root = lxml.html.document_fromstring(markup)
    except (etree.ParserError, ValueError):
        return "<!doctype html><html><body></body></html>"
    for el in list(root.iter()):
        if not isinstance(el.tag, str):  # comments / processing instructions
            if isinstance(el, (etree._Comment, etree._ProcessingInstruction)) and el.getparent() is not None:
                el.getparent().remove(el)
            continue
        tag = el.tag.lower().split("}")[-1]
        if tag in _DANGEROUS_TAGS or (tag == "meta" and (el.get("http-equiv") or "").lower() in ("refresh", "set-cookie")) \
                or (tag == "link" and (el.get("rel") or "").lower() in ("import", "prerender", "prefetch")):
            parent = el.getparent()
            if parent is not None:
                el.drop_tree()
            continue
        if tag == "style" and el.text:
            el.text = _clean_css(el.text)
        for attr in list(el.attrib):
            low = attr.lower()
            value = el.attrib[attr]
            if low.startswith("on") or low in ("srcdoc", "formtarget"):
                del el.attrib[attr]
            elif low in _URL_ATTRS and (_BAD_SCHEME.search(value) or (low == "srcset" and re.search(r"file:|javascript:", value, re.I))):
                del el.attrib[attr]
            elif low == "style":
                el.attrib[attr] = _clean_css(value)
    return "<!doctype html>\n" + lxml.html.tostring(root, encoding="unicode", method="html")


# --------------------------------------------------------------------------- upload sniffing

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP = b"PK\x03\x04"
_ZIP_FORMATS = {"docx", "docm", "dotx", "dotm", "xlsx", "xlsm", "xltx", "pptx", "pptm", "ppsx", "potx",
                "odt", "ott", "ods", "ots", "odp", "otp", "odg", "otg", "epub", "pages", "numbers", "key", "vsdx", "ipynb_zip"}
_OLE_FORMATS = {"doc", "dot", "xls", "xlt", "ppt", "pps", "pot", "msg", "vsd", "pub"}


def check_upload(path: Path, name: str) -> None:
    """Reject files whose content contradicts their extension (cheap header checks)."""
    e = ext_of(name)
    with path.open("rb") as fh:
        head = fh.read(4096)
    if not head:
        raise ToolError(f"'{name}' is empty.")
    if e == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise ToolError(f"'{name}' is not a valid PDF file.")
    elif e in _ZIP_FORMATS:
        if not head.startswith(_ZIP):
            raise ToolError(f"'{name}' is not a valid .{e} file.")
    elif e in _OLE_FORMATS:
        if not (head.startswith(_OLE) or head.startswith(_ZIP)):
            raise ToolError(f"'{name}' is not a valid .{e} file.")
    # PostScript disguised as anything is never passed on.
    if head.lstrip()[:2] == b"%!" and e not in ("eps", "txt", "log"):
        raise ToolError(f"'{name}' contains PostScript code, which is not accepted.")


# --------------------------------------------------------------------------- validators

_TIME = re.compile(r"^(\d{1,2}:){0,2}\d{1,6}(\.\d{1,3})?$")


def media_time(value: object) -> str | None:
    """Validate a start/end time such as "75", "01:15" or "00:01:15.5"."""
    s = str(value or "").strip()
    if not s:
        return None
    if not _TIME.fullmatch(s):
        raise ToolError(f"'{s}' is not a valid time. Use seconds (75) or hh:mm:ss (00:01:15).")
    return s


# --------------------------------------------------------------------------- rate limiting

class SlidingWindow:
    """Thread-safe sliding-window counter per key (e.g. client IP)."""

    def __init__(self, limit: int, window: float = 60.0, max_keys: int = 100_000):
        self.limit, self.window, self.max_keys = limit, window, max_keys
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self.hits) > self.max_keys:
                for k in [k for k, v in self.hits.items() if not v or v[-1] <= now - self.window][: self.max_keys // 5]:
                    self.hits.pop(k, None)
            return True
