# Contributing to PDFVana

Thanks for helping make PDFVana the best free document toolkit. Every contribution matters — bug reports, fixes, new tools,
translations, docs and design.

## Ground rules

- Be kind and constructive. See the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security issues go to the private channel in [SECURITY.md](SECURITY.md), never to public issues.
- Keep PDFVana **free and private**: no tracking, no third-party requests, no paywalled features.

## Getting started

```bash
git clone https://github.com/divyakush2006/pdfvana.git && cd pdfvana
docker compose up -d --build            # full app on http://localhost:8080
cd frontend && npm install && npm run dev  # UI with hot reload on http://localhost:5173
```

## Development

Run the engine with your local code mounted, and the UI with hot reload:

```bash
docker compose up -d converter
docker build --target engine -t pdfvana-engine .
docker run --rm -p 8080:8000 --network pdfvana_default -e CONVERTER_URL=http://converter:3000 \
  -v "$PWD/backend/app:/app/app" pdfvana-engine            # backend with your local code

cd frontend && npm install && npm run dev                   # UI with hot reload on :5173
```

Run the unit, end-to-end and security tests against a running stack:

```bash
docker build --target test -t pdfvana-test .
docker run --rm --network pdfvana_default -e BASE_URL=http://app:8000 pdfvana-test
```

## Project layout

| Path | Contents |
|---|---|
| `backend/app/tools.py` | Tool registry: metadata, option schema and handler for every tool. The UI is generated from it. |
| `backend/app/engine/` | PDF engine: page geometry, stamping, layout analysis and Office/Markdown writers |
| `backend/app/convert.py` | Document conversion (any document → PDF → any document) |
| `backend/app/media.py` / `data.py` | Image, audio/video and tabular data converters |
| `backend/app/ops.py` | PDF operations (merge, compress, OCR, redact, compare…) |
| `backend/app/seo.py` | Page titles, structured data, sitemap |
| `frontend/src/` | React app |
| `tests/` | Unit and end-to-end tests |

## Adding a tool

1. Write a handler `def h_my_tool(ctx: Ctx) -> Path` in `backend/app/tools.py` (or put the heavy lifting in `ops.py`/`media.py`).
2. Register it with a `Tool(...)` entry: id, name, description, category, icon, accepted extensions and `Option`s.
3. Add an end-to-end test in `tests/test_tools.py`.

The frontend renders the page, options form, validation and SEO content automatically.

## Pull requests

1. Fork, create a branch (`feat/…`, `fix/…`, `docs/…`).
2. Keep changes focused; update docs and tests with the code.
3. Make sure these pass locally:
   - `cd frontend && npx tsc -b` (type check)
   - `ruff check backend tests` (lint)
   - the test suite (`docker build --target test -t pdfvana-test . && docker run --rm --network pdfvana_default -e BASE_URL=http://app:8000 pdfvana-test`)
4. Use clear commit messages in the imperative mood (`Add favicon generator`, `Fix rotated-page watermark`).
5. Open the PR using the template and describe how you tested it.

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
