"""Tabular data conversion: CSV, TSV, JSON, Excel, HTML and Markdown tables."""
from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path

from .util import ToolError, ext_of, stem

Table = list[list[object]]


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_table(path: Path, name: str | None = None) -> Table:
    e = ext_of(name or path.name)
    if e in ("csv", "tsv", "txt"):
        text = _decode(path.read_bytes())
        if e == "tsv":
            dialect = csv.excel_tab
        else:
            try:
                dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    if e in ("json", "jsonl"):
        text = _decode(path.read_bytes())
        try:
            data = [json.loads(l) for l in text.splitlines() if l.strip()] if e == "jsonl" else json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError(f"'{name or path.name}' is not valid JSON (line {exc.lineno}).") from exc
        if isinstance(data, dict):  # {"items": [...]} or a single record
            lists = [v for v in data.values() if isinstance(v, list)]
            data = lists[0] if len(lists) == 1 else [data]
        if not isinstance(data, list) or not data:
            raise ToolError("The JSON must contain a list of records.")
        if all(isinstance(r, dict) for r in data):
            flat = [_flatten(r) for r in data]
            keys: list[str] = []
            for r in flat:
                keys += [k for k in r if k not in keys]
            return [keys] + [[r.get(k, "") for k in keys] for r in flat]
        if all(isinstance(r, list) for r in data):
            return data
        return [["value"]] + [[r] for r in data]
    if e in ("xlsx", "xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [["" if v is None else v for v in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        while rows and not any(str(v).strip() for v in rows[-1]):
            rows.pop()
        return rows
    raise ToolError(f".{e} files can't be read as a table. Use CSV, JSON or XLSX.")


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        elif isinstance(v, list):
            out[key] = json.dumps(v, ensure_ascii=False)
        else:
            out[key] = v
    return out


def table_to_html(rows: Table, title: str = "", css: str = "") -> str:
    head, body = (rows[0], rows[1:]) if rows else ([], [])
    th = "".join(f"<th>{html.escape(str(c))}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in body)
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{css}table{{font-size:9pt}}</style></head><body><h3>{html.escape(title)}</h3>"
            f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></body></html>")


def write_table(rows: Table, dst_dir: Path, base: str, fmt: str) -> Path:
    dst = dst_dir / f"{base}.{fmt}"
    if fmt == "csv":
        with dst.open("w", newline="", encoding="utf-8-sig") as fh:
            csv.writer(fh).writerows(rows)
    elif fmt == "json":
        head = [str(h) or f"column{i + 1}" for i, h in enumerate(rows[0])] if rows else []
        records = [{head[i]: _json_value(v) for i, v in enumerate(r) if i < len(head)} for r in rows[1:]]
        dst.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    elif fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = base[:31] or "Sheet1"
        for r in rows:
            ws.append([_json_value(v) for v in r])
        if rows:
            for cell in ws[1]:
                cell.font, cell.fill = Font(bold=True), PatternFill("solid", fgColor="E8F5EE")
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, width + 2), 60)
        wb.save(dst)
    elif fmt == "html":
        dst.write_text(table_to_html(rows, base, "body{font-family:sans-serif}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}"), encoding="utf-8")
    elif fmt == "md":
        cols = max((len(r) for r in rows), default=0)
        norm = [[str(c).replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (cols - len(r)) for r in rows]
        lines = ["| " + " | ".join(norm[0]) + " |", "|" + "---|" * cols] + ["| " + " | ".join(r) + " |" for r in norm[1:]] if norm else []
        dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        raise ToolError(f"Tables can't be saved as {fmt.upper()}.")
    return dst


def _json_value(v):
    if isinstance(v, str):
        s = v.strip()
        if s.lstrip("-").replace(".", "", 1).isdigit() and not (s.startswith("0") and len(s) > 1 and "." not in s):
            try:
                return int(s) if "." not in s else float(s)
            except ValueError:
                return v
    return v


def convert_table(src: Path, name: str, dst_dir: Path, fmt: str) -> Path:
    rows = read_table(src, name)
    if not rows:
        raise ToolError(f"'{name}' contains no data.")
    return write_table(rows, dst_dir, stem(name), fmt)


def pdf_tables_json(pdf: Path, dst: Path) -> Path:
    import pdfplumber

    out = []
    with pdfplumber.open(pdf) as plumb:
        for i, page in enumerate(plumb.pages):
            for t in page.find_tables():
                rows = t.extract()
                if rows and len(rows) > 1:
                    head = [str(h or f"column{k + 1}").strip() for k, h in enumerate(rows[0])]
                    out.append({"page": i + 1, "rows": [{head[k]: (c or "").strip() for k, c in enumerate(r) if k < len(head)} for r in rows[1:]]})
    if not out:
        raise ToolError("No tables were detected in this PDF.")
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst
