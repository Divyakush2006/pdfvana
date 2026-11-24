"""Unit tests for pure helpers (run inside the engine image: ``pytest tests/test_unit.py``)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, "/app")

from app.engine import geometry as g  # noqa: E402
from app.security import SlidingWindow, media_time, sanitize_html  # noqa: E402
from app.util import ToolError, parse_pages, parse_ranges, safe_name  # noqa: E402


def test_sanitize_html_removes_active_content():
    dirty = """<html><head><meta http-equiv="refresh" content="0;url=file:///etc/"><base href="file:///">
    <style>body{background:url(file:///etc/passwd)} @import 'file:///x.css';</style></head>
    <body onload="x()"><script>alert(1)</script><iframe src="file:///etc/passwd"></iframe>
    <a href="javascript:alert(1)">link</a><img src="file:///etc/passwd" srcset="file:///a 1x">
    <svg><use href="file:///etc/passwd#x"/></svg><object data="x.swf"></object><p style="color:red">Keep me</p></body></html>"""
    clean = sanitize_html(dirty).lower()
    for bad in ("<script", "<iframe", "<object", "<base", "http-equiv", "onload", "javascript:", "file:"):
        assert bad not in clean, bad
    assert "keep me" in clean and "color:red" in clean


def test_media_time_validation():
    assert media_time("75") == "75" and media_time("00:01:15.5") == "00:01:15.5" and media_time("") is None
    for bad in ("-i /etc/passwd", "1;rm -rf /", "concat:a|b", "00:00:05 -f"):
        with pytest.raises(ToolError):
            media_time(bad)


def test_sliding_window_limits():
    w = SlidingWindow(3, window=60)
    assert [w.allow("a") for _ in range(4)] == [True, True, True, False]
    assert w.allow("b")


def test_parse_pages():
    assert parse_pages("1-3, 5", 10) == [0, 1, 2, 4]
    assert parse_pages("8-", 10) == [7, 8, 9]
    assert parse_pages("last", 4) == [3]
    assert parse_pages("odd", 5) == [0, 2, 4]
    assert parse_pages("3-1", 5) == [2, 1, 0]
    with pytest.raises(ToolError):
        parse_pages("12", 5)


def test_parse_ranges():
    assert parse_ranges("1-2, 3", 3) == [[0, 1], [2]]


def test_safe_name():
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("my report (final).pdf") == "my report (final).pdf"
    assert safe_name("") == "file"


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_view_user_roundtrip(rot):
    geo = g.PageGeometry(10, 20, 610, 820, rot)
    for u, v in [(0, 0), (100, 50), (geo.width, geo.height)]:
        x, y = geo.view_to_user(u, v)
        assert geo.x0 - 1e-6 <= x <= geo.x1 + 1e-6 and geo.y0 - 1e-6 <= y <= geo.y1 + 1e-6
        u2, v2 = geo.user_to_view(x, y)
        assert abs(u2 - u) < 1e-6 and abs(v2 - v) < 1e-6


def test_view_top_left_is_visible_top_left():
    geo = g.PageGeometry(0, 0, 600, 800, 0)
    assert geo.view_to_user(0, 0) == (0, 800)
    geo90 = g.PageGeometry(0, 0, 600, 800, 90)
    assert (geo90.width, geo90.height) == (800, 600)
    assert geo90.view_to_user(0, 0) == (0, 0)  # rotated 90° clockwise: user origin appears top-left


def test_conversion_pairs_are_unique_reachable_and_supported():
    from app import formats as F
    from app.tools import TOOLS_BY_ID

    slugs = [F.pair_slug(a, b) for a, b in F.PAIRS]
    assert len(slugs) == len(set(slugs)), "duplicate conversion page"
    assert not set(slugs) & set(TOOLS_BY_ID), "a conversion page would be hidden by a tool with the same URL"
    for a, b in F.PAIRS:
        assert a in F.all_input_ext(), a
        assert b in F.TARGETS[F.category(f"x.{a}")], f"{a} -> {b} is not a supported conversion"
