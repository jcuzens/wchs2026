# Live Scores integration — design

Date: 2026-08-24
Status: approved (sectioned design approved in chat 2026-08-24).
Protocol details corrected 2026-08-24 after end-to-end verification:
per-row `SHOWDETAILROW` (accordion detail), state from the response
envelope, growing key set.

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

### Callback POST (one per class row)

**The detail view is an accordion**: the server keeps at most one detail
row expanded per response (`SHOWALLDETAIL` expands only row 0 — do not use
it). To collect every class's placed entries the fetcher sends
**`SHOWDETAILROW <key>` once per row key** and parses the detail from each
response.

POST to the same URL, body = all form fields (step 2) + the grid state
input (step 3), then:

- `__CALLBACKID` = the grid uniqueID
- `__CALLBACKPARAM` =
  `c0:KV|<len>;<keys-json>;FR|1;0;CT|2;{};GB|<len>;<serArgs>;`
  where `<keys-json>` is the compact JSON key array, and `<serArgs>` is
  each item as `<strlen>|<item>` concatenated:
  - `SHOWDETAILROW <key>` → `13|SHOWDETAILROW<len(key)>|<key>`
  - `GOTOPAGE <n>` (0-based) → `8|GOTOPAGE1|<n>` (only needed if the GET
    page itself is paginated; callback responses always render the whole
    current window)
- `__EVENTVALIDATION` (last)

Wire facts (all verified against a jsdom capture of the real page and
end-to-end runs on 2026-08-24):

- The `c0:` prefix (callback type `c` = common, slot `0`) is **required** —
  without it the server throws `Length cannot be less than zero`.
- `FR|1;0;` (focused row 0) and `CT|2;{};` (toolbar `{}`) are part of the
  real request; sending KV+GB alone yields an empty grid (no error).
- A full/synchronous postback and the UpdatePanel async postback do **not**
  work: the grid binds data on GET only ("No data to display").
- The callback response is `0|/*DX*/({'result':{'html':'<escaped grid
  html>','stateObject':{...}},...})`. A server fault appears as
  `{'error':{'message':...}}` or `{'generalError':...}`
  (stale/corrupt state → "control callback state encryption" error —
  always re-parse state from the previous response).
- `result.html` is a JS-escaped string (unescape `\'` `\\` `\n` `\r` `\/`).
- **State comes from the envelope `stateObject`, not the response HTML.**
  The response HTML re-initializes the main grid via
  `PostponeInitialize` (no `createControl`), and it *also* contains
  `createControl` blocks for the detail sub-grids (`grPlaced_*`,
  `grNonPlaced_*`) whose state must not be confused with the main grid's.
  After each callback, re-parse `keys`/`callbackState`/`groupLevelState`
  from the envelope before the next request.
- **The key set grows while fetching** (the show is live: new classes join
  the window mid-run). Loop: expand every key of the current set, then
  re-check the set from the last response; repeat until stable (cap ~5
  rounds). Row index for a key = `keys.index(key)` in the *current* key
  list (the server expands by key, so this stays correct when the window
  shifts).
- Each response contains **all** parent rows (fresh ring/ord/progress/
  placed/updated/source) plus exactly **one** detail row (the row just
  expanded). Parse parent info from every response; parse the detail from
  the response it belongs to.
- `NEXTPAGE` (no args) errors server-side — don't use it.

### Parse

The grid's top-level rows all carry ids `<prefix>_grMain_DX*` (headers,
`DXADRow`, `DXDataRowN`, `DXDRowN`); nested table rows (progress bar,
sub-grids) do not — so split the grid HTML on
`<tr id="[^"]*_grMain_DX[A-Za-z]` to get complete rows without a
depth-tracker.

From each response:

- Parent rows (`DXDataRowN`, N = row index = position in the key list):
  columns are Ring Name, Ord, `NN - <name>` (num includes `x.y`
  sub-classes), progress bar `shown / total`, Placed, Not Placed, Updated,
  Source. The name+progress cell is the `<td id="..._tccell...">`; the four
  plain cells after it are Placed, Not Placed, Updated, Source.
- The one detail row (`DXDRowN`) holds two sub-grids:
  `grPlaced_N` (placed entries) and `grNonPlaced_N` (not placed — v1
  ignores it). Placed entry rows carry spans with ids
  `..._lbEntryNo_K` (entry #), `..._lbEntryName_K` (horse),
  `..._lbHorseDetails_K` (color/age — ignored), `..._lbCntry_K`
  (country — ignored); the rider is the bold plain cell, then two bold
  right-aligned cells: Ord (ignored) and **Place** (1-based). Score column
  empty in sampled classes — ignored in v1.

### Output: `refresh/live.json` (git-ignored)

```json
{
  "fetched": "2026-08-24 09:20",
  "classes": [
    {"num": "54", "name": "ASB Adult Five Gaited Show Pleasure Div II",
     "ring": "Ring 1", "ord": 8,
     "shown": 15, "total": 15,
     "placed": 8, "not_placed": 7,
     "updated": "32 min", "updated_min": 32, "source": "Show Secretary",
     "entries": [[1379, "SOMETHING JUSTT LIKE THIS", "VERRILL, TAYLOR", 5]]}
  ]
}
```

`entries` = `[entry#, horse, rider, place]` for placed entries only.
`updated_min` = parsed minutes (feeds the 60-min freshness cutoff). The
window can contain sub-classes that are not in `classes.json` (e.g. `55.1`,
split from its parent during the show); the merge ignores class numbers
the page doesn't know.

## Section 2 — Pipeline scripts

### `refresh/fetch_live.py` (new; stdlib only — urllib, re, json)

- Reuses the protocol helpers from `refresh/live_scores.py` (pure
  functions, unit-tested) for GET parsing, callback param building,
  response parsing.
- Warms the session (GET ShowDetails, mirroring `fetch_entries.sh`), then:
  GET `LiveScoring.aspx`, then one `SHOWDETAILROW` callback per row key,
  re-parsing state (keys/callbackState) from each response's envelope.
  Loop until the key set is stable (new classes can join the window
  mid-run); cap ~5 rounds. ~0.7 s pacing between callbacks.
- Parent-row info is collected from every response (all rows are rendered
  in each); the detail is parsed from the response that expanded it
  (accordion: only the just-expanded row is detailed).
- Writes `live.json`. Exits 0 on success.
- **Fail-safe:** any failure (no grid block, callback error, parse yields
  zero classes) → non-zero exit, **does not touch** `live.json` or
  `live_cache.json`. Cron logs a warning and continues; the page degrades
  to official-only data (today's behavior) with the cache retained.
- Request volume: one GET + N callbacks (N = class rows in the live
  window, 8–15 observed); ~8-min cron cadence makes rate limits a
  non-issue.

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
  - fixtures committed under `tests/fixtures/`:
    `live_page.html` (a real GET of LiveScoring.aspx — form fields + grid
    state) and `live_showall.txt` (a real callback response with one
    expanded detail row — the parse is identical for any
    `SHOWDETAILROW`/`SHOWALLDETAIL` response).
  - `parse_get_page` → form fields, callback ID, keys, callbackState;
  - response parse → expected classes (fixture: 8 classes 48–54, class 48
    expanded: placed 7 / not-placed 4, "2 hours, 2 min", "Show
    Secretary") and the 7 placed entries (e.g. `1158 TWENTY FOUR KARAT
    MAGIC, WITMER HAYLEN, ord 6, place 1`);
  - `updated`-string → minutes (`53 min`, `1 hour, 51 min`, `2 hours, 2
    min`, `43 min`);
  - merge rule: official wins over live; live fills gaps; classes absent
    from cache untouched;
  - cache: accumulates across simulated runs, idempotent on re-run,
    unchanged on failed fetch (no live.json);
  - freshness cutoff: 59 min → `live` present, 61 min → absent.
- `tests/test_asof.py` / `tests/test_payload.py` unchanged: the build only
  *reads* `live.json`/`live_cache.json` (never writes them), so the
  byte-identical/asof invariants hold exactly as they do for `data.json`
  (local intermediates must match the committed build — same pre-existing
  assumption).
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
- Not-placed entries (the live page renders them in a separate
  `grNonPlaced` sub-grid without placings; v1 ignores them).
