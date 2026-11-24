"""Unit tests for pure helpers (run inside the engine image: ``pytest tests/test_unit.py``)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, "/app")

from app.engine import geometry as g  # noqa: E402
from app.util import ToolError, parse_pages, parse_ranges, safe_name  # noqa: E402


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
