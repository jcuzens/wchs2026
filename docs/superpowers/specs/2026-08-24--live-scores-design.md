# Live Scores integration — design

Date: 2026-08-24
Status: approved (sectioned design approved in chat 2026-08-24)

## Problem

The class-results pages the pipeline already pulls are delayed: a class can
be scored and placed for minutes or longer before its `ClassResults.aspx`
page updates. Two consequences:

1. Placements appear on the site late — the family wants them as soon as
   they're scored.
2. The "up next" card (first class in schedule order with no placings)
   lags reality, so "which class are we actually on" is unreliable.

## Goal

In addition to the class-results pages, pull the show's **Live Scores**
tab (`https://horseshowsonline.com/ShowDetails?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12` →
"Live Scores" → `LiveScoring.aspx`). Its per-class detail lists placed
entries (entry #, horse, rider, place) within minutes of scoring, and its
summary list is ordered by recency with "Updated Xm ago" per class.

Live data is merged into the payload so existing page logic (placings,
"up next", done pill) improves automatically. Classes with fresh live data
get a small gold **live pill**.

## Approved decisions

- **Merge rule: official class-results placings win; live fills gaps.**
  For each entry, `place = official if known, else live`. Monotonic, no
  flicker, self-correcting when the official page catches up.
- **Accumulating local cache** (`refresh/live_cache.json`, git-ignored):
  live placings persist across cron runs so a class doesn't "un-place"
  when it ages out of the live window before its official page re-fetches.
- **UI:** live pill (gold, "up next" family) on classes with live data
  fresher than 60 min at build time + faster placings. No other UI changes.
- **Cron frontier:** unchanged (existing walk-the-frontier + lookahead).
  Live is an additive data source only.
- **"Up next" rule:** unchanged (first class in display order with no
  placings). It improves automatically as live placings fill gaps.

## Key existing facts

- `LiveScoring.aspx` is on the same domain and session as the existing
  fetcher: `refresh/jar.txt` (`ASP.NET_SessionId`) works as-is; the
  fetcher's ShowDetails session warm-up applies.
- The summary grid (DevExpress ASPxGridView, `grMain`) renders server-side
  on GET: ring, ord, class num+name, shown/total progress bar, Placed,
  Not Placed, "Updated Xm ago" (e.g. `53 min`, `1 hour, 51 min`,
  `2 hours, 2 min`), Source (`Show Secretary` = reviewed). Rows are
  oldest→newest by update time. The grid paginates at **10 rows/page**.
- Per-class detail (the placed entries) loads via a **WebForms callback**
  (XHR), not a page fetch. Reverse-engineered from the site's own JS
  (`DXR.axd` bundle + `webforms.js`) and verified end-to-end 2026-08-24
  with a jsdom capture of the real page's request, replayed with curl.
  See "Callback protocol" below.
- The live detail lists **placed entries only** (no not-placed detail).
  The detail's Score column is empty for the classes sampled — ignored in
  v1.
- The show is live during implementation (2026-08-24): the protocol can be
  probed against production, and the real page is the acceptance test.

## Section 1 — Callback protocol (reverse-engineered, verified)

Page: `https://horseshowsonline.com/LiveScoring.aspx?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12`
(with or without the query string; the session picks the show).

### GET phase

1. GET the page (with `jar.txt` cookie). A valid response contains an
   `ASPx.createControl(ASPxClientGridView,'...grMain', ...)` script block.
   No such block (login shell / dead session) → treat as fetch failure.
2. Parse from the static HTML:
   - All form fields in DOM order: the 5 hidden
     (`__EVENTTARGET`, `__EVENTARGUMENT`, `__VIEWSTATE`,
     `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`) plus the 2 text inputs
     (`...grMain$DXSE`, `ctl00$ctl00$ASPxDateEditMaster`).
   - The grid block: `callbackID` (the `WebForm_DoCallback('...')` arg =
     `ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain`),
     and its `stateObject`: `keys` (array of row GUIDs),
     `groupLevelState` (`{}`), `callbackState` (base64-ish token).
3. Build the grid's **hidden state input** (the grid renders a hidden
   input named with its own uniqueID at JS runtime; the server needs it on
   the callback):
   ```json
   {"keys":[...],"groupLevelState":{},"callbackState":"...","focusedRow":0,"selection":"","toolbar":"{}"}
   ```
   HTML-escaped (`"` → `&quot;`) as the field value.

### Callback POST (one per grid page)

POST to the same URL, body = all form fields (step 2) + the grid state
input (step 3), then:

- `__CALLBACKID` = the grid uniqueID
- `__CALLBACKPARAM` =
  `c0:KV|<len>;<keys-json>;FR|1;0;CT|2;{};GB|<len>;<serArgs>;`
  where `<keys-json>` is the compact JSON key array, and `<serArgs>` is
  each item as `<strlen>|<item>` concatenated:
  - `SHOWALLDETAIL` → `13|SHOWALLDETAIL`
  - `GOTOPAGE <n>` (0-based) → `8|GOTOPAGE1|<n>`
- `__EVENTVALIDATION` (last)

Wire facts (all verified against a jsdom capture of the real page):

- The `c0:` prefix (callback type `c` = common, slot `0`) is **required** —
  without it the server throws `Length cannot be less than zero`.
- `FR|1;0;` (focused row 0) and `CT|2;{};` (toolbar `{}`) are part of the
  real request; sending KV+GB alone yields an empty grid (no error).
- A full/synchronous postback and the UpdatePanel async postback do **not**
  work: the grid binds data on GET only ("No data to display").
- The callback response is `0|/*DX*/({'result':{'html':'<escaped grid
  html>','stateObject':{...}},...})`. A server fault appears as
  `{'error':{'message':...}}` or `{'generalError':...}`.
- `result.html` is a JS-escaped string (unescape `\'` `\\` `\n` `\/`).
- On multi-page grids: `GOTOPAGE n` then `SHOWALLDETAIL`. Re-parse the
  grid state (keys/callbackState) **from each response's HTML** before the
  next request. `NEXTPAGE` (no args) errors server-side — don't use it.
  (Verified `GOTOPAGE` to a nonexistent page degrades gracefully.)

### Parse

From `result.html`:

- Parent rows (`dxgvDataRow_*`): ring, ord, `NN - <name>` (num includes
  `x.y` sub-classes), progress bar `shown / total` (the
  `customDisplayFormat` "N / M" div), Placed, Not Placed, Updated, Source.
- Detail rows (one block per expanded parent): header `Entries that
  placed`, then per entry: entry #, horse name, color/age/sex (ignored),
  rider, country (ignored), Ord (ignored), **Place** (1-based; blank =
  not placed, not listed), Score (ignored in v1).

### Output: `refresh/live.json` (git-ignored)

```json
{
  "fetched": "2026-08-24 09:20",
  "pages": 1,
  "classes": [
    {"num": "54", "name": "ASB Adult Five Gaited Show Pleasure Div II",
     "ring": "Ring 1", "shown": 15, "total": 15,
     "placed": 8, "not_placed": 7,
     "updated": "32 min", "source": "Show Secretary",
     "entries": [[1379, "SOMETHING JUSTT LIKE THIS", "VERRILL, TAYLOR", 5]]}
  ]
}
```

`entries` = `[entry#, horse, rider, place]` for placed entries only.

## Section 2 — Pipeline scripts

### `refresh/fetch_live.py` (new; stdlib only — urllib, re, json)

- Warms the session (GET ShowDetails, mirroring `fetch_entries.sh`), then
  runs the GET + callbacks above: page 0 = 1 callback (SHOWALLDETAIL);
  each further page = 2 (GOTOPAGE n, then SHOWALLDETAIL). `pageIndex` is
  assumed 0-based (ASPx convention; the server clamps invalid pages and an
  off-by-one would worst-case re-fetch a page, which the merge tolerates).
- Writes `live.json`. Exits 0 on success.
- **Fail-safe:** any failure (no grid block, callback error, parse yields
  zero classes) → non-zero exit, **does not touch** `live.json` or
  `live_cache.json`. Cron logs a warning and continues; the page degrades
  to official-only data (today's behavior) with the cache retained.
- Request pacing: one GET + N callbacks (N = pages, expected 1); ~8-min
  cron cadence makes rate limits a non-issue.

### `refresh/parse_live.py` (new; stdlib only)

- Reads `live.json`, folds it into `live_cache.json` (git-ignored):
  ```json
  {"54": {"1379": {"p": 5, "at": "2026-08-24 09:20"}}, ...}
  ```
  Cache grows only (no deletes during the show). Re-running with the same
  data is idempotent.
- `parse_entries.py` is unchanged; the merge happens in `build_page.py`.

### `refresh/build_page.py` (changed)

- After loading `data.json`, if `live_cache.json` exists: for each class
  (join key = class number) and each entry with **no** official place, if
  the entry# is in the cache → set its place from the cache. Official
  places are never overwritten.
- Payload: classes present in the **current** `live.json` whose `updated`
  parses to fewer than **60 min** gain `"live": <minutes-ago>`; key omitted
  otherwise. The pill tracks live *activity* (per-class "Updated Xm ago"
  from the fresh fetch), not when a placing was first cached. If the live
  fetch failed this run, no class gets a pill (degraded to official-only).
- asof policy, `--ui-only`, embedding, and the asof compare logic are
  unchanged. (Live changes alter `classes` ⇒ payload changes ⇒ asof bumps
  ⇒ the 30 s poll picks it up.)

### `refresh/refresh_cron.sh` (changed)

- After the class-fetch phase (full or frontier mode) and before the
  safety check, run `python3 fetch_live.py && python3 parse_live.py`;
  non-fatal: `|| log "WARNING: live scores fetch failed (cache retained)"`.

## Section 3 — Page template (`build_page.py` raw string)

- New `.clive` pill rendered next to the class name in the card head for
  classes with a `live` payload field: small gold pill, text `live`,
  subtle 2 s pulse dot; `@media (prefers-reduced-motion: reduce)` disables
  the pulse; print media unaffected (reset like other vars).
- Colors via CSS custom properties (light + `html.dark` overrides),
  consistent with the "up next" gold family; the pill is plain text + dot
  (no emoji).
- No changes to display order, filters, done/up-next logic — the merged
  places flow through the existing `e` array.

## Section 4 — Tests

- `tests/test_live.py` (new, stdlib):
  - fixture: a saved real callback response (today's `SHOWALLDETAIL`
    capture) committed under `tests/fixtures/`;
  - response parse → expected classes/placings (entry #, place);
  - `updated`-string → minutes (`53 min`, `1 hour, 51 min`, `2 hours, 2
    min`);
  - merge rule: official wins over live; live fills gaps; classes absent
    from cache untouched;
  - cache: accumulates across simulated runs, idempotent on re-run,
    unchanged on failed fetch (no live.json);
  - freshness cutoff: 59 min → `live` present, 61 min → absent.
- `tests/test.js` additions (pinned date as today):
  - pill present exactly for `live` classes, absent otherwise;
  - an entry with no official place but a cached-live place renders its
    gold place;
  - up-next follows merged data (live-placed class no longer "up next").
- Existing suites (test_asof, test_frontier, test_payload, test_ui_only,
  jsdom) stay green.

## Section 5 — Docs

- `AGENTS.md`: commands (fetch/parse live), architecture (new data source,
  merge rule, cache), git-ignored intermediates (`live.json`,
  `live_cache.json`), and a tip that the callback protocol is
  reverse-engineered (breakage degrades to official-only; see spec
  "Callback protocol" for the wire format).
- `refresh/README.md`: the live stage in the pipeline diagram.

## Out of scope (follow-ups)

- Driving the cron frontier from the live list (rejected for now — keep
  existing frontier).
- Displaying live **scores** (column empty in sampled classes).
- A "live Xm ago" time text on the pill (user chose pill only).
- Not-placed detail (the live page doesn't render it).
