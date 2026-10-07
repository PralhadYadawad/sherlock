# Support — demo draft

> **TODO: lawyer review of support SLAs before public launch.**
> Demo contact: `demo@example.com`. No live chat in v1.

## Contact

- Bugs / refusals that look wrong: email `demo@example.com` with the
  exact input, the returned `status`/`reason`, and `verify.sh` output.
- Deletion requests: same address; see `review/privacy.md` §4
  (per-user storage, delete on request, 90-day retention).
- Security issues: same address with subject `[security]`; do not open
  public issues for suspected key leaks. (Repo holds `DUMMY_` keys
  only.)

## Scope

- Supported: the 6 MCP tools on demo fixtures
  (`triage_target`, `probe_username`, `intel_domain`, `save_reel`,
  `search_memory`, `case_summary`), the offline `sites/index.html`
  dashboard, and `verify.sh`.
- Not supported: login-gated/cookie flows, Saved/Liked history (no
  endpoint exists), PII lookups, bulk scraping, live keys, Meta App
  Review submission, public Directory video production.

## Response targets (demo, non-binding)

- Deletion confirmations: within 30 days (TODO: counsel to confirm).
- Bug reports: best effort; demo project, no SLA.
