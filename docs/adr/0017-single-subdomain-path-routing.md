# 0017 — Single subdomain alpha.cihua.run with path routing

日期:2026-07-20
状态:已接受

The platform lives at **`alpha.cihua.run`**. The packet feed (展示面) is served at `/`, the intake form (工单面) at `/submit`, and the intake service at `/api/intake` — one subdomain, different routes, instead of two subdomains.

## Reasons

- Same-origin form → API avoids CORS entirely and keeps the intake service tiny.
- One DNS record, one certificate, one nginx site, one deploy target — fits the ~30% platform time budget.
- The link shared to WeChat is just the root URL; audience separation is done by which link you share (`/submit` is given to teammates, optionally to outsiders), not by domain.

## Considered alternatives

- Two subdomains (e.g. `alpha.cihua.run` + `ticket.cihua.run`): cleaner audience separation, but doubles DNS/cert/nginx work and forces CORS on the intake API, for no functional gain since the intake is primarily internal.
- Other names considered: `factor.cihua.run`, `lab.cihua.run`.

## Consequences

- Once the URL circulates in WeChat, changing the subdomain breaks shared links — the name is effectively frozen after first share.
