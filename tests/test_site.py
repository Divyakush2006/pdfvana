"""Web app, SEO and API-contract tests."""
from __future__ import annotations

import httpx

from conftest import BASE_URL


def get(path: str) -> httpx.Response:
    return httpx.get(BASE_URL + path, timeout=30)


def test_catalog_contract():
    data = get("/api/tools").json()
    ids = {t["id"] for t in data["tools"]}
    assert {"merge-pdf", "compress-pdf", "convert", "image-converter", "video-converter", "studio"} <= ids
    assert data["targets"]["image"] and data["targets"]["video"]
    assert any(p["slug"] == "png-to-jpg" for p in data["pairs"])
    for t in data["tools"]:
        assert t["seo"]["title"] and t["seo"]["faqs"]


def test_tool_page_is_server_rendered():
    r = get("/merge-pdf")
    assert r.status_code == 200
    html = r.text
    assert "<title>Merge PDF Online" in html
    assert 'rel="canonical"' in html and "application/ld+json" in html
    assert "<h1>Merge PDF</h1>" in html and "Frequently asked questions" in html


def test_conversion_landing_page():
    r = get("/heic-to-jpg")
    assert r.status_code == 200 and "HEIC to JPG Converter" in r.text


def test_unknown_page_is_404():
    r = get("/definitely-not-a-tool")
    assert r.status_code == 404 and r.headers.get("x-robots-tag") == "noindex"


def test_sitemap_and_robots():
    sm = get("/sitemap.xml")
    assert sm.status_code == 200 and "/compress-pdf</loc>" in sm.text and "/mp4-to-mp3</loc>" in sm.text
    assert "Sitemap:" in get("/robots.txt").text


def test_security_headers():
    h = get("/").headers
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert "googleapis" not in h["content-security-policy"]
