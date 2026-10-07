# Third-party components (Sherlock)

> Rule: permissive licenses only (MIT / BSD / Apache-2.0 / Unlicense), used as
> pip dependencies or pip-installable packages — never copy-pasted into our
> tree. GPL/AGPL code is never bundled. This file is the attribution record.

## sherlock-project (MIT)

- Upstream: https://github.com/sherlock-project/sherlock
- Used as: pip dependency `sherlock-project==0.16.2` (see server/requirements.txt)
- Used by: `server/adapters/deep_probe.py` (deep username-sweep lane). Only the
  `sherlock()` engine call, local `resources/data.json` site list, and
  `QueryStatus`/`QueryNotify` types are used. No upstream code copied.
- License: MIT License (see package dist-info `License-File: LICENSE`).
- Scope note: stealth/proxy features of the ecosystem are NOT used; plain
  public-GET sweeps only, NSFW sites skipped, no proxies configured.

## Transitive / stdlib-adjacent (permissive, via pip)

- `readability-lxml` (Apache-2.0), `trafilatura` (Apache-2.0), `scrapling`
  (BSD-3-Clause) — page-reader extraction chain. See server/requirements.txt
  for per-entry scope notes.
- `fastapi`, `uvicorn`, `pydantic`, `httpx`, `requests`, `pytest` — infra/test.

## Not bundled (patterns studied from docs only, never copied)

- Maigret dossier shape (MIT project; reimplemented), WhatsMyName presence
  shape (CC BY-SA data — not vendored), Scrapling spiders (BSD; used as dep
  only where pinned above).
