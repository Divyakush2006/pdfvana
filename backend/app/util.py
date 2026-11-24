"""Shared helpers: subprocess, page ranges, filenames, zipping."""
from __future__ import annotations

import re
import subprocess
import unicodedata
import zipfile
from pathlib import Path
from collections.abc import Iterable, Sequence

from .config import SUBPROCESS_TIMEOUT


class ToolError(Exception):
    """An error whose message is safe and useful to show to the end user."""


def run(cmd: Sequence[str], timeout: int | None = None, ok_codes: Iterable[int] = (0,)) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=timeout or SUBPROCESS_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Processing took too long and was stopped. Try a smaller file.") from exc
    except FileNotFoundError as exc:
        raise ToolError(f"Server component missing: {cmd[0]}") from exc
    if proc.returncode not in set(ok_codes):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise RuntimeError(f"{cmd[0]} failed ({proc.returncode}): " + " | ".join(tail))
    return proc


def safe_name(name: str, default: str = "file") -> str:
    """Return a filesystem- and header-safe version of a user supplied filename."""
    name = unicodedata.normalize("NFKC", name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name, flags=re.UNICODE).strip(" ._")
    if not name:
        name = default
    if len(name) > 120:
        stem, dot, ext = name.rpartition(".")
        name = (stem[:100] + "." + ext[:15]) if dot else name[:120]
    return name


def stem(name: str) -> str:
    s = Path(name).stem
    return s or "document"


def ext_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def parse_pages(spec: str | None, total: int) -> list[int]:
    """Parse a page selection such as "1-3, 5, 8-", "even", "odd", "last" or "all".

    Returns zero-based indexes in the given order (duplicates removed, order kept).
    """
    spec = (spec or "").strip().lower()
    if not spec or spec == "all":
        return list(range(total))
    if spec == "even":
        return [i for i in range(total) if (i + 1) % 2 == 0]
    if spec == "odd":
        return [i for i in range(total) if (i + 1) % 2 == 1]

    def num(tok: str) -> int:
        tok = tok.strip()
        if tok in ("last", "end", "z"):
            return total
        if not tok.isdigit():
            raise ToolError(f"'{tok}' is not a valid page number.")
        return int(tok)

    out: list[int] = []
    seen: set[int] = set()
    for part in re.split(r"[,;\s]+", spec):
        if not part:
            continue
        m = re.fullmatch(r"(last|end|z|\d+)?-(last|end|z|\d+)?", part)
        if m and part != "-":
            a = num(m.group(1)) if m.group(1) else 1
            b = num(m.group(2)) if m.group(2) else total
            rng = range(a, b + 1) if a <= b else range(a, b - 1, -1)
        else:
            rng = [num(part)]
        for p in rng:
            if p < 1 or p > total:
                raise ToolError(f"Page {p} does not exist (document has {total} pages).")
            if p - 1 not in seen:
                seen.add(p - 1)
                out.append(p - 1)
    if not out:
        raise ToolError("No pages selected.")
    return out


def parse_ranges(spec: str, total: int) -> list[list[int]]:
    """Parse "1-3, 4-6, 7" into groups of zero-based page indexes (one group per comma)."""
    groups = []
    for part in re.split(r"[,;]+", spec or ""):
        part = part.strip()
        if part:
            groups.append(parse_pages(part, total))
    if not groups:
        raise ToolError("Enter at least one page range, for example 1-3, 4-6.")
    return groups


def zip_files(files: list[tuple[Path, str]], dest: Path) -> Path:
    used: dict[str, int] = {}
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, arcname in files:
            arcname = safe_name(arcname)
            if arcname in used:
                used[arcname] += 1
                s, dot, e = arcname.rpartition(".")
                arcname = f"{s} ({used[arcname]}).{e}" if dot else f"{arcname} ({used[arcname]})"
            else:
                used[arcname] = 1
            zf.write(path, arcname)
    return dest


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def hex_to_rgb(color: str, default=(0, 0, 0)) -> tuple[float, float, float]:
    c = (color or "").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        return default
    return tuple(int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
