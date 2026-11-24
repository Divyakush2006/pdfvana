# Deployment guide

## Single server with automatic HTTPS

1. Get a Linux server (4 vCPU / 8 GB RAM handles a healthy public load) with Docker installed.
2. Point your domain's DNS `A`/`AAAA` record at it.
3. Run:

```bash
git clone https://github.com/divyakush2006/pdfvana.git && cd pdfvana
export DOMAIN=pdf.example.com
docker compose -f deploy/docker-compose.prod.yml up -d
```

Caddy obtains and renews certificates automatically. The prebuilt image `ghcr.io/divyakush2006/pdfvana` is used; to build
from source instead, run `docker compose build` and change the `image:` line.

## Configuration checklist

- `SITE_URL` must be your public `https://` URL — canonical links, the sitemap and social cards use it.
- `TRUST_PROXY=true` only when a reverse proxy you control sets `X-Forwarded-For` (the production compose file does).
- Tune `MAX_FILE_MB`, `MAX_TOTAL_MB`, `RATE_LIMIT_PER_MINUTE` and `JOB_TTL_SECONDS` for your audience.
- Keep the conversion service on the internal network only.

## Sizing

| Workload | Suggested host |
|---|---|
| Personal / team use | 2 vCPU, 4 GB RAM |
| Public site, thousands of jobs a day | 4–8 vCPU, 8–16 GB RAM |
| Heavy OCR or video | More CPU first; each worker uses one job slot (`WORKERS`, default = CPU count) |

Disk usage is temporary: plan for roughly `MAX_TOTAL_MB × WORKERS × 3` of free space under `/data`.

## SEO checklist for a public instance

PDFVana ships server-rendered titles, descriptions, canonical URLs, Open Graph cards, FAQ and breadcrumb structured data,
`/sitemap.xml` and `/robots.txt` for the home page, every tool and every conversion landing page.

1. Set `SITE_URL` to the final domain before launch.
2. Verify the domain in Google Search Console and Bing Webmaster Tools and submit `https://<domain>/sitemap.xml`.
3. Serve only one hostname (redirect `www` ↔ apex) so canonical URLs stay consistent.
4. Keep the site fast: put a CDN in front of `/assets/*` (files are content-hashed and cached for a year).
5. Earn links: list the project on directories of free/open-source tools and alternatives, and link to specific tool pages.

## Updating

```bash
docker compose -f deploy/docker-compose.prod.yml pull
docker compose -f deploy/docker-compose.prod.yml up -d
```

Jobs in progress are lost on restart (by design, nothing is stored permanently).
