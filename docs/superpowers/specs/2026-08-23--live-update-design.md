# Live page updates — design

Date: 2026-08-23
Status: approved (approaches + sectioned design approved in chat)

## Problem

The site is a single generated `index.html` whose data is a snapshot embedded
at build time. Data changes during the show (cron re-fetches the results
frontier every 8 min and pushes a rebuilt page), but an already-open page
stays stale until the user manually refreshes. "Up next" and done classes
only move on a manual reload.

## Goal

With the page open, it pulls fresh data itself every ~30 s and re-renders:
"up next" advances, the previous class goes green, new placings appear — no
manual refresh. The host page stays static HTML on GitHub Pages; the cron
refresh task updates a published JSON file, and the page shell updates
itself from it.

## Approved decisions

- **Data endpoint:** a compact `payload.json` committed at the repo root,
  served by GitHub Pages at the site root. No new backend. (Options
  considered and rejected: always-on Worker backend — new infra for an
  8-day show; re-fetching `index.html` — 385 KB of HTML to re-parse every
  30 s and re-render on UI-only deploys.)
- **First paint:** `index.html` keeps the embedded data snapshot. The page
  renders instantly and works if the fetch ever fails (offline, CDN hiccup);
  the snapshot is at most one deploy cycle stale until the first poll.
- **Poll interval:** 30 s. No manual refresh button, no toast per update
  (the "Updated" line moving is the indicator).
- **Countdown indicator:** a circular progress ring next to the "Updated"
  line, filling over each 30 s poll cycle (user chose a circular bar over
  ticking text).

## Key existing fact

The page's "up next" (`frontierNum()`) and done-green (`isDone()`) logic is
already 100% data-driven in the shell JS. No new display logic is needed —
the re-render from fresh data produces the behavior.

## Section 1 — Pipeline

### `payload.json` (new committed artifact)

- Location: repo root, next to `index.html`. Served at the site root.
- Content: exactly the compact payload string
  (`{"asof":"...","classes":[...]}`) + one trailing newline —
  byte-identical (modulo newline) to the payload embedded in `index.html`.
- Committed like `index.html`; never git-ignored.

### `refresh/build_page.py`

- Regular build: asof policy unchanged (compare new `classes` against the
  payload embedded in `index.html`, keep the old asof when identical — the
  comparison source stays `index.html`, not `payload.json`; both are
  committed together and never diverge in practice). After computing
  `payload`, write it to `ROOT/payload.json` (payload string + "\n").
- `--ui-only`: unchanged behavior — re-embeds the payload from
  `index.html`; never reads or writes `payload.json`, never touches asof.
- Payload-line regexes (two occurrences: the `--ui-only` extraction and the
  asof comparison) change from
  `^const DATA = (\{.*\});\s*$` to `^(?:const|let) DATA = (\{.*\});\s*$`.

### `refresh/refresh_cron.sh`

- The uncommitted-changes warning and the no-change detection/staging expand
  from `index.html` to `index.html payload.json`:
  - `git status --porcelain -- index.html payload.json`
  - `git diff --quiet HEAD -- index.html payload.json`
  - `git add index.html payload.json`
- Commit message stays `Refresh entries <date>`.
- Safety heredoc (entry-count halving check): regex updated to
  `^(?:const|let) DATA = (\{.*\});\s*$`; it keeps reading the embedded
  payload in `index.html` (same content as `payload.json`, less change).
- Header comment "Only index.html is ever committed" → both files.
- Cron cadence (8 min) unchanged. End-to-end freshness: ≤ 8 min (cron) +
  1–2 min (Pages deploy) + ≤ 30 s (poll).

## Section 2 — Page (shell JS in the `build_page.py` template)

### Data binding

- `const DATA = __PAYLOAD__;` → `let DATA = __PAYLOAD__;` (module-scope
  `let` binding, so closures see reassignment).
- The one-time index build (NAMES maps, DIVS, DIV_LIST) moves into
  `function buildIndexes()`; called once before the first render and again
  after every accepted data update. `DIV_LIST` becomes `let`.

### Poller

- `const POLL_MS = (typeof window.__POLL_MS === "number") ? window.__POLL_MS : 30000;`
  (`__POLL_MS` is a test hook set via jsdom `beforeParse`.)
- Module state: `liveRaw = JSON.stringify(DATA)` (last accepted payload),
  `pollsFailed = 0`, `pollInFlight = false`, `pollTimer = null`.
- Startup: only if `typeof fetch === "function"` (keeps jsdom and
  file:// usage working — poller inert there), schedule the first poll at
  `+POLL_MS` (no immediate poll; the embedded snapshot is fresh at deploy).
- `poll()`:
  1. If `pollInFlight`, return; else set it.
  2. `fetch("payload.json?ts=" + Date.now(), {cache: "no-store"})`.
     - `?ts=` busts the Pages/CloudFront edge cache (`max-age=600` on
       static assets); `cache: "no-store"` busts the browser cache.
  3. Reject on `!r.ok` or a payload without an array `classes`.
  4. On success: `pollsFailed = 0`; `raw = JSON.stringify(p)`;
     - `raw === liveRaw` → do nothing except clear the stale marker
       (update the Updated line, cheap textContent set).
     - else → `liveRaw = raw; DATA = p; buildIndexes(); renderFilters();
       restoreSearch(); renderSchedule();` and update the Updated line.
       Scroll position is preserved (see below).
  5. On failure: `pollsFailed++`; when `pollsFailed >= 3` and
     `location.protocol` starts with `http`, append " · not updating" to
     the Updated line (cleared on next success).
  6. Always (finally): `pollInFlight = false`; reschedule at `+POLL_MS`.
- `visibilitychange`: tab hidden → cancel the pending timer (no polling
  while hidden); tab visible again → poll immediately, then resume the
  schedule.

### State preservation across a re-render

Survive a data update unchanged: filter selection (`state`), view toggles
(`view`), open class cards (`openCls`), day collapse state (`dayState`),
filter search texts, scroll position.

- `renderFilters()` recreates all filter groups. The options lists already
  re-filter from the module-level `search` object inside `makeGroup`, so
  only the search input *text* must be restored:
  `restoreSearch()` sets each `#filters .fsearch` value from
  `search[key]` (group order: trainer, rider, horse, owner, division).
  No event dispatch needed.
- Scroll: capture `y = window.scrollY` before `renderSchedule()`; after,
  call `window.scrollTo(0, y)` only when `y > 0` (jsdom's scrollY is always
  0, so tests never trigger jsdom's "not implemented" noise; at the top of
  the page there is nothing to restore).
- Known accepted limitation: a per-card "Show all"/"Show mine" toggle
  resets to the default filtered view on a data change (the card itself
  stays open per `openCls`).

### Updated line + countdown ring

- `#updatedLine` is restructured: an inline SVG ring followed by
  `<span id="updatedText">`. All text writes (including the failure marker)
  go to the span; existing text-based tests keep passing unchanged.
- Text: initial render unchanged (`"Updated " + fmtAsof(DATA.asof)`); on
  accepted update, same with the new asof; on 3+ consecutive failures
  (http(s) origins only): `"Updated <asof> · not updating"`.
- The print header line (`#phSub`) is rebuilt inside `renderSchedule()` and
  therefore follows the new asof automatically.
- Ring markup (14 px, starts at 12 o'clock):
  `<svg class="ring" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">`
  with a track circle (stroke `var(--line)`, fill none, r=6) and a progress
  circle (stroke `var(--accent)`, fill none, r=6, `stroke-linecap: round`),
  both `cx=7 cy=7`; the SVG rotated `-90deg` via CSS.
  Progress circle: `stroke-dasharray = C` where `C = 2 * Math.PI * 6`
  (≈ 37.7, computed in JS at init).
- Animation (no recurring timer): after each completed poll
  (success or failure), reset the progress circle:
  `transition = "none"; stroke-dashoffset = C` → force reflow
  (`void el.getBoundingClientRect()`) →
  `transition = "stroke-dashoffset <POLL_MS>ms linear"; stroke-dashoffset = 0`.
  The browser animates the fill over the whole cycle; the next poll's reset
  restarts it. A hidden tab leaves the transition behind, but the
  visibilitychange poll on return resets the ring immediately.
- Visibility rules:
  - Polling inactive (no `fetch` or non-http origin) → the ring element is
    removed at init (no fake countdown on file:// / offline shells).
  - Failure marker active ("not updating") → ring hidden (`display: none`);
    restored on the next successful poll.
  - `@media print`: the ring is hidden (added to the existing print
    hide-list).

## Section 3 — Docs

- `AGENTS.md`: data flow gains `payload.json` (published, committed) vs
  `data.json` (local intermediate); the "single self-contained HTML file"
  story becomes "shell + `payload.json`, embedded snapshot for first
  paint/offline"; Commands (build writes `payload.json`; commit both
  files); Auto-refresh (cron commits both); Publishing (two files, both
  too big for GitHub MCP file tools — keep pushing via git); Verification
  (add `tests/test_payload.py`); Tips (payload line is now `let DATA`).
- `README.md`: the page now updates itself ~every 30 s — no manual refresh
  needed; the header's "Updated" line shows data freshness and a small
  circular ring shows the countdown to the next check; file table
  gains `payload.json`; the "one self-contained HTML file — works offline"
  bullet is reworded (embedded snapshot keeps it working offline for the
  snapshot's data).
- `refresh/README.md`: `payload.json` is the published data file the page
  polls; `--ui-only` never touches it; cron commits both artifacts.

## Section 4 — Tests

### `tests/test.js` (jsdom)

- Payload-line regex: `/^(?:const|let) DATA = (.*);$/m`.
- All existing checks keep passing unmodified (embedded payload line stays;
  `#updatedText` carries the same text so the updated-line regex is
  unaffected; jsdom has no `fetch`, so the poller is inert via the guard and
  the ring is removed at init — the plain dom has no `.ring`).
- New live-update section (a fourth JSDOM instance, built after the existing
  mobile-default checks, before the summary):
  - `beforeParse`: pin the clock (existing `pinDate`), set
    `w.__POLL_MS = 50`, stub `w.fetch` to resolve a prepared payload.
  - Prepared payload = a deep clone of the embedded `DATA` with: the
    current frontier class settled (first entry gets `place: "1"`), and
    `asof` set to a later timestamp. Expectations (next frontier, filtered
    counts, done counts) are computed from the mutated payload exactly the
    way the existing tests compute them from `DATA`.
  - Checks:
    1. After ~250 ms: done count +1; `.cls.now` is the *next* class number;
       Updated line matches the new asof.
    2. State survival: a trainer selection applied before the poll keeps
       its chip and filtered count after the poll; a class card opened
       before the poll is still `.open` after.
    3. No-op poll: stub returns the already-accepted payload → the
       schedule's first child node is the *same* DOM node (no re-render).
    4. Failure path: stub rejects → after 3 polls the Updated line contains
       "not updating" and the ring is hidden; stub recovers → marker
       clears and the ring is visible again.
    5. Ring: present in this dom; progress circle `stroke-dasharray` ≈ 37.7
       (2π·6); `stroke-dashoffset` returns to C (empty) after the first
       poll's cycle reset.

### `tests/test_payload.py` (new, modeled on `test_asof.py`)

Backs up `index.html` + `payload.json` and always restores them at the end.

1. Regular build → `payload.json` exists and its content (minus trailing
   newline) equals the payload embedded in `index.html`.
2. Rebuild with unchanged data → `payload.json` byte-identical (asof
   policy holds for the published file too).
3. Mutated `data.json` (fake class appended, same backup/restore pattern
   and same-minute aliasing wait as `test_asof.py`) → asof in
   `payload.json` bumps.
4. `--ui-only` → `payload.json` byte-identical.
5. Final rebuild from real data → fake class gone.

### Regex touch-ups (logic unchanged)

- `tests/test_ui_only.py` `payload_of()`:
  `^const DATA = ` → `^(?:const|let) DATA = `.
- `tests/test_frontier.py` (real-payload section, ~line 117): same.

### Verification (after the rebuild)

```bash
python3 refresh/build_page.py
npm --prefix tests test
python3 tests/test_ui_only.py
python3 tests/test_asof.py
python3 tests/test_frontier.py
python3 tests/test_payload.py
```

Plus the existing embedded-payload sanity snippet (class/entry counts,
asof) and a check that `payload.json` equals the embedded payload.

Deployment is mid-show: old (non-polling) pages and new pages coexist fine;
the cron keeps running, and the new no-change check simply covers one extra
file.

## Non-goals (YAGNI)

- No backend/WebSockets/push, no partial/DOM-diff re-render (full
  re-render + state restore), no per-update toast, no manual refresh
  button, no service worker/offline cache, no configurable poll interval
  for users.
- `classes.json` / `schedule.json` handling and the cron cadence are
  unchanged.
