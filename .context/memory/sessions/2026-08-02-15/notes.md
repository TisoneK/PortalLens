# Session 15 — docs: usage tutorial (2026-08-02)

> **Adjacent file:** the review report is at
> `.context/memory/reviews/2026-08-02-review-2.md`.

## Target

"Add how to use the tool in README (summary) but point to full tutorial
to a dedicated file."

## What changed (product surface, 2 commits pushed)

- `docs/TUTORIAL.md` (new) — full tutorial: install + extras table,
  quick start, `analyze` with all options (incl. `--format sarif`,
  `-o`, `--notes`), report walkthrough + confidence model, TUI, saved
  investigations + `resolve_dns`/`ip_asn_lookup` steps + DB path,
  `--authorized` active analysis, five bypass probes with verified
  signatures, library API (markdown/SARIF/TUI-as-library), SARIF,
  troubleshooting, responsible use.
- `README.md` — Usage section condensed to quick-start tour + command
  table + library snippet, with a prominent pointer to the tutorial.
- `CHANGELOG.md` — plain-language "full user tutorial" entry under
  [Unreleased] Added.

## Useful negative results / facts for future sessions

- **The TUI has no quit key bindings** — `tui/` source has no
  `BINDINGS`/`action_quit`/key handlers (verified by code search).
  Textual's default `Ctrl+C` is the reliable quit. If the user ever
  reports TUI quit friction, that's the gap; don't document `q` again
  without adding a binding.
- **`analyze` has no `--db` option** — persistence options live on
  `investigate`/`investigations`/`show`/`step`. The reviewer caught a
  tutorial line listing `--db` under `analyze`; fixed.
- **Code review pays off on docs too**: every probe signature was
  verified against `bypass.py`, yet the reviewer still caught the one
  wrong option line. Cross-check documented flags against the actual
  `@click.option` decorators in `cli.py`.

## Process

- Followed the full local-edition protocol (Phase 1 reads + baseline,
  docs commit + push, reviewer pass, fixes, memory phase). Baseline
  green before and after. Session numbered 15 (14 was the last logged).
