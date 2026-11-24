"""Runtime configuration (all overridable with environment variables)."""
import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


VERSION = "1.0.0"
BRAND_NAME = os.getenv("BRAND_NAME", "PDFVana")
# Public URL of this deployment, used for canonical links, sitemap.xml and social cards.
SITE_URL = os.getenv("SITE_URL", "http://localhost:8080")
# Only trust X-Forwarded-For when running behind your own reverse proxy.
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")
REPO_URL = os.getenv("REPO_URL", "https://github.com/divyakush2006/pdfvana")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data/jobs"))
STATIC_DIR = Path(os.getenv("STATIC_DIR", "/app/static"))
CONVERTER_URL = os.getenv("CONVERTER_URL", os.getenv("GOTENBERG_URL", "http://converter:3000")).rstrip("/")

# Privacy: every uploaded and generated file is deleted after this many seconds.
JOB_TTL_SECONDS = _int("JOB_TTL_SECONDS", 3600)

# Limits that keep a free public instance healthy.
MAX_FILE_MB = _int("MAX_FILE_MB", 200)
MAX_TOTAL_MB = _int("MAX_TOTAL_MB", 500)
MAX_FILES = _int("MAX_FILES", 60)
WORKERS = _int("WORKERS", max(2, (os.cpu_count() or 2)))
RATE_LIMIT_PER_MINUTE = _int("RATE_LIMIT_PER_MINUTE", 40)
SUBPROCESS_TIMEOUT = _int("SUBPROCESS_TIMEOUT", 900)
