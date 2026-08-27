# Scratch entries — design

Date: 2026-08-27
Status: approved (sectioned design approved in chat 2026-08-27).

## Problem

Entries that scratch (are withdrawn before their class) are invisible on our
page. On the main site (horseshowsonline.com) they appear on the class
entries page with a strikethrough and a pink/red background. The family
wants scratches on the schedule page.

## Key existing facts

- Scratched entries already sit on the exact entry pages the pipeline
  fetches (`ClassResults.aspx?ClassGUID=…`). The scratch row is a normal
  `grNonPlacing` data row whose `<tr>` tag carries
  `style="background-color:LightPink;font-size:8pt;text-decoration: line-through;"`;
  a normal row's `<tr>` has no such style. No new data source, no new URL.
- The existing 8-minute cron re-fetches the results frontier + 8 lookahead
  classes, so scratches for the imminent classes land within ~8 minutes
  once the parser understands the mark.
- A class's page is re-fetched when the frontier reaches it (i.e. when its
  results post), so a settled class's page already contains every scratch
  that class will ever have. A one-time full re-fetch of settled classes is
  unnecessary.

## Goal

Parse the scratch mark, carry it into the payload, render scratched entries
with a pink/red background + strikethrough (always shown, counted in
"N entries"), and keep the whole upcoming schedule's scratch state fresh
via a separate 4-hour cron pass over all unsettled classes.

## Approved decisions

- **Display:** scratched entries are always listed, styled like the site
  (pink/red background, strikethrough), counted in the class entry count.
  No filter, no toggle.
- **Cron:** a separate job — `refresh/refresh_upcoming.sh` on
  `0 */4 * * *` — that re-fetches every *unsettled* class. The 8-minute job
  (frontier + lookahead) is unchanged. Same lock, log, and safety net.
  Stateless (no time bookkeeping; "which classes" is re-derived from the
  payload each run, like the frontier).
- **First run = the big refresh:** the new job's first run re-fetches every
  unsettled class (~73 on 2026-08-27, shrinking daily). Settled classes'
  pages already contain all their scratches. No 241-page re-fetch.
- **Stale classes are excluded** from the 4-hour pass (session started >4 h
  ago with no results → presumed skipped, same rule the frontier uses): no
  point re-fetching a presumed-void class.
- **Edge case accepted:** a scratch entered on a class *after* its results
  posted will not be picked up (its page is no longer re-fetched).
  Practically nonexistent for this show.

## Design

### 1. Parse (`refresh/parse_entries.py`)

`parse_rows` already matches
`<tr id="…_gr<Grid>_DXDataRow\d+"[^>]*>(…)`. Change the match to also
capture the `<tr>` tag's attribute string, and set `"scratch": True` on the
row dict when the tag contains `text-decoration: line-through` (the
reliable marker on the `LightPink` row style; checked on both grids, though
scratch rows appear in `grNonPlacing`).

`parse_page` propagates the flag: entry dicts gain `"scratch": True` only
when the row is scratched (key absent otherwise, so `data.json` stays lean
and the no-scratch bytes are zero).

### 2. Payload + build (`refresh/build_page.py`)

Each class dict gains

```json
"sc": ["1446", "1462"]
```

— the entry numbers of its scratched entries — **only when non-empty**
(one-letter key, matching `n`/`div`/`e`/`ps`/`pe`).

No other build changes: `h` (sha1-12 of the classes JSON), `check.json`,
and the asof policy are pure functions of the classes JSON, so a scratch
appearing or disappearing changes `h` and the "Updated" stamp exactly once,
and the page's 30-second poll picks it up. The `--ui-only` path re-embeds
the stored payload untouched. The live merge and predicted-pace stamping
do not touch `sc` (scratched entries never carry places; official
placings still win everywhere).

### 3. Page display (template in `build_page.py`)

- `makeClass`: `const scr = new Set(c.sc || [])`; in `buildRows`, entry
  rows whose `e[0]` is in `scr` get a `scratch` class on the `.erow`.
- CSS `.erow.scratch`: pink background (light-mode and dark-mode vars) with
  strikethrough and red ink on the row text, mirroring the site's
  LightPink + line-through treatment. The row keeps its grid layout; a
  scratched entry has no place, so no place badge is affected.

### 4. Refresh strategy

`refresh/select_frontier.py` gains an `upcoming` command (and the CLI
choice): all classes in schedule order that are **not settled and not
stale**, each expanded with `fetch_nums_for` to its sections, printed one
per line. Reuses `is_settled`, `is_stale`, `fetch_nums_for`, `_order` — no
new logic.

New `refresh/refresh_upcoming.sh`, cron `0 */4 * * *`:

- `set -u`, same `exec >> cron.log 2>&1` logging; `flock -n` on the **same**
  `refresh/cron.lock` (a run can never overlap the 8-minute job or another
  upcoming run; if the lock is held it logs and exits 0).
- Robustness: if `entries/` has < 50 pages (fresh clone / wiped dir) it
  does the full resumable fetch instead (same guard the 8-minute job uses).
- Otherwise: `select_frontier.py upcoming > refreshlist.txt`; empty list →
  log "nothing upcoming" and exit. Else `fetch_entries.sh <list>` (list
  mode: re-fetch exactly those nums, never skipping), `parse_entries.py`,
  then the same build + >50 %-entry-drop safety check + commit/push-if-
  changed flow as `refresh_cron.sh` (adds the same four paths:
  `index.html payload.json check.json refresh/classes.json`; the classes
  file is a no-op here — the 8-minute job keeps the class list fresh).
- No class-list refresh step in this job (the 8-minute job runs
  `class_list.py` at most 8 minutes stale; `fetch_entries.sh` already
  warns + skips nums missing from `classes.json`).

### 5. Tests

- `tests/test_parse_entries.py`: a scratch row (`<tr>` with the LightPink
  line-through style) yields an entry with the scratch flag; a normal row
  does not; placed-grid rows can carry the flag too.
- `tests/test_frontier.py`: `upcoming` returns all unsettled, non-stale
  classes in schedule order, sections expanded (a split class contributes
  both section nums); settled classes excluded; stale classes excluded;
  empty when everything is settled; CLI prints the list.
- `tests/test.js`: from the built payload, find a class with non-empty
  `sc`, open it, assert the scratched entry's `.erow` has the `scratch`
  class and a non-scratched row does not. (Real data: the show has
  scratches by mid-show; if the payload has none, the check is skipped
  with a note.)
- Existing suites keep passing: asof policy, payload/check, ui-only,
  live, predict — the asof policy is untouched (scratch data flows through
  the same classes JSON).

### 6. Docs

- `AGENTS.md`: Commands (new script + cron line), the Auto-refresh section
  (what the 4-hour job does and why it's separate), Architecture (scratch
  mark source + `sc` payload key), and a Tip (scratch mark is on the
  already-fetched pages; settled pages already contain all their
  scratches).
- `refresh/README.md`: one line per new artifact (upcoming script, `sc`).

## Rollout

1. Implement (parse → payload → UI → `upcoming` command → cron script),
   tests green.
2. Rebuild with existing fetched pages: scratches for all classes whose
   pages are current appear immediately.
3. Commit + push (publishes to GitHub Pages).
4. User installs `0 */4 * * *  <repo>/refresh/refresh_upcoming.sh`; its
   first run is the big refresh of all unsettled classes.
