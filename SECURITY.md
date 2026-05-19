# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x (latest) | ✅ |

## Reporting a vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

If you discover a security issue, send a private report by emailing the maintainers
or using [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability).

Include:

1. A description of the vulnerability
2. Steps to reproduce or a proof-of-concept
3. Potential impact
4. Any suggested fix (optional)

You can expect an acknowledgement within 72 hours and a status update within 7 days.

## Scope

STAN is designed as a **local, single-user tool** with no authentication layer.
It binds to `127.0.0.1` by default. If you expose it on a public interface or
behind a reverse proxy, ensure you add appropriate authentication (e.g. HTTP Basic
Auth via nginx) — this is outside the scope of STAN itself.

Known non-issues:
- No authentication on API endpoints (by design — local tool)
- SQLite database has no password (by design — local tool)
