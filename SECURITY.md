# Security policy

## Supported versions

Security fixes are released for the latest version on `main` and the most recent release.

## Reporting a vulnerability

**Please do not open a public issue.** Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/divyakush2006/pdfvana/security/advisories/new) and include a description,
impact, reproduction steps (a sample file if relevant) and the version or commit you tested.

You'll get an acknowledgement within 72 hours. Once a fix is ready we publish a release and an advisory, crediting you if you
wish. Good-faith research that respects users' privacy and doesn't degrade the service is welcome.

## How PDFVana is protected

PDFVana processes untrusted files from anonymous users, so every layer assumes hostile input. Highlights — the full threat
model is in [docs/security.md](docs/security.md):

- **No database, no accounts, no secrets** — nothing to inject into or steal; SQL injection is not applicable.
- **No shell** — every tool runs with an argument list (never through a shell); user values are validated against strict
  formats and option schemas, so command and argument injection are not possible.
- **Content verification** — uploads must match their extension (e.g. PostScript disguised as a PDF is refused); media must be
  a real local container (playlists, concat lists and network protocols are blocked).
- **Isolated jobs** — every job runs in its own process with a memory ceiling, maximum output size and wall-clock timeout;
  the whole process tree is killed on timeout.
- **Safe rendering** — uploaded HTML is sanitised (no scripts, frames, refreshes or `file:`/`javascript:` URLs); Pandoc runs in
  sandbox mode; SVG is parsed with external access disabled; XML parsers have entity expansion disabled.
- **SSRF protection** — URL conversion refuses private, loopback, link-local and internal hosts, and the conversion service
  independently denies private networks with DNS-rebinding protection.
- **DoS protection** — streaming upload limits enforced before anything is buffered, per-client rate limits for jobs and API
  calls, per-client and global job caps, concurrent-upload caps, disk-space guards, render-size caps and media duration limits.
- **Web hardening** — strict Content-Security-Policy, framing denied, cross-site job submission refused, results that could
  carry script are never rendered inline and are sandboxed, no server banner.
- **Container hardening** — unprivileged user, read-only filesystem, all Linux capabilities dropped, no privilege escalation,
  process and memory limits; the conversion service is never exposed.
- **Privacy** — files are deleted as soon as processing ends and results after one hour; nothing survives a restart.
- **Supply chain** — checksum-verified downloads, CodeQL code scanning, dependency audits, container vulnerability scanning,
  OpenSSF Scorecard, Dependabot and branch protection with required checks.
