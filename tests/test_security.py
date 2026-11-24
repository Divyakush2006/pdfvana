"""Security regression tests: each test attempts an attack against the live API and checks it is stopped."""
from __future__ import annotations

import json
import socket
from urllib.parse import urlparse

import httpx
import pytest

from conftest import BASE_URL, pdf_text


def post_job(tool: str, files: list[tuple[str, bytes]], options: dict | None = None, headers: dict | None = None):
    return httpx.post(f"{BASE_URL}/api/jobs", data={"tool": tool, "options": json.dumps(options or {})},
                      files=[("files", f) for f in files], headers=headers or {}, timeout=60)


def run(api_client, tool, files, options=None):
    r = post_job(tool, files, options)
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    import time

    for _ in range(300):
        s = httpx.get(f"{BASE_URL}/api/jobs/{jid}", timeout=30).json()
        if s["status"] in ("done", "error"):
            return s, jid
        time.sleep(0.4)
    raise AssertionError("job did not finish")


# --------------------------------------------------------------------------- malicious uploads

def test_postscript_disguised_as_pdf_is_rejected():
    r = post_job("compress-pdf", [("evil.pdf", b"%!PS-Adobe-3.0\n(/etc/passwd) (r) file\n")])
    assert r.status_code == 400 and "not a valid PDF" in r.json()["error"]


def test_fake_office_file_is_rejected():
    r = post_job("word-to-pdf", [("report.docx", b"this is not a zip archive")])
    assert r.status_code == 400


def test_playlist_disguised_as_video_is_rejected(api):
    playlist = b"#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:10.0,\nfile:///etc/passwd\n#EXT-X-ENDLIST\n"
    s, _ = run(api, "video-converter", [("clip.mp4", playlist)], {"format": "mp4"})
    assert s["status"] == "error" and "root:" not in s["error"]


def test_media_time_cannot_inject_arguments(api, samples):
    s, _ = run(api, "video-converter", [("clip.mp4", (samples / "clip.mp4").read_bytes())],
               {"format": "mp4", "start": "-i /etc/passwd"})
    assert s["status"] == "error" and "not a valid time" in s["error"]


def test_path_traversal_filename_is_neutralised(api, samples):
    s, _ = run(api, "compress-pdf", [("../../../../etc/passwd.pdf", (samples / "b.pdf").read_bytes())])
    assert s["status"] == "done" and ".." not in s["result"]["name"] and "/" not in s["result"]["name"]


# --------------------------------------------------------------------------- HTML / browser engine

def _download(jid: str, inline: bool = False) -> httpx.Response:
    return httpx.get(f"{BASE_URL}/api/jobs/{jid}/download", params={"inline": "true"} if inline else None, timeout=60)


def test_uploaded_html_scripts_and_local_files_are_blocked(api):
    html = (b"<html><body><h1>Visible heading</h1><script>document.write('XSSMARK')</script>"
            b"<iframe src='file:///etc/passwd'></iframe><img src=x onerror=\"document.body.append('ONERRORMARK')\">"
            b"<meta http-equiv='refresh' content='0;url=file:///etc/'></body></html>")
    s, jid = run(api, "html-to-pdf", [("page.html", html)])
    assert s["status"] == "done"
    text = pdf_text(_download(jid).content)
    assert "Visible heading" in text
    assert "XSSMARK" not in text and "ONERRORMARK" not in text and "root:" not in text


def test_markdown_cannot_read_server_files(api):
    md = b"# Title\n\n![x](/etc/passwd)\n\n<iframe src=\"file:///etc/passwd\"></iframe>\n\n<script>document.write('MDXSS')</script>\n"
    s, jid = run(api, "any-to-pdf", [("notes.md", md)])
    assert s["status"] == "done"
    text = pdf_text(_download(jid).content)
    assert "Title" in text and "root:" not in text and "MDXSS" not in text


def test_active_results_are_never_rendered_inline(api, samples):
    s, jid = run(api, "convert", [("notes.md", b"# Hi\n\n<script>alert(1)</script>\n")], {"format": "html"})
    assert s["status"] == "done"
    r = _download(jid, inline=True)
    assert r.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("url", [
    "http://localhost:8000/api/health", "http://127.0.0.1", "http://[::1]/", "http://2130706433/",
    "http://0.0.0.0/", "http://10.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://app:8000/",
    "http://converter:3000/health",
])
def test_ssrf_to_internal_addresses_is_blocked(api, url):
    s, _ = run(api, "html-to-pdf", [], {"url": url})
    assert s["status"] == "error"


# --------------------------------------------------------------------------- API abuse

def test_cross_site_submission_is_refused(samples):
    r = post_job("compress-pdf", [("b.pdf", (samples / "b.pdf").read_bytes())], headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_same_site_submission_is_allowed(samples):
    origin = f"{urlparse(BASE_URL).scheme}://{urlparse(BASE_URL).netloc}"
    r = post_job("compress-pdf", [("b.pdf", (samples / "b.pdf").read_bytes())], headers={"Origin": origin})
    assert r.status_code == 200


def test_oversized_upload_is_refused_before_reading_the_body():
    u = urlparse(BASE_URL)
    with socket.create_connection((u.hostname, u.port or 80), timeout=10) as sock:
        sock.sendall(b"POST /api/jobs HTTP/1.1\r\nHost: " + u.netloc.encode() +
                     b"\r\nContent-Type: multipart/form-data; boundary=x\r\nContent-Length: 50000000000\r\n\r\n")
        reply = sock.recv(4096).decode(errors="replace")
    assert reply.startswith("HTTP/1.1 413")


def test_invalid_options_are_sanitised(api, samples):
    s, _ = run(api, "convert", [("photo.jpg", (samples / "photo.jpg").read_bytes())], {"format": "../../etc/passwd"})
    assert s["status"] == "done" and s["result"]["name"].endswith(".pdf")  # unknown format -> safe default


def test_oversized_workflow_is_refused(samples):
    steps = json.dumps([{"op": "flatten"}] * 500)
    r = post_job("studio", [("b.pdf", (samples / "b.pdf").read_bytes())], {"steps": steps})
    assert r.status_code == 400


@pytest.mark.parametrize("path", ["/api/jobs/..%2F..%2Fetc%2Fpasswd", "/api/jobs/not-a-job/download", "/api/jobs/%00"])
def test_job_ids_are_validated(path):
    r = httpx.get(BASE_URL + path, timeout=10)
    assert r.status_code == 404


def test_security_headers_present():
    h = httpx.get(f"{BASE_URL}/api/health", timeout=10).headers
    for name in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy",
                 "cross-origin-opener-policy", "cross-origin-resource-policy", "permissions-policy"):
        assert name in h, name
    assert "server" not in h or "uvicorn" not in h["server"].lower()
