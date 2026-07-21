# 0002 — Static platform with issue intake

日期:2026-07-20
状态:已接受

The sharing platform will be a static site deployed to the user's own server, with a minimal intake service that turns form submissions from classmates into structured GitHub issues. This keeps the platform within the ~30% time budget while still making it usable from WeChat and compatible with the local AI-assisted workflow.

## Considered Options

- **Static site only**: easy to ship, but classmates cannot submit structured feedback.
- **Full workflow system**: closer to intelligrow-flow, but too large for a five-day single-person project.
- **Static site + minimal intake service**: enough interaction to create issues, without building a second product.

## Implementation notes(2026-07-20 补充)

- Intake service holds a **fine-grained GitHub PAT**(仅本仓库、仅 Issues read/write)**server-side only** — the token must never reach the browser or the static bundle.
- Form fields follow the *Intake Fields* term in CONTEXT.md; submitter name goes into the issue body, type/priority become issue labels.
- Deployed same-origin per ADR-0017(form posts to `/api/intake`),so no CORS configuration is needed.
- Minimal spam guard: honeypot field + per-IP rate limit. The repo is public, so created issues are public — teammates must not paste sensitive data into tickets.

