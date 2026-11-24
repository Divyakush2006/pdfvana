# Security policy

## Supported versions

Security fixes are released for the latest version on the `main` branch and the most recent release.

## Reporting a vulnerability

**Please do not open a public issue.** Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/divyakush2006/pdfvana/security/advisories/new).

Include:

- a description of the issue and its impact,
- steps to reproduce (a sample file if relevant),
- the version or commit you tested.

You will receive an acknowledgement within 72 hours. Once a fix is ready, we publish a release and a security advisory,
crediting you if you wish.

## Security design

- Uploaded files are stored in a per-job temporary directory, removed as soon as processing finishes; results are deleted
  after `JOB_TTL_SECONDS` (default one hour) and nothing survives a restart.
- File names are sanitised; uploads are size-limited; every external process has a time limit.
- Web-page conversion rejects private, loopback and link-local addresses (SSRF protection), and the conversion service is
  configured to deny private networks and is never exposed publicly.
- Redaction re-renders affected pages so the removed text, images and vectors cannot be recovered.
- Strict Content-Security-Policy, no third-party scripts, fonts or trackers.
- The container runs as an unprivileged user.
