# REST API

Every tool in the web app is available over HTTP. The OpenAPI document is served at `/api/openapi.json` and interactive docs
at `/api/docs`.

## Flow

```bash
# 1. Create a job (multipart form)
curl -s -F tool=merge-pdf \
     -F 'options={"bookmarks": true}' \
     -F files=@a.pdf -F files=@slides.pptx -F files=@photo.jpg \
     http://localhost:8080/api/jobs
# → {"id": "3f2c…", "status": "queued", ...}

# 2. Poll until status is "done" or "error"
curl -s http://localhost:8080/api/jobs/3f2c…
# → {"status": "done", "result": {"name": "merged.pdf", "size": 81234}, "message": "Merged 3 files into 7 pages.", ...}

# 3. Download (add ?inline=true to display in the browser)
curl -OJ http://localhost:8080/api/jobs/3f2c…/download

# 4. Optional: delete immediately
curl -X DELETE http://localhost:8080/api/jobs/3f2c…
```

## Form fields

| Field | Description |
|---|---|
| `tool` | Tool id (see below) |
| `options` | JSON object with the tool's options; omitted options use their defaults |
| `files` | One or more files (repeat the field) |
| `extra_<id>` | Additional files some tools need, e.g. `extra_signature` for `sign-pdf`, `extra_image` for `add-watermark` |

## Discovering tools and options

`GET /api/tools` returns every tool with its accepted file types and a typed option schema (`select`, `number`, `checkbox`,
`text`, `pages`, …), plus the format matrix used by the universal converter:

```bash
curl -s http://localhost:8080/api/tools | jq '.tools[] | {id, accept, options: [.options[].id]}'
```

## Examples

```bash
# Compress to at most 1 MB
curl -F tool=compress-pdf -F 'options={"level":"target","target_mb":1}' -F files=@big.pdf http://localhost:8080/api/jobs

# Anything → anything
curl -F tool=convert -F 'options={"format":"pptx"}' -F files=@report.docx http://localhost:8080/api/jobs
curl -F tool=convert -F 'options={"format":"mp3"}'  -F files=@talk.mp4    http://localhost:8080/api/jobs
curl -F tool=convert -F 'options={"format":"svg"}'  -F files=@logo.png    http://localhost:8080/api/jobs

# OCR a scan in English + Hindi
curl -F tool=ocr-pdf -F 'options={"languages":["eng","hin"]}' -F files=@scan.pdf http://localhost:8080/api/jobs

# Document Studio pipeline
curl -F tool=studio \
     -F 'options={"merge":true,"format":"pdf","steps":"[{\"op\":\"page_numbers\"},{\"op\":\"compress\",\"level\":\"strong\"}]"}' \
     -F files=@a.docx -F files=@b.pdf http://localhost:8080/api/jobs
```

## Errors and limits

Errors return JSON `{"error": "<human readable message>"}` with an HTTP status (400 invalid input, 413 too large,
429 rate limited). A job that fails during processing reports `"status": "error"` with a message in `error`.
