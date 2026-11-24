"""Every input and output format PDFVana understands, grouped by category,
plus the popular "X to Y" conversion pairs that get their own landing pages."""
from __future__ import annotations

from .util import ext_of

IMAGE_EXT = {"jpg", "jpeg", "jfif", "png", "webp", "bmp", "tif", "tiff", "gif", "heic", "heif", "avif", "ico", "svg", "tga", "ppm", "psd"}
AUDIO_EXT = {"mp3", "wav", "ogg", "oga", "opus", "flac", "m4a", "aac", "wma", "aiff", "aif", "amr", "weba"}
VIDEO_EXT = {"mp4", "m4v", "mov", "mkv", "webm", "avi", "wmv", "flv", "3gp", "mpeg", "mpg", "ts", "mts", "ogv"}
DATA_EXT = {"csv", "tsv", "json", "jsonl"}
SHEET_EXT = {"xlsx", "xls", "xlsm", "ods"}
PANDOC_EXT = {
    "md": "markdown", "markdown": "markdown", "rst": "rst", "org": "org", "ipynb": "ipynb",
    "tex": "latex", "latex": "latex", "fb2": "fb2", "textile": "textile", "wiki": "mediawiki",
    "mediawiki": "mediawiki", "epub": "epub", "dbk": "docbook", "opml": "opml", "typ": "typst",
    "adoc": "asciidoc", "asciidoc": "asciidoc", "djot": "djot",
}
HTML_EXT = {"html", "htm", "xhtml"}
CODE_EXT = {
    "log", "yaml", "yml", "toml", "ini", "cfg", "conf", "py", "js", "mjs", "ts", "tsx", "jsx",
    "java", "kt", "c", "h", "cpp", "hpp", "cc", "cs", "go", "rs", "rb", "php", "swift", "sh", "bash",
    "ps1", "bat", "sql", "css", "scss", "r", "m", "lua", "pl", "dart", "scala", "vue", "svelte", "env",
}
OFFICE_EXT = {
    "doc", "docx", "docm", "dot", "dotx", "dotm", "odt", "ott", "fodt", "rtf", "txt", "wpd", "wps", "pages",
    "xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "ods", "ots", "fods", "numbers", "dbf", "dif", "slk",
    "ppt", "pptx", "pptm", "pps", "ppsx", "pot", "potx", "odp", "otp", "fodp", "key",
    "odg", "otg", "fodg", "vsd", "vsdx", "vsdm", "pub", "cdr", "emf", "wmf", "eps",
    "xml", "sxw", "sxc", "sxi", "sxd", "hwp", "lwp", "abw", "zabw", "cwk", "mcw", "uot", "uos", "uop",
}

# label, category
FORMATS: dict[str, tuple[str, str]] = {
    "pdf": ("PDF", "document"), "pdfa": ("PDF/A (archival)", "document"), "docx": ("Word (.docx)", "document"),
    "odt": ("OpenDocument (.odt)", "document"), "rtf": ("Rich Text (.rtf)", "document"),
    "pptx": ("PowerPoint (.pptx)", "document"), "txt": ("Plain text", "document"), "md": ("Markdown", "document"),
    "html": ("HTML web page", "document"), "epub": ("EPUB e-book", "document"),
    "xlsx": ("Excel (.xlsx)", "data"), "csv": ("CSV", "data"), "json": ("JSON", "data"),
    "jpg": ("JPG", "image"), "png": ("PNG", "image"), "webp": ("WebP", "image"), "avif": ("AVIF", "image"),
    "gif": ("GIF", "image"), "bmp": ("BMP", "image"), "tiff": ("TIFF", "image"), "ico": ("ICO icon", "image"),
    "svg": ("SVG vector", "image"),
    "mp3": ("MP3", "audio"), "wav": ("WAV", "audio"), "ogg": ("OGG", "audio"), "opus": ("Opus", "audio"),
    "flac": ("FLAC", "audio"), "m4a": ("M4A (AAC)", "audio"),
    "mp4": ("MP4", "video"), "webm": ("WebM", "video"), "mov": ("MOV", "video"), "mkv": ("MKV", "video"),
    "avi": ("AVI", "video"),
}

DOC_TARGETS = ["pdf", "pdfa", "docx", "odt", "rtf", "pptx", "xlsx", "csv", "json", "txt", "md", "html", "epub",
               "jpg", "png", "webp", "tiff", "svg"]
IMAGE_TARGETS = ["jpg", "png", "webp", "avif", "gif", "bmp", "tiff", "ico", "svg", "pdf", "docx", "txt"]
TARGETS = {
    "document": DOC_TARGETS,
    "spreadsheet": ["pdf", "xlsx", "csv", "json", "html", "md", "jpg", "png"],
    "data": ["xlsx", "csv", "json", "html", "md", "pdf"],
    "image": IMAGE_TARGETS,
    "animation": IMAGE_TARGETS + ["mp4", "webm", "mov"],  # animated GIF
    "audio": ["mp3", "wav", "ogg", "opus", "flac", "m4a"],
    "video": ["mp4", "webm", "mov", "mkv", "avi", "gif", "mp3", "wav", "m4a"],
}


def category(name: str) -> str:
    e = ext_of(name)
    if e == "gif":
        return "animation"
    if e in IMAGE_EXT:
        return "image"
    if e in AUDIO_EXT:
        return "audio"
    if e in VIDEO_EXT:
        return "video"
    if e in DATA_EXT:
        return "data"
    if e in SHEET_EXT:
        return "spreadsheet"
    return "document"


def all_input_ext() -> set[str]:
    return ({"pdf", "eml"} | IMAGE_EXT | AUDIO_EXT | VIDEO_EXT | DATA_EXT | SHEET_EXT | set(PANDOC_EXT) | HTML_EXT
            | CODE_EXT | OFFICE_EXT)


# Popular conversions, each served at /<from>-to-<to> with its own title and description.
PAIRS: list[tuple[str, str]] = [
    ("jpg", "png"), ("png", "jpg"), ("webp", "jpg"), ("webp", "png"), ("heic", "jpg"), ("heic", "png"),
    ("png", "webp"), ("jpg", "webp"), ("avif", "jpg"), ("avif", "png"), ("png", "avif"), ("jpg", "avif"),
    ("png", "ico"), ("jpg", "ico"), ("svg", "ico"), ("png", "svg"), ("jpg", "svg"), ("svg", "png"), ("svg", "jpg"),
    ("gif", "png"), ("gif", "jpg"), ("bmp", "jpg"), ("bmp", "png"), ("tiff", "jpg"), ("tiff", "png"),
    ("jpg", "gif"), ("png", "gif"), ("webp", "gif"), ("gif", "webp"),
    ("mp4", "mp3"), ("mp4", "gif"), ("gif", "mp4"), ("mov", "mp4"), ("mkv", "mp4"), ("webm", "mp4"),
    ("avi", "mp4"), ("mp4", "webm"), ("mov", "gif"), ("webm", "mp3"), ("mov", "mp3"),
    ("wav", "mp3"), ("m4a", "mp3"), ("flac", "mp3"), ("ogg", "mp3"), ("mp3", "wav"), ("aac", "mp3"),
    ("opus", "mp3"), ("mp3", "ogg"), ("wma", "mp3"),
    ("csv", "xlsx"), ("xlsx", "csv"), ("json", "csv"), ("csv", "json"), ("json", "xlsx"), ("xlsx", "json"),
    ("pdf", "svg"), ("pdf", "png"), ("pdf", "txt"), ("pdf", "epub"), ("pdf", "html"), ("pdf", "tiff"),
    ("epub", "pdf"), ("md", "pdf"), ("txt", "pdf"), ("tiff", "pdf"), ("heic", "pdf"), ("svg", "pdf"),
    ("docx", "odt"), ("odt", "docx"), ("docx", "md"), ("md", "docx"), ("html", "docx"), ("rtf", "docx"),
    ("pptx", "png"), ("docx", "jpg"), ("xlsx", "pdf"), ("csv", "pdf"),
]


def pair_slug(a: str, b: str) -> str:
    return f"{a}-to-{b}"


def pair_accept(src: str) -> list[str]:
    groups = {
        "jpg": ["jpg", "jpeg", "jfif"], "tiff": ["tif", "tiff"], "heic": ["heic", "heif"], "md": ["md", "markdown"],
        "html": ["html", "htm"], "mpeg": ["mpeg", "mpg"],
    }
    return groups.get(src, [src])
