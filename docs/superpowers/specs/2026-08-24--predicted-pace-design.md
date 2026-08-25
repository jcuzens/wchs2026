# Predicted pace ("up next" prediction) — design

Date: 2026-08-24
Status: approved (sectioned design approved in chat 2026-08-24).

## Problem

Official class-results placings are delayed — a class can be scored and
placed for tens of minutes (or hours) before its `ClassResults.aspx` page
updates. The current "up next" card (first class in display order with no
official placings) therefore lags reality badly. Concrete example,
2026-08-24 21:32 ET: official placings existed through class 74, but the
first no-placings class was **62** (Monday morning session) — ~13 classes
behind the live grid, whose newest observation was class 74 at 21:03.

## Goal

Predict the show's progress from a pace heuristic, the published session
start times, and live-grid observations — and display it clearly labeled
as a prediction:

1. The single highlighted card ("up next" family) reflects reality:
   **"on now · est H:MM"** while a class's predicted window contains
   "now", otherwise **"up next · est H:MM"** for the next class to start.
2. Classes predicted to have finished but lacking official placings get an
   **"awaiting results"** badge.
3. Predicted times are visually and textually distinct from official data
   ("est" marker, dashed badge, footnote).

## Approved decisions

- **Approach B** (recommended over pure-schedule and server-side status):
  per-session schedule model, anchored to the newest live observation,
  evaluated client-side on the user's own clock.
- **Pace:** 13.5 wall-clock minutes per class slot (includes turnover).
- **Champion equitation:** 25 minutes per class (user-chosen). Detected by
  class name matching both *equitation* and *champion*
  (currently #146 Senior, #158 Junior).
- **Anchor:** the session holding the newest live observation (the class
  whose last placing first appeared most recently in the live cache) is the
  "hot" session; its whole timeline is shifted so that observed class's
  predicted end equals the observed end. Positive shift capped at
  **+180 min**. All other sessions run pure schedule.
- **Evaluation:** client-side from the user's clock; the payload carries
  per-class predicted start/end; a 60 s tick advances the badges in place.
- **Official placings always beat the model** (same principle as the live
  merge): a placed class is "done", never "on now" or "awaiting".
- Pill labels: "on now · est …" / "up next · est …" / "awaiting results".

## Key existing facts

- **Rings:** the LiveScoring grid has Ring 1 / Ring 2, but observed
  behavior is one ring per session (the Monday morning block is all Ring 1,
  the night block all Ring 2; `ord` resets per ring). The model is
  therefore one sequential timeline per session. If the show ever splits a
  session across rings, the model degrades gracefully: official placings
  still win, windows are just less accurate.
- **Observation signal:** the first-seen `at` timestamps in
  `live_cache.json` (per entry; `fold_live_cache` keeps the first stamp on
  re-folds, so they are immutable once folded). A class's observed end is
  the **latest** first-seen `at` across its entries (when its last placing
  first appeared). The live grid's "Updated Xm ago" column
  (`updated_min` in `live.json`) is deliberately NOT the anchor: it is a
  rounded relative string, so `fetched − updated_min` jitters by up to a
  minute across fetches and would wobble the asof stamp (and gain spurious
  "Refresh entries" commits) on every cron cycle. `fetched` is stamped in
  America/New_York (`fetch_live.py`), matching the model's zone.
- **Session starts:** `schedule.json` (11:00 a.m., 9:00 a.m., 12:00 Noon,
  6:30 p.m., 7:00 p.m.); `data.json`/payload classes carry the joined
  session slot (`weekday`, `period`, `date`, `time`); sub-classes
  (`x.y`) inherit the parent's slot.
- **Payload classes** carry `n`, `name`, `e` (with `e[6]` = place), `date`
  ("August 24"), `period`, `time`. The asof policy compares the JSON of
  the `classes` array, so new per-class fields are picked up
  automatically; an anchor shift counts as a real data change.
- **Page JS** already groups day → session (period order
  Morning < Afternoon < Night) → `parseFloat(n)`, exposes pure helpers on
  `window` (`isPastDay`, `defaultFiltersOpen`, …) unit-tested in
  `tests/test.js`, where "now" is pinned to 2026-08-25 10:00 via a `Date`
  subclass. `window.__POLL_MS` is the existing pattern for a
  test-configurable timer.
- **Observed pace check (2026-08-24):** Monday night session (6:30 pm
  start) — class 64 observed 18:54, class 74 observed 21:03: ~12 min/class
  between first and last observation, consistent with the 13.5 default.
  Monday morning (9:00 am start) — class 48 observed 09:52; class 62's
  observation at 18:53 is an outlier (secretary batch post), which is why
  only the hot session is anchored and the shift is capped.

## Section 1 — Model (`refresh/predict.py`, new pure module)

No I/O; imported by `build_page.py` and the tests (mirrors
`live_scores.py`).

Constants:

```
PACE_MIN        = 13.5    # wall-clock minutes per class slot
CHAMP_EQ_MIN    = 25.0    # champion equitation pattern classes
MAX_SHIFT_MIN   = 180.0   # cap on positive hot-session anchor shift
SHOW_YEAR       = 2026
TZ              = America/New_York
```

Functions:

- `is_champion_equitation(name)` — name is not None and matches both
  `equit` and `champion` (case-insensitive).
- `session_key(c)` — `(c.get("day"), c.get("per"), c.get("time"))`
  (payload keys); a class missing any of the three is excluded from
  windows (defensive).
- `num_order(n)` — `tuple(int(p) for p in n.split("."))`
  (so 45 < 45.1 < 45.2 < 46).
- `parse_session_start(date_str, time_str)` — UTC epoch seconds. Delegates
  the month/time formats ("H:MM a.m." / "H:MM p.m." / "12:00 Noon") to
  `select_frontier.parse_session_time(..., SHOW_YEAR)`, then attaches `TZ`;
  None when unparseable.
- `build_windows(classes, cache=None)` — returns `{num: (ps, pe)}` in UTC
  epoch seconds (ints). `cache` is the `live_cache.json` dict.

Algorithm:

1. Group classes by `session_key`; sort each group by `num_order`.
2. Duration: `CHAMP_EQ_MIN` if `is_champion_equitation(name)` else
   `PACE_MIN`.
3. Walk each group from its published start: `ps[0] = start`,
   `pe[k] = ps[k] + dur[k]`, `ps[k+1] = pe[k]` (contiguous). Sub-classes
   are independent slots (they run separately; live `ord` confirms).
4. Anchor — only when `cache` is a non-empty dict:
   - For each cache class that has a model window and at least one
     parseable entry `at`: `end_obs = max(epoch(at) over its entries)`
     (show-local minute stamps in `TZ`; immutable per entry).
   - Take the newest `end_obs` (ties → later class number).
   - Hot session = the session containing that class.
   - `shift = end_obs − model_pe(that class)`; clamp: `shift ≤
     MAX_SHIFT_MIN` (negative shift is uncapped — it is naturally bounded).
   - Add `shift` to every window in the hot session.
5. `cache` missing/empty → pure schedule (identical output to no cache).
   A deleted cache degrades this way for at most one cron cycle (it
   re-accumulates from `live.json` on the next fold).
6. **Determinism:** the model never reads wall-clock "now"; same inputs
   always give the same `ps`/`pe`. The asof policy and `--ui-only` are
   therefore untouched.

## Section 2 — Build integration (`refresh/build_page.py`)

- The existing `live.json` read (gold "live" pill, `updated_min < 60`) and
  the `live_cache.json` read (live merge) are unchanged.
- After the live merge, compute `wins = predict.build_windows(classes,
  cache)` and add `"ps"`, `"pe"` to each class dict that has a window
  (defensive: omit if absent). Insertion order is fixed, so the JSON
  shape is stable.
- `--ui-only` path: unchanged (re-embeds the existing payload).
- asof: no code change — the `classes` comparison includes `ps`/`pe`, so
  a real anchor shift updates the stamp; a rebuild with unchanged
  `data.json` + unchanged observed times is byte-identical.

## Section 3 — Client status (template JS)

Pure helpers (window globals, unit-tested from `tests/test.js`):

```
isDone(c)                       // existing: any e[6] != null
onNowCls(classes, nowMs)        // !isDone, c.ps and c.pe present,
                                //   c.ps*1000 <= nowMs < c.pe*1000; if more
                                //   than one matches (a late session
                                //   overlaps the next), the LATEST ps wins;
                                //   null if none
upNextCls(classes, nowMs)       // onNowCls, else first !isDone class in
                                //   display order (buildSchedule order)
                                //   with c.ps present and c.ps*1000 > nowMs;
                                //   null if none
isPendingCls(c, nowMs)          // !isDone, c.pe present, nowMs >= c.pe*1000
fmtShowTime(epochSec)           // Intl.DateTimeFormat, timeZone
                                //   "America/New_York", hour numeric +
                                //   minute 2-digit -> "7:15 PM"
```

`frontierNum()` is removed; `upNextCls` replaces it for both the highlight
and the scope-mode injection.

Rendering (`renderSchedule` / `makeClass`):

- `hot = upNextCls(DATA.classes, Date.now())` once per render.
- `hot`'s card: existing `.cls.now` border + `.cnow` pill, text
  `"on now · est " + fmtShowTime(c.pe)` when `onNowCls === hot`, else
  `"up next · est " + fmtShowTime(c.ps)`.
- `isPendingCls(c, now)` cards: `.cpend` pill, text `"awaiting results"`,
  `title` = `"est done " + fmtShowTime(c.pe) + " (predicted)"`.
- "Hide done" is unchanged: awaiting classes have no official placings, so
  they stay visible. The gold live pill and these badges coexist.
- Every class card gets `dataset.num` (needed by the tick below).

Tick:

```
TICK_MS = window.__TICK_MS (number) or 60000
```

- `refreshStatus()`: if a control has focus (`focusInBody()`), skip (next
  tick picks it up); else recompute `hot` and the per-class pending state
  at `Date.now()` and apply targeted updates to rendered `.cls` elements:
  toggle the `now` class, upsert/remove the `.cnow` and `.cpend` pills.
  **No full re-render** — scroll, open cards, and focus are untouched.
- Chained `setTimeout` like `poll`; paused while `document.hidden`,
  resumed on `visibilitychange`. Started in the init block.
- A full re-render (payload change / state change) rebuilds the pills from
  the same helpers, so the tick and renders can't disagree.

## Section 4 — UI / CSS

- `.cnow` (existing amber pill): now carries the est time
  ("on now · est 7:15 PM" / "up next · est 7:30 PM"). The header is
  `flex-wrap`, so the longer text wraps rather than truncating.
- `.cpend` (new): dashed-border badge — the visual "not official" cue:
  `background: var(--now-bg); border: 1px dashed var(--now-line);
  color: var(--gold); border-radius: 6px; font-size: 11px; padding: 1px
  6px; flex: none;` (works in both themes; print OK).
- Footnote appended at the bottom of `main` (rebuilt each render):
  `"est" times are predictions from an average class pace (~13.5 min);
  actual order may vary.`
- No other layout changes.

## Section 5 — Tests

`tests/test_predict.py` (new; plain Python, stdlib, style of
`test_frontier.py`):

1. Contiguity + anchor: synthetic session — first `ps` equals the
   published start epoch; `pe[k] == ps[k+1]` throughout.
2. Champion equitation: a name matching equitation+champion gets a 25-min
   slot; plain equitation gets 13.5.
3. Sub-class ordering: 4 < 5.1 < 5.2 < 6 in the cumulative walk; a
   class's observed end is the LATEST first-seen `at` across its entries.
4. Hot-session anchor: synthetic cache whose newest first-seen `at`
   belongs to a night-session class — that class's `pe` equals the
   observed epoch exactly; other classes in that session shift by the same
   delta; other sessions unchanged.
5. Cap: observation ~16 h after the model's end → shift clamped to 180
   min; a negative shift (early start) is not capped. A tie on observed
   end → the later class number anchors.
6. Degrade: cache None / `{}` / corrupt `at` strings / cache class with no
   model window → output identical to the pure-schedule result; a class
   without a session slot gets no window and doesn't affect the rest.
7. Determinism: two calls, same inputs → equal output.
8. Session-start parsing (a.m. / Noon / p.m. / garbage) via
   `parse_session_start`.

`tests/test_live.py` (extended):

- `fold_live_cache` keeps the first-seen `at` when an entry is re-folded
  (a re-score updates `p` only); a new entry is stamped with the fetch
  time. (This is what makes the anchor stable — see Observation signal.)

`tests/test.js` (updated; still runs against the freshly built
`index.html`, still self-consistent as the live show progresses):

- Frontier-based expectations switch to the page's own functions with the
  pinned clock: `hot = w.upNextCls(DATA.classes, PIN_MS)`; the `.cls.now`
  card must be `hot`; exactly one (or zero) `.cls.now`.
  The old "all classes before the current are done" check becomes: every
  non-done card rendered before the hot card is either past its window
  (carries `.cpend`) or inside its own window (the late-session-overlap
  edge where its window still contains the pinned "now").
- New: `.cpend` count equals the number of payload classes with
  `!isDone && c.pe != null && c.pe*1000 <= PIN_MS`.
- New unit block for `onNowCls` / `upNextCls` / `isPendingCls` with
  synthetic classes: boundary at `ps` (on) and `pe` (pending); overlap →
  latest ps wins; official placings override "on"; `upNext` picks the
  first !done with `ps > now`; all-done/all-past → null.
- New tick test: dom with `__TICK_MS = 50` and a test-side Date seam
  (`w.__advance(ms)`, extends the existing `pinDate`); advance just past
  the hot class's `pe` → after a few ticks the highlight and pills moved
  to the expected next class **in place**: `#schedule` first-child
  identity unchanged (no re-render), the old hot card gained `.cpend`.
- All unrelated checks (filters, scope, day collapse, persistence, mobile,
  live polling) stay; the live-update expectations that used
  `orderedClasses().find(!isDone)` are recomputed with `upNextCls`.

`tests/test_payload.py` (extended):

- Every class has integer `ps`/`pe` with `pe > ps`.
- Within each (day, period, time) session group, `ps` is non-decreasing in
  class-number order.
- The payload's windows equal `predict.build_windows(payload_classes,
  live_cache)` exactly (build wiring + anchor + cap in one invariant).
- Existing asof / ui-only / frontier suites pass unchanged (the asof
  comparison includes `ps`/`pe` automatically; they're stable across
  rebuilds with unchanged inputs).

## Section 6 — Docs, rollout, rollback

- AGENTS.md: architecture bullet for the predicted-pace model (constants,
  hot-session anchor rule, client-side evaluation, "official placings
  always beat the model") + `tests/test_predict.py` in Commands.
- README.md: one user-facing line about "est" times being predictions.
- Rollout: the show is live — the cron picks up the rebuild within ~8 min;
  verify for a few cycles that the highlighted card tracks the live grid
  within ~1–2 classes, and that `git log` doesn't gain "Refresh entries"
  commits while data is unchanged (asof discipline intact).
- Rollback / failure modes: the model is display-only — it never touches
  placings, the live merge, or the cron frontier fetch
  (`select_frontier.py` stays results-based). A broken `live.json`
  degrades to pure schedule (spec'd in the model); a deleted/absent live
  cache degrades the same way, for at most one cron cycle. A model
  *exception*
  propagates and fails the build: the cron then commits nothing and the
  published site keeps the last good payload — a model bug should be
  loud, not silent. The only silent path is a class missing a session
  slot (excluded from windows; JS null-guards skip it) — no class in the
  current data is affected.

## Out of scope (YAGNI)

- No pace learning/fitting beyond the single-point anchor (no regression,
  no per-class durations).
- No per-ring model (rings are per-session today; see Key existing facts).
- No server-side status computation; the client evaluates.
- No auto-hiding of awaiting-results classes, no per-class confidence.
- No changes to the cron frontier fetch, the live merge, or the live pill.
- No anchor hysteresis or state file: the first-`at` signal is immutable
  per entry, so the anchor is stable without extra state.
