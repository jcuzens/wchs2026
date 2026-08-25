# Predicted Pace ("Up Next" Prediction) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or execute inline.

**Goal:** Predict each class's start/end from a per-session pace model anchored to the newest live observation, and display it on the schedule page as clearly-labeled "est" times ("on now" / "up next" / "awaiting results").

**Architecture:** A new pure Python module (`refresh/predict.py`) walks each session's classes from the published start at 13.5 min/class (25 min for champion equitation); the session holding the newest live observation ("hot" session) is shifted so that class's predicted end equals the observed end (positive shift capped at +180 min). The build stamps each payload class with `ps`/`pe` (UTC epoch seconds); the page evaluates status client-side on the user's clock and refreshes the pills in place on a 60 s tick (no re-render). Official placings always beat the model. The anchor uses the live cache's immutable first-seen `at` timestamps — not `live.json`'s rounded "Updated Xm ago" column, which jitters across fetches and would wobble the asof stamp.

**Tech Stack:** Python 3 stdlib only (`zoneinfo`), the page stays one dependency-free HTML file, jsdom for the page smoke tests.

**Spec:** `docs/superpowers/specs/2026-08-24--predicted-pace-design.md` (approved; amended 2026-08-24 for the anchor signal — see "Key existing facts → Observation signal").

## Global Constraints

- `index.html` is **generated** — all markup/CSS/JS edits go into the `r"""..."""` raw-string template in `refresh/build_page.py`, then rebuild. Keep the `r` prefix (JS regex with backslashes). Never hand-edit `index.html`.
- The page stays dependency-free: no external requests, no new JS libraries. The pipeline stays Python stdlib + curl.
- The model is **deterministic**: same inputs → same `ps`/`pe`; it never reads wall-clock "now" (the asof policy depends on this). The anchor's `at` stamps are immutable per entry, so a rebuild around unchanged data is byte-identical.
- **Official placings always beat the model:** a class with any `e[6]` is never "on now", "up next", or "awaiting".
- Git-ignored intermediates (`refresh/live_cache.json`, `refresh/live.json`, `refresh/data.json`, …) are never staged or committed.
- Never print `git remote -v` (the origin URL embeds a PAT).
- Commit style: short imperative subject (`feat:` / `test:` / `docs:`), stage only the intended files.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `refresh/live_scores.py` | `fold_live_cache` keeps the first-seen `at` per entry (anchor stability) | Modify |
| `refresh/predict.py` | Pure pace model: constants, `is_champion_equitation`, `num_order`, `session_key`, `parse_session_start`, `build_windows` | Create |
| `refresh/build_page.py` | Stamp `ps`/`pe` per payload class; template JS: pace helpers, rendering switch, tick, `.cpend` CSS, footnote | Modify |
| `tests/test_live.py` | Fold first-`at` / re-score tests | Modify |
| `tests/test_predict.py` | Model unit tests (synthetic two-session fixture) | Create |
| `tests/test_payload.py` | `ps`/`pe` invariants + model-equality wiring check | Modify |
| `tests/test.js` | Pace-helper unit tests, DOM status checks (replacing frontier expectations), tick test | Modify |
| `AGENTS.md` | Architecture bullet + command | Modify |
| `README.md` | One user-facing bullet about "est" times | Modify |

Test commands (from the repo root):

```bash
python3 tests/test_live.py          # fold/merge protocol tests (fixtures)
python3 tests/test_predict.py       # model unit tests
python3 tests/test_payload.py       # payload/asof invariants (takes the cron lock)
python3 refresh/build_page.py       # rebuild index.html + payload.json
npm --prefix tests test             # page smoke suite against the built index.html
```

---

### Task 1: `fold_live_cache` keeps the first-seen "at"

The pace model anchors on first-observation times. Today `fold_live_cache`
overwrites each entry's `at` with the latest fetch time, so no stable
observation time exists. Make `at` = first-seen (immutable), `p` = latest.

**Files:**
- Modify: `refresh/live_scores.py:205-213` (`fold_live_cache`)
- Test: `tests/test_live.py` (insert after line 134, the "cache: idempotent on re-run" check)

**Interfaces:**
- Consumes: existing cache shape `{num: {entry: {"p": int, "at": "YYYY-MM-DD HH:MM"}}}`.
- Produces: `fold_live_cache(cache, live)` — `at` is the FIRST-seen fetch timestamp (kept on re-folds); `p` tracks the latest place.

- [ ] **Step 1: Write the failing test**

Insert into `tests/test_live.py` immediately after the line
`check("cache: idempotent on re-run", c == snapshot)`:

```python
# first-seen timestamp is stable across re-folds (the predicted-pace model
# anchors on it; a moving stamp would wobble the asof stamp)
live3 = {"fetched": "2026-08-24 09:36",
         "classes": [{"num": "48", "entries": [["1158", "H", "R", 3]]}]}
c_snap = json.loads(json.dumps(c))
ls.fold_live_cache(c, live3)
check("cache: re-score updates the place", c["48"]["1158"]["p"] == 3)
check("cache: first-seen at kept on re-fold", c["48"]["1158"]["at"] == "2026-08-24 09:20")
check("cache: other entries untouched",
      c["48"]["958"] == c_snap["48"]["958"] and c["49"] == c_snap["49"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_live.py`
Expected: FAIL on `cache: first-seen at kept on re-fold` (current code stamps `09:36`), everything else passes.

- [ ] **Step 3: Write the implementation**

Replace `fold_live_cache` in `refresh/live_scores.py`:

```python
def fold_live_cache(cache, live):
    """In place: fold a live.json payload into the accumulating cache.
    Grows only — no deletes during the show; re-folding is idempotent.
    "at" is the FIRST-seen fetch timestamp (kept on re-folds so it stays
    stable; the predicted-pace model anchors on it); "p" tracks the latest
    place (re-scoring can change it)."""
    fetched = live.get("fetched", "")
    for c in live.get("classes", []):
        cls = cache.setdefault(c["num"], {})
        for entry, _horse, _rider, place in c.get("entries", []):
            e = cls.get(str(entry))
            if e is None:
                cls[str(entry)] = {"p": place, "at": fetched}
            else:
                e["p"] = place
    return cache
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_live.py`
Expected: ALL PASS (the existing `c["48"]["958"]["at"] == "2026-08-24 09:28"` check still holds — 958 first appears in `live2`, fetched 09:28).

- [ ] **Step 5: Commit**

```bash
git add refresh/live_scores.py tests/test_live.py
git commit -m "feat: fold_live_cache keeps first-seen at (stable pace anchor)"
```

---

### Task 2: the pure pace model (`refresh/predict.py`)

**Files:**
- Create: `refresh/predict.py`
- Test: `tests/test_predict.py`

**Interfaces:**
- Consumes: `select_frontier.parse_session_time(date_str, time_str, year=SHOW_YEAR)` (naive show-local datetime or None) and `select_frontier.SHOW_YEAR` (2026); payload-shaped class dicts (`n`, `name`, `day`, `per`, `time`); the live-cache dict from Task 1.
- Produces: `build_windows(classes, cache=None)` → `{num: (ps, pe)}` in UTC epoch **seconds (ints)**; plus `is_champion_equitation(name)`, `num_order(n)`, `session_key(c)`, `parse_session_start(date_str, time_str)`, constants `PACE_MIN=13.5`, `CHAMP_EQ_MIN=25.0`, `MAX_SHIFT_MIN=180.0`, `TZ=ZoneInfo("America/New_York")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_predict.py`:

```python
#!/usr/bin/env python3
"""Predicted class windows (refresh/predict.py): per-session pace model,
hot-session anchor from the live cache's first-seen timestamps, the 180-min
cap, degrade paths, determinism."""
import datetime, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import predict as pr

TZ = pr.TZ
def ep(y, mo, d, h, mi):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp())

A_START = ep(2026, 8, 22, 10, 0)   # session A: Saturday Morning, 10:00 a.m.
B_START = ep(2026, 8, 22, 18, 0)   # session B: Saturday Night, 6:00 p.m.
PACE = int(pr.PACE_MIN * 60)       # 810 s
CHAMP = int(pr.CHAMP_EQ_MIN * 60)  # 1500 s

def cls(n, name, day="August 22", per="Morning", time="10:00 a.m."):
    return {"n": n, "name": name, "day": day, "per": per, "time": time, "e": []}

B = "6:00 p.m."
A1 = cls("1", "Hunt Seat Equitation")
A2 = cls("2", "Champion Equitation")
B4 = cls("4", "Hunt Seat Equitation", per="Night", time=B)
B51 = cls("5.1", "Hunt Seat Equitation", per="Night", time=B)
B52 = cls("5.2", "Hunt Seat Equitation", per="Night", time=B)
B6 = cls("6", "Hunt Seat Equitation", per="Night", time=B)
ALL = [A1, A2, B4, B51, B52, B6]

base = pr.build_windows(ALL)

# 1. pure schedule: contiguous walk from the published start
check("first ps = published start", base["1"][0] == A_START, str(base["1"]))
check("session B starts at its published time", base["4"][0] == B_START, str(base["4"]))
check("contiguous within a session",
      base["1"][1] == base["2"][0]
      and base["4"][1] == base["5.1"][0]
      and base["5.1"][1] == base["5.2"][0]
      and base["5.2"][1] == base["6"][0], str(base))

# 2. durations: champion equitation 25 min, everything else 13.5
check("champion equitation gets a 25-min slot",
      base["2"] == (A_START + PACE, A_START + PACE + CHAMP), str(base["2"]))
check("plain class gets 13.5 min", base["1"] == (A_START, A_START + PACE), str(base["1"]))
check("is_champion_equitation needs both words",
      pr.is_champion_equitation("Champion Equitation")
      and pr.is_champion_equitation("EQ - Champion Equitation - Senior")
      and not pr.is_champion_equitation("Equitation - Open")
      and not pr.is_champion_equitation("Champion Hunter")
      and not pr.is_champion_equitation(None))

# 3. observed end = the LATEST first-seen at across a class's entries
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"},
                                 "2": {"p": 2, "at": "2026-08-22 18:41"}}})
check("observed end = latest first-seen at", w["4"][1] == B_START + 6 * 60, str(w["4"]))

# 4. hot-session anchor: observed class pe = observed end, the rest of the
#    hot session shifts by the same delta, other sessions untouched
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}})
check("anchor: observed class pe = observed end", w["4"][1] == B_START + 5 * 60, str(w["4"]))
check("anchor: hot session shifted by the same delta",
      w["4"][0] == B_START + 5 * 60
      and w["5.1"][0] == B_START + 5 * 60 + PACE
      and w["6"][1] == B_START + 5 * 60 + 4 * PACE, str(w))
check("anchor: other sessions unchanged",
      w["1"] == base["1"] and w["2"] == base["2"], str(w))

# 5. cap: a very late observation clamps the positive shift at 180 min;
#    a negative shift (early start) is not capped
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-23 10:00"}}})
check("cap: positive shift clamped at 180 min", w["4"][0] == B_START + 180 * 60, str(w["4"]))
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 17:50"}}})
check("cap: negative shift not capped", w["4"][1] == B_START - 10 * 60, str(w["4"]))

# 6. degrade: no/empty/corrupt cache -> pure schedule; unknown numbers and
#    slot-less classes are ignored
check("degrade: no cache", pr.build_windows(ALL) == base)
check("degrade: empty cache", pr.build_windows(ALL, {}) == base)
check("degrade: corrupt at ignored",
      pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "whenever"}}}) == base)
check("degrade: cache class with no window ignored",
      pr.build_windows(ALL, {"99": {"1": {"p": 1, "at": "2026-08-22 18:35"}}}) == base)
noslot = cls("9", "no slot", day=None)
check("no-slot class gets no window, others fine",
      "9" not in pr.build_windows(ALL + [noslot])
      and pr.build_windows(ALL + [noslot])["1"] == base["1"])

# 7. tie: same observed end -> the later class number anchors
w = pr.build_windows(ALL, {"2": {"1": {"p": 1, "at": "2026-08-22 10:20"}},
                           "4": {"1": {"p": 1, "at": "2026-08-22 10:20"}}})
check("tie: later class number is the anchor",
      w["4"][1] == A_START + 20 * 60 and w["1"][0] == A_START, str(w["4"]))

# 8. determinism
check("deterministic: same inputs -> same output",
      pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}})
      == pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}}))

# 9. session-start parsing (delegates to select_frontier)
check("parse a.m. start", pr.parse_session_start("August 22", "10:00 a.m.") == A_START)
check("parse Noon start",
      pr.parse_session_start("August 23", "12:00 Noon") == ep(2026, 8, 23, 12, 0))
check("parse p.m. start", pr.parse_session_start("August 22", "6:00 p.m.") == B_START)
check("parse garbage -> None", pr.parse_session_start("August 22", "whenever") is None)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_predict.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'predict'`.

- [ ] **Step 3: Write the implementation**

Create `refresh/predict.py`:

```python
#!/usr/bin/env python3
"""Predicted class windows for the schedule page.

Pure module: same inputs -> same output (it never reads wall-clock "now"),
so the asof policy is untouched. build_page.py imports it to stamp each
payload class with ps/pe (UTC epoch seconds); the page evaluates "on now" /
"up next" / "awaiting" client-side on the user's own clock.

Model: one sequential timeline per session, walking from the published
session start at PACE_MIN per class (CHAMP_EQ_MIN for champion equitation).
The session holding the newest live observation (the "hot" session) is
shifted so that observed class's predicted end equals the observed end; a
positive shift is capped at MAX_SHIFT_MIN. Official placings always beat
the model (enforced by the page, not here).

Observation source: the first-seen "at" timestamps in live_cache.json
(immutable per entry once folded — fold_live_cache keeps the first stamp).
A class's observed end is the LATEST first-seen "at" across its entries
(when its last placing first appeared). The live.json "Updated Xm ago"
column is deliberately NOT used: it is a rounded relative string, so the
reconstructed absolute time jitters by a minute across fetches and would
wobble the asof stamp on every cron cycle.

See docs/superpowers/specs/2026-08-24--predicted-pace-design.md
"""
import datetime
from zoneinfo import ZoneInfo

import select_frontier as sf

PACE_MIN = 13.5        # wall-clock minutes per class slot (incl. turnover)
CHAMP_EQ_MIN = 25.0    # champion equitation pattern classes
MAX_SHIFT_MIN = 180.0  # cap on the positive hot-session anchor shift
TZ = ZoneInfo("America/New_York")

def is_champion_equitation(name):
    """Name matches both 'equit' and 'champion' (case-insensitive)."""
    if not name:
        return False
    n = name.lower()
    return "equit" in n and "champion" in n

def num_order(n):
    """45 < 45.1 < 45.2 < 46."""
    return tuple(int(p) for p in str(n).split("."))

def session_key(c):
    """Payload keys; a class missing any of the three has no window."""
    return (c.get("day"), c.get("per"), c.get("time"))

def parse_session_start(date_str, time_str):
    """'August 24' + '1:00 p.m.' -> UTC epoch seconds; None when
    unparseable. Delegates the formats to
    select_frontier.parse_session_time (naive show-local time), then
    attaches the show zone."""
    dt = sf.parse_session_time(date_str or "", time_str or "", sf.SHOW_YEAR)
    if dt is None:
        return None
    return int(dt.replace(tzinfo=TZ).timestamp())

def _at_epoch(s):
    """A cache 'at' stamp (show-local '%Y-%m-%d %H:%M') -> epoch seconds."""
    try:
        dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    return int(dt.replace(tzinfo=TZ).timestamp())

def build_windows(classes, cache=None):
    """{num: (ps, pe)} in UTC epoch seconds (ints) for every class with a
    session slot. cache: the live_cache.json dict; None/empty -> pure
    schedule. Deterministic: same inputs -> same output."""
    sessions = {}
    for c in classes:
        k = session_key(c)
        if any(v is None for v in k):
            continue
        sessions.setdefault(k, []).append(c)
    for k in sessions:
        sessions[k].sort(key=lambda c: num_order(c["n"]))

    wins = {}
    key_by_num = {}
    for k, cs in sessions.items():
        start = parse_session_start(k[0], k[2])
        if start is None:
            continue
        t = start
        for c in cs:
            dur = CHAMP_EQ_MIN if is_champion_equitation(c.get("name")) else PACE_MIN
            wins[c["n"]] = [t, t + dur * 60.0]
            key_by_num[c["n"]] = k
            t += dur * 60.0

    # Anchor: the newest observed end (the class whose last placing first
    # appeared most recently); ties -> later class number.
    anchor = None   # (end_obs, class_num)
    if cache:
        for num, entries in cache.items():
            if num not in wins:
                continue
            obs = None
            for e in entries.values():
                if isinstance(e, dict):
                    ep = _at_epoch(e.get("at"))
                    if ep is not None and (obs is None or ep > obs):
                        obs = ep
            if obs is None:
                continue
            if anchor is None or (obs, num_order(num)) > (anchor[0], num_order(anchor[1])):
                anchor = (obs, num)
    if anchor:
        end_obs, num = anchor
        shift = end_obs - wins[num][1]
        if shift > MAX_SHIFT_MIN * 60.0:
            shift = MAX_SHIFT_MIN * 60.0
        for c in sessions[key_by_num[num]]:
            wins[c["n"]][0] += shift
            wins[c["n"]][1] += shift

    return {n: (int(w[0]), int(w[1])) for n, w in wins.items()}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_predict.py`
Expected: ALL PASS (20 checks).

- [ ] **Step 5: Commit**

```bash
git add refresh/predict.py tests/test_predict.py
git commit -m "feat: predicted-pace model (refresh/predict.py)"
```

---

### Task 3: build integration — `ps`/`pe` in the payload

**Files:**
- Modify: `refresh/build_page.py` (the `else` branch, between the live-merge block ending at the `c["live"]` assignment and the asof block)
- Test: `tests/test_payload.py` (insert after the `a0 = asof_of_payload(...)` line)

**Interfaces:**
- Consumes: `predict.build_windows(classes, cache)` from Task 2; `cache` (the already-loaded `live_cache.json` dict, `{}` when missing).
- Produces: every payload class with a session slot gains integer `ps`, `pe` keys (UTC epoch seconds), appended after the existing keys; classes without a window are unchanged.

- [ ] **Step 1: Write the failing test**

Insert into `tests/test_payload.py` after `a0 = asof_of_payload(open(PLJ).read())`:

```python
    # 1b. predicted windows: integer ps/pe per class, ordered within a
    #     session, and equal to the pure model's output (wiring check)
    sys.path.insert(0, os.path.dirname(BUILDER))
    import predict as pr
    pl = json.loads(open(PLJ).read())
    missing = [c["n"] for c in pl["classes"]
               if not (isinstance(c.get("ps"), int)
                       and isinstance(c.get("pe"), int) and c["pe"] > c["ps"])]
    check("every class has integer ps/pe with pe > ps",
          not missing, ",".join(missing[:5]))
    groups = {}
    for c in pl["classes"]:
        groups.setdefault((c.get("day"), c.get("per"), c.get("time")), []).append(c)
    bad_sessions = []
    for key, cs in groups.items():
        if any(v is None for v in key):
            continue
        seq = [c["ps"] for c in sorted(cs, key=lambda c: float(c["n"]))]
        if any(a > b for a, b in zip(seq, seq[1:])):
            bad_sessions.append(key)
    check("predicted starts non-decreasing within a session",
          not bad_sessions, str(bad_sessions))
    cache_p = os.path.join(os.path.dirname(BUILDER), "live_cache.json")
    try:
        cache = json.load(open(cache_p))
    except (OSError, ValueError):
        cache = None
    wins = pr.build_windows(pl["classes"], cache)
    bad_wins = [c["n"] for c in pl["classes"]
                if c["n"] in wins and (c.get("ps"), c.get("pe")) != wins[c["n"]]]
    check("payload windows equal the pure model output",
          not bad_wins, ",".join(bad_wins[:5]))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/test_payload.py`
Expected: FAIL on `every class has integer ps/pe with pe > ps` (no `ps`/`pe` yet). Note this test takes the cron lock and restores `index.html`/`payload.json` at the end.

- [ ] **Step 3: Write the implementation**

In `refresh/build_page.py`, insert after the live-merge block (after the
`c["live"] = live_fresh[c["n"]]` loop, before the
`# The "Updated" timestamp only changes when the data actually changes:`
comment):

```python
    # Predicted windows: per-session pace model + hot-session anchor from
    # the live cache's first-seen timestamps. Pure function of
    # (classes, cache) — the asof policy is untouched (same inputs ->
    # same ps/pe).
    # See docs/superpowers/specs/2026-08-24--predicted-pace-design.md
    import predict as pr
    wins = pr.build_windows(classes, cache)
    for c in classes:
        w = wins.get(c["n"])
        if w:
            c["ps"], c["pe"] = w
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_payload.py`
Expected: ALL PASS. Then rebuild and eyeball the payload:

Run: `python3 refresh/build_page.py && python3 -c "import json; p=json.load(open('payload.json')); c=p['classes'][0]; print(c['n'], c['ps'], c['pe'])"`
Expected: a class number and two increasing integers.

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test_payload.py index.html payload.json
git commit -m "feat: stamp payload classes with predicted ps/pe windows"
```

(Committing the rebuilt `index.html`/`payload.json` is normal here — the
asof policy keeps the stamp unchanged when the data is unchanged.)

---

### Task 4: page JS status helpers (+ unit tests)

Pure helpers on `window`, unit-tested from `tests/test.js` with synthetic
classes. Rendering is NOT switched yet (Task 5) — `frontierNum` stays.

**Files:**
- Modify: `refresh/build_page.py` template (insert the block after the `frontierNum` function, i.e. after the `// ---- rendering` comment region — place it directly after `frontierNum`'s closing brace)
- Test: `tests/test.js` (insert a new block after the `// (6) completed-class treatment` section, i.e. after the closing `}` of the `if (FRONTIER_NUM){ ... }` block)

**Interfaces:**
- Produces (all window globals, unit-testable):
  - `displayOrderOf(classes)` → array in display order (day → period (Morning < Afternoon < Night/Evening) → `parseFloat(n)`).
  - `onNowCls(classes, nowMs)` → class with `ps*1000 <= nowMs < pe*1000` and no placings (latest `ps` wins on overlap), or null.
  - `upNextCls(classes, nowMs)` → `onNowCls`, else first display-order class with no placings and `ps*1000 > nowMs`, or null.
  - `isPendingCls(c, nowMs)` → no placings and `nowMs >= pe*1000`.
  - `fmtShowTime(epochSec)` → `"7:15 PM"` (Intl, `America/New_York`).
  - `classPill(c, nowMs, hotNum)` → `{tag:"cnow"|"cpend", text, title, clsNow}` or null (done classes → null; the hot card → `cnow` "on now"/"up next" with an est time; a past-window non-done card → `cpend` "awaiting results").
- Consumes: existing `isDone(c)`, `PER_ORDER`, payload `ps`/`pe`.

- [ ] **Step 1: Write the failing test**

Insert into `tests/test.js` after the `if (FRONTIER_NUM){ ... }` block of
section (6):

```javascript
  // (11) predicted-pace helpers (synthetic classes; the page's own fns)
  const C = (n, ps, pe, done, day, per) => ({
    n, day: day || "August 25", per: per || "Morning", ps, pe,
    e: done ? [["1","H","R","T","O","1","1"]] : [["1","H","R","T","O","1",null]],
  });
  const T0 = 1000000;
  const mOn = x => w.onNowCls(x, T0);
  check("onNow: inside window", mOn([C("1", T0/1000-10, T0/1000+10)]).n === "1");
  check("onNow: at ps boundary is on", mOn([C("1", T0/1000, T0/1000+10)]).n === "1");
  check("onNow: at pe boundary is off", mOn([C("1", T0/1000-10, T0/1000)]) === null);
  check("onNow: overlap -> latest ps wins",
        mOn([C("1", T0/1000-100, T0/1000+50), C("2", T0/1000-10, T0/1000+60)]).n === "2");
  check("onNow: done class never on", mOn([C("1", T0/1000-10, T0/1000+10, true)]) === null);
  check("onNow: missing ps -> null",
        mOn([{n:"1", day:"August 25", per:"Morning", pe:T0/1000+10, e:[["1","H","R","T","O","1",null]]}]) === null);
  const mUp = x => w.upNextCls(x, T0);
  check("upNext: on-now class wins",
        mUp([C("1", T0/1000-10, T0/1000+10), C("2", T0/1000+20, T0/1000+30)]).n === "1");
  check("upNext: first future in display order",
        mUp([C("10", T0/1000+200, T0/1000+210, false, "August 26"),
             C("3", T0/1000+20, T0/1000+30, false, "August 25", "Night"),
             C("2", T0/1000+10, T0/1000+12)]).n === "2");
  check("upNext: done classes skipped",
        mUp([C("1", T0/1000+20, T0/1000+30, true), C("2", T0/1000+40, T0/1000+50)]).n === "2");
  check("upNext: all past or done -> null",
        mUp([C("1", T0/1000-100, T0/1000-90), C("2", T0/1000-50, T0/1000-40, true)]) === null);
  const mPend = x => w.isPendingCls(x, T0);
  check("pending: at pe is pending", mPend(C("1", T0/1000-10, T0/1000)) === true);
  check("pending: before pe is not", mPend(C("1", T0/1000-10, T0/1000+1)) === false);
  check("pending: done never pending", mPend(C("1", T0/1000-10, T0/1000-5, true)) === false);
  check("pending: missing pe is not",
        mPend({n:"1", day:"August 25", per:"Morning", ps:T0/1000-10, e:[["1","H","R","T","O","1",null]]}) === false);
  const f0 = Date.UTC(2026, 7, 25, 23, 15) / 1000;   // 7:15 PM on show day (EDT)
  check("fmtShowTime: show-zone wall clock", w.fmtShowTime(f0) === "7:15 PM", w.fmtShowTime(f0));
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: FAIL on `onNow: inside window` (`w.onNowCls is not a function`), all pre-existing checks still pass.

- [ ] **Step 3: Write the implementation**

In the `refresh/build_page.py` template, insert directly after the
`frontierNum` function's closing brace:

```javascript
// ---- predicted-pace status (unit-tested)
// ps/pe are UTC epoch seconds predicted at build time (refresh/predict.py);
// official placings always beat the model.
function displayOrderOf(cls){
  const byDay = new Map();
  for (const c of cls){
    if (!byDay.has(c.day)) byDay.set(c.day, {day:c.day, sessions:new Map()});
    const d = byDay.get(c.day);
    if (!d.sessions.has(c.per)) d.sessions.set(c.per, []);
    d.sessions.get(c.per).push(c);
  }
  const days = [...byDay.values()].sort((a,b)=>parseInt(a.day.slice(-2))-parseInt(b.day.slice(-2)));
  const out = [];
  for (const d of days){
    const secs = [...d.sessions.entries()].sort((a,b)=>(PER_ORDER[a[0]]??9)-(PER_ORDER[b[0]]??9));
    for (const [, cs] of secs) out.push(...cs.slice().sort((a,b)=>parseFloat(a.n)-parseFloat(b.n)));
  }
  return out;
}
function onNowCls(classes, nowMs){
  let best = null;
  for (const c of classes){
    if (isDone(c) || c.ps == null || c.pe == null) continue;
    if (c.ps * 1000 <= nowMs && nowMs < c.pe * 1000 && (!best || c.ps > best.ps)) best = c;
  }
  return best;
}
function upNextCls(classes, nowMs){
  const on = onNowCls(classes, nowMs);
  if (on) return on;
  for (const c of displayOrderOf(classes))
    if (!isDone(c) && c.ps != null && c.ps * 1000 > nowMs) return c;
  return null;
}
function isPendingCls(c, nowMs){
  return !isDone(c) && c.pe != null && nowMs >= c.pe * 1000;
}
const SHOW_TZ = "America/New_York";
function fmtShowTime(epochSec){
  try {
    return new Intl.DateTimeFormat("en-US", {timeZone: SHOW_TZ, hour: "numeric", minute: "2-digit"}).format(new Date(epochSec * 1000));
  } catch(e){ return ""; }
}
// {tag, text, title, clsNow} for a card's predicted-status pill; null when
// the card has none (done classes, or a future class outside its window).
function classPill(c, nowMs, hotNum){
  if (isDone(c)) return null;
  if (c.n === hotNum){
    if (c.ps != null && c.ps * 1000 <= nowMs && nowMs < c.pe * 1000)
      return {tag:"cnow", text:"on now \u00b7 est " + fmtShowTime(c.pe), title:"", clsNow:true};
    return {tag:"cnow", text:"up next \u00b7 est " + fmtShowTime(c.ps), title:"", clsNow:true};
  }
  if (isPendingCls(c, nowMs))
    return {tag:"cpend", text:"awaiting results", title:"est done " + fmtShowTime(c.pe) + " (predicted)", clsNow:false};
  return null;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: ALL TESTS PASSED (the new 14 checks + all pre-existing).

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js index.html
git commit -m "feat: page predicted-pace status helpers"
```

---

### Task 5: rendering switch — `frontierNum` → predicted status

**Files:**
- Modify: `refresh/build_page.py` template (remove `frontierNum`; rework `renderSchedule`, `makeClass`; add `.cpend` CSS)
- Test: `tests/test.js` (frontier expectations → predicted-status expectations)

**Interfaces:**
- Consumes: Task 4's `upNextCls`, `classPill`, `isPendingCls`; payload `ps`/`pe`.
- Produces: one `.cls.now` card (the `upNextCls` result) carrying a `.cnow` pill ("on now · est H:MM" or "up next · est H:MM"); `.cpend` "awaiting results" pills on past-window non-done cards; every card has `dataset.num`; a `.footnote` explaining "est" times.

- [ ] **Step 1: Write the failing test**

Apply these replacements to `tests/test.js` (old → new):

**1a.** Module-level constants (the block starting `const orderedClasses = () => orderedClassesOf(DATA.classes);`):

```javascript
const orderedClasses = () => orderedClassesOf(DATA.classes);
// mirror of the page's up-next logic; the DOM identity checks cross-check
// it against the page's own upNextCls, while the mirror keeps count
// expectations computable before the dom exists
function onNowOf(cls, nowMs){
  let best = null;
  for (const c of cls){
    if (isDone(c) || c.ps == null || c.pe == null) continue;
    if (c.ps * 1000 <= nowMs && nowMs < c.pe * 1000 && (!best || c.ps > best.ps)) best = c;
  }
  return best;
}
function upNextOf(cls, nowMs){
  const on = onNowOf(cls, nowMs);
  if (on) return on;
  for (const c of orderedClassesOf(cls))
    if (!isDone(c) && c.ps != null && c.ps * 1000 > nowMs) return c;
  return null;
}
const HOT = upNextOf(DATA.classes, PIN_MS);
const HOT_NUM = HOT ? HOT.n : null;
const HOT_MATCHED = HOT ? matchTrainer(HOT) : false;
const HOT_EXTRA = HOT_NUM && !HOT_MATCHED ? 1 : 0;   // card injected beyond matches
const FILTERED_SHOWN = MATCHED_COUNT + HOT_EXTRA;
const MUTED_SHOWN = TOTAL - MATCHED_COUNT - HOT_EXTRA;         // hot card never muted
```

(delete the old `FRONTIER`, `FRONTIER_NUM`, `FRONTIER_MATCHED`, `FRONTIER_EXTRA` lines; keep `orderedClasses` — the live section still uses it to pick a test-target class.)

**1b.** Section (6) — replace the whole block from `// (6) completed-class treatment` through the end of its `if (FRONTIER_NUM){ ... }` block with:

```javascript
  // (6) completed-class treatment + predicted-pace status
  check("done pills rendered for placed classes", doc.querySelectorAll(".cdone").length === DONE_COUNT, doc.querySelectorAll(".cdone").length + " vs " + DONE_COUNT);
  check("done cards tinted", doc.querySelectorAll("main .cls.done").length === DONE_COUNT, "got " + doc.querySelectorAll("main .cls.done").length);
  const pageHot = w.upNextCls(DATA.classes, PIN_MS);
  check("mirror matches the page's upNextCls",
        (pageHot ? pageHot.n : null) === HOT_NUM, (pageHot && pageHot.n) + " vs " + HOT_NUM);
  check("current card count matches expected",
        doc.querySelectorAll("main .cls.now").length === (HOT_NUM ? 1 : 0), "got " + doc.querySelectorAll("main .cls.now").length);
  if (HOT_NUM){
    const nowCard = doc.querySelector("main .cls.now");
    check("current card is expected up-next",
          !!nowCard && nowCard.querySelector(".cnum").textContent === (pageHot ? pageHot.n : HOT_NUM),
          (nowCard && nowCard.querySelector(".cnum").textContent) + " vs " + HOT_NUM);
    const pillTxt = nowCard ? (nowCard.querySelector(".cnow").textContent || "") : "";
    const pillRe = (pageHot && pageHot.ps * 1000 <= PIN_MS && PIN_MS < pageHot.pe * 1000)
      ? /on now · est \d{1,2}:\d{2} (AM|PM)/ : /up next · est \d{1,2}:\d{2} (AM|PM)/;
    check("current card pill shows a predicted time", !!nowCard && pillRe.test(pillTxt), pillTxt);
    const cards = [...doc.querySelectorAll("main .cls")];
    const nowIdx = cards.findIndex(x => x.classList.contains("now"));
    check("cards before current are done, awaiting, or in-window",
          nowIdx >= 0 && cards.slice(0, nowIdx).every(x => {
            const c = DATA.classes.find(cc => cc.n === x.querySelector(".cnum").textContent);
            return x.classList.contains("done") || x.querySelector(".cpend") ||
              (c && c.pe != null && c.ps * 1000 <= PIN_MS && PIN_MS < c.pe * 1000);
          }), "idx " + nowIdx);
    check("current card never muted", !doc.querySelector("main .cls.now.muted"));
  }
  const PENDING_EXPECT = DATA.classes.filter(c => !isDone(c) && c.pe != null && c.pe * 1000 <= PIN_MS).length;
  check("awaiting-results pills match expectation",
        doc.querySelectorAll("main .cpend").length === PENDING_EXPECT,
        doc.querySelectorAll("main .cpend").length + " vs " + PENDING_EXPECT);
  const fnote = doc.querySelector("main .footnote");
  check("pace footnote present", !!fnote && fnote.textContent.includes("predictions"), fnote ? fnote.textContent : "missing");
```

**1c.** Done-hidden block:

```javascript
  if (HOT_NUM){
    check("current card visible with done hidden", !!doc.querySelector("main .cls.now"));
  }
```

(replaces the 3-line block; "current card first when done hidden" is deleted — awaiting classes legitimately render before the hot card when done are hidden.)

**1d.** Trainer-filter block: replace `if (FRONTIER_NUM){` with `if (HOT_NUM){` (the two checks inside are unchanged).

**1e.** Scope block: `if (FRONTIER_NUM) check("current card shown in scope", ...)` → `if (HOT_NUM) check(...)`.

**1f.** Division-filter expectations: replace `FRONTIER_NUM` with `HOT_NUM` and `FRONTIER.div` with `HOT.div` in the `fInRp` / `expectedDivs` / `expectedN` lines.

**1g.** Live-update IIFE, p1 setup: comment `// phase-1 payload: settle the current frontier class, bump asof` → `// phase-1 payload: settle the current up-next class, bump asof`; `const f1 = p1.classes.find(c => c.n === FRONTIER_NUM);` → `const f1 = p1.classes.find(c => c.n === HOT_NUM);`

**1h.** Live expectations after `const P1 = w4.__live.current;`:

```javascript
        // expectations computed from the fetched payload (the show may be over
        // when this runs: HOT_NUM can be null, then p1 differs only by asof)
        const P1 = w4.__live.current;
        const P1_DONE = P1.classes.filter(isDone).length;
        const P1_HOT = upNextOf(P1.classes, PIN_MS);
        const P1_HOT_NUM = P1_HOT ? P1_HOT.n : null;
```

**1i.** Check 1: `check("live: up-next card count", ..., (P1_FRONTIER_NUM ? 1 : 0), ...)` → `(P1_HOT_NUM ? 1 : 0)`; `if (P1_FRONTIER_NUM){` → `if (P1_HOT_NUM){`; `=== P1_FRONTIER_NUM` → `=== P1_HOT_NUM` (both occurrences in that block).

**1j.** p2 setup: comment `// serve one more update: settle the next frontier class` → `// serve one more update: settle the next up-next class`; `const f2 = p2.classes.find(c => c.n === P1_FRONTIER_NUM);` → `... P1_HOT_NUM ...`; replace

```javascript
          const P2 = w4.__live.current;
          const P2_FRONTIER = orderedClassesOf(P2.classes).find(c => !isDone(c));
          const P2_FRONTIER_NUM = P2_FRONTIER ? P2_FRONTIER.n : null;
```

with

```javascript
          const P2 = w4.__live.current;
          const P2_HOT = upNextOf(P2.classes, PIN_MS);
          const P2_HOT_NUM = P2_HOT ? P2_HOT.n : null;
```

**1k.** All remaining `P2_FRONTIER_NUM` → `P2_HOT_NUM`; `P2_FRONTIER_MATCHED = P2_FRONTIER ? P2_FRONTIER.e.some(...)` → `P2_HOT_MATCHED = P2_HOT ? P2_HOT.e.some(...)`; `P2_FILTERED = P2_MATCHED + (P2_FRONTIER_NUM && !P2_FRONTIER_MATCHED ? 1 : 0)` → `P2_MATCHED + (P2_HOT_NUM && !P2_HOT_MATCHED ? 1 : 0)`.

**1l.** Check 7 (focus deferral): `if (P2_FRONTIER_NUM){` → `if (P2_HOT_NUM){`; `const f3 = p3.classes.find(c => c.n === P2_FRONTIER_NUM);` → `... P2_HOT_NUM ...`; replace

```javascript
            const P3_FRONTIER = orderedClassesOf(p3.classes).find(c => !isDone(c));
            const P3_FRONTIER_NUM = P3_FRONTIER ? P3_FRONTIER.n : null;
```

with

```javascript
            const P3_HOT = upNextOf(p3.classes, PIN_MS);
            const P3_HOT_NUM = P3_HOT ? P3_HOT.n : null;
```

and rename the remaining `P3_FRONTIER_NUM` → `P3_HOT_NUM`, `P2_FRONTIER_NUM` → `P2_HOT_NUM` in that block (including the check labels "body still shows old up-next while deferred" / "up-next advanced after deferred apply").

**1m.** Check 9 (live pill): `const P4_FRONT = orderedClassesOf(p4.classes).find(c => !isDone(c));` → `const P4_HOT = upNextOf(p4.classes, PIN_MS);`; the "live: up-next follows merged data" check →

```javascript
            check("live: up-next follows merged data",
                  P4_HOT
                    ? (!!nowCard4 && nowCard4.querySelector(".cnum").textContent === P4_HOT.n)
                    : !nowCard4,
                  (nowCard4 && nowCard4.querySelector(".cnum").textContent) + " vs " + (P4_HOT && P4_HOT.n));
```

(the `f4` test-target selection `orderedClassesOf(p4.classes).find(c => !isDone(c))` stays — it only picks which class to stamp with a live place.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: FAIL on `mirror matches the page's upNextCls` / current-card checks — the page still highlights the frontier (first no-placings class in display order), which generally is not the model's up-next (official placings lag, so frontier < up-next in class number), and no `.cpend` pills / footnote exist yet.

- [ ] **Step 3: Write the implementation**

In the `refresh/build_page.py` template:

**3a.** Delete the `frontierNum` function and its two-line comment (the block starting `// the "current" class: first class in displayed order`).

**3b.** In `renderSchedule`, replace:

```javascript
  const front = frontierNum();
```

with:

```javascript
  const nowMs = Date.now();
  const hot = upNextCls(DATA.classes, nowMs);
  const hotNum = hot ? hot.n : null;
```

Replace the scope-injection block:

```javascript
      if (on && !view.scope && front && list.some(c => c.n === front) && !vis.some(c => c.n === front)){
        vis = [...vis, list.find(c => c.n === front)];
      }
```

with:

```javascript
      if (on && !view.scope && hotNum && list.some(c => c.n === hotNum) && !vis.some(c => c.n === hotNum)){
        vis = [...vis, list.find(c => c.n === hotNum)];
      }
```

Replace `sEl.appendChild(makeClass(c, m, c.n === front));` with `sEl.appendChild(makeClass(c, m, hotNum));`.

After the `if (!rendered){ ... }` block at the end of `renderSchedule`, add:

```javascript
  main.appendChild(el("div","footnote",'"est" times are predictions from an average class pace (~13.5 min); actual order may vary.'));
```

**3c.** `makeClass` — change the signature `function makeClass(c, isMatch, isFrontier){` to `function makeClass(c, isMatch, hotNum){` and add `const isHot = c.n === hotNum;` as its first line. Replace:

```javascript
  const d = el("div","cls" + (on && !isMatch && !isFrontier ? " muted" : "") + (isDone(c) ? " done" : "") + (isFrontier ? " now" : ""));
```

with:

```javascript
  const d = el("div","cls" + (on && !isMatch && !isHot ? " muted" : "") + (isDone(c) ? " done" : "") + (isHot ? " now" : ""));
  d.dataset.num = c.n;
```

Replace `if (isFrontier) head.appendChild(el("span","cnow","up next"));` with:

```javascript
  const pill = classPill(c, Date.now(), hotNum);
  if (pill){
    const p = el("span", pill.tag, pill.text);
    if (pill.title) p.title = pill.title;
    head.appendChild(p);
  }
```

**3d.** CSS — after the `.cnow { ... }` rule add:

```css
.cpend { background: var(--now-bg); border: 1px dashed var(--now-line); color: var(--gold); border-radius: 6px; font-size: 11px; padding: 1px 6px; flex: none; }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: ALL TESTS PASSED.

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js index.html
git commit -m "feat: up-next prediction rendering (replace frontier highlight)"
```

---

### Task 6: the 60 s status tick

Advances the predicted pills in place (no re-render) so the "on now" →
"awaiting results" transition happens within a minute of the predicted
time, on the user's own clock.

**Files:**
- Modify: `refresh/build_page.py` template (tick block after the `poll` function; `visibilitychange` listener; init)
- Test: `tests/test.js` (extend `pinDate` with an `__advance` seam; tick test at the top of the live-update async IIFE, before its `await sleep(250);`)

**Interfaces:**
- Consumes: Task 5's `classPill`, `upNextCls`; `focusInBody()`.
- Produces: `window.__TICK_MS` (test seam, default 60000); `refreshStatus()` (targeted in-place pill/class updates for rendered `.cls` cards); `scheduleTick()` (chained `setTimeout`, paused while `document.hidden`); `window.__advance(ms)` (test-only pinned-clock advance).

- [ ] **Step 1: Write the failing test**

**1a.** Extend `pinDate` in `tests/test.js`:

```javascript
function pinDate(w){
  const shift = PIN_MS - Date.now();
  const Real = w.Date;
  let adv = 0;
  class D extends Real {
    constructor(...a){ a.length ? super(...a) : super(Real.now() + shift + adv); }
    static now(){ return Real.now() + shift + adv; }
  }
  w.Date = D;
  w.__advance = ms => { adv += ms; };   // tick test: move the pinned clock
}
```

**1b.** In the live-update IIFE, insert before `await sleep(250);   // several 50 ms polls have landed`:

```javascript
          // tick: the predicted pills advance in place (no re-render).
          // A dedicated dom: __TICK_MS=50 set in beforeParse + the pinDate
          // clock seam. (This dom has no fetch stub, so no polling runs.)
          const tickDom = makeDom({
            url: "https://example.com/index.html",
            beforeParse: wt => { pinDate(wt); wt.__TICK_MS = 50; },
          });
          const w5 = tickDom.window, d5 = w5.document;
          w5.addEventListener("error", e => { console.log("WINDOW ERROR (tick):", e.message); failures++; });
          const firstChild5 = d5.querySelector("#schedule").firstChild;
          const tHot = upNextOf(DATA.classes, PIN_MS);
          if (tHot && tHot.pe != null){
            const hotCard = [...d5.querySelectorAll("main .cls")].find(x => x.dataset.num === tHot.n);
            check("tick: hot card highlighted at pinned clock",
                  !!hotCard && hotCard.classList.contains("now"));
            const delta = tHot.pe * 1000 - PIN_MS + 60000;
            w5.__advance(delta);
            await sleep(300);   // several 50 ms ticks at the advanced clock
            const nowMs2 = PIN_MS + delta;
            const tHot2 = upNextOf(DATA.classes, nowMs2);
            check("tick: no re-render (first child identity)",
                  d5.querySelector("#schedule").firstChild === firstChild5);
            check("tick: old hot card lost .now", !!hotCard && !hotCard.classList.contains("now"));
            check("tick: old hot card gained awaiting pill",
                  !!hotCard && !!hotCard.querySelector(".cpend"));
            if (tHot2){
              const hotCard2 = [...d5.querySelectorAll("main .cls")].find(x => x.dataset.num === tHot2.n);
              check("tick: highlight moved to the next class",
                    !!hotCard2 && hotCard2.classList.contains("now") && !!hotCard2.querySelector(".cnow"));
            } else {
              check("tick: no future class -> no highlight",
                    d5.querySelectorAll("main .cls.now").length === 0);
            }
          } else {
            check("tick: no hot at pinned clock -> no highlight",
                  d5.querySelectorAll("main .cls.now").length === 0);
          }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: FAIL on `tick: old hot card gained awaiting pill` (no tick exists — the highlight stays put; the `w5.__advance` call is a harmless no-op since nothing reads it yet… the `hot card highlighted` check passes because rendering already works).

- [ ] **Step 3: Write the implementation**

In the `refresh/build_page.py` template, after the `poll` function (before `// ---- init`) add:

```javascript
// ---- status tick (predicted pills advance in place; never re-renders)
const TICK_MS = (typeof window.__TICK_MS === "number") ? window.__TICK_MS : 60000;
let tickTimer = null;
function refreshStatus(){
  if (focusInBody()) return;   // deferred; the next tick picks it up
  const nowMs = Date.now();
  const hot = upNextCls(DATA.classes, nowMs);
  const hotNum = hot ? hot.n : null;
  const byNum = new Map(DATA.classes.map(c => [c.n, c]));
  for (const card of document.querySelectorAll("#schedule .cls")){
    const c = byNum.get(card.dataset.num);
    if (!c) continue;
    const want = classPill(c, nowMs, hotNum);
    const wantNow = !!(want && want.clsNow);
    if (card.classList.contains("now") !== wantNow) card.classList.toggle("now", wantNow);
    const cur = card.querySelector(".cnow, .cpend");
    if (!want){ if (cur) cur.remove(); continue; }
    if (cur && cur.classList.contains(want.tag)
        && cur.textContent === want.text && (cur.title || "") === want.title) continue;
    if (cur) cur.remove();
    const p = el("span", want.tag, want.text);
    if (want.title) p.title = want.title;
    const head = card.querySelector(".cls-head");
    head.insertBefore(p, head.querySelector(".clive") || head.querySelector(".cdiv"));
  }
}
function scheduleTick(){
  clearTimeout(tickTimer);
  tickTimer = setTimeout(() => {
    if (!document.hidden){ refreshStatus(); scheduleTick(); }
  }, TICK_MS);
}
```

Replace the `visibilitychange` listener:

```javascript
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { clearTimeout(pollTimer); }
  else { clearTimeout(pollTimer); poll(); }
});
```

with:

```javascript
document.addEventListener("visibilitychange", () => {
  clearTimeout(tickTimer);
  if (document.hidden) { clearTimeout(pollTimer); }
  else { clearTimeout(pollTimer); poll(); scheduleTick(); }
});
```

In the init block, after `renderSchedule();` add `scheduleTick();`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: ALL TESTS PASSED (including the 6 new tick checks).

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js index.html
git commit -m "feat: 60s status tick for predicted pills"
```

---

### Task 7: docs + full verification

**Files:**
- Modify: `AGENTS.md` (Commands + Architecture + Tips)
- Modify: `README.md` (one bullet in "Using the page")

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: documentation + a green full-suite run.

- [ ] **Step 1: Update AGENTS.md**

In the Commands block, after the `python3 tests/test_frontier.py` line add:

```
python3 tests/test_predict.py              # predicted-pace model (synthetic sessions)
```

In the Architecture section, after the **Live scores** bullet add:

```
- **Predicted pace:** `refresh/predict.py` is a pure per-session pace
  model (13.5 min/class, 25 min champion equitation — constants in that
  file). The session holding the newest live observation is the "hot"
  session, shifted so that class's predicted end matches it (positive
  shift capped at +180 min). The build stamps each payload class with
  `ps`/`pe` (UTC epoch seconds); the page evaluates "on now" / "up next" /
  "awaiting results" client-side on the user's clock and ticks every 60 s
  in place. **Official placings always beat the model.** The model never
  reads wall-clock time, so the asof policy is untouched.
```

In "Tips for AI Agents", after the **Live protocol is reverse-engineered** tip add:

```
**The pace anchor is the live cache's first-seen `at`**, not live.json's
"Updated Xm ago": the latter is a rounded relative string whose absolute
value jitters by a minute across fetches and would wobble the asof stamp on
every cron cycle. `fold_live_cache` keeps the first `at` per entry on
purpose — don't "fix" it to the latest.
```

- [ ] **Step 2: Update README.md**

In "Using the page", after the "Under each class you'll see the **entry number and placings**…" bullet add:

```
- The highlighted card shows where the show is: **"on now · est H:MM"** or
  **"up next · est H:MM"**. Those times are *predictions* from an average
  class pace (~13.5 min, anchored to the live scoreboard) — actual order
  may vary. Classes the model has passed but that still lack official
  results are marked **"awaiting results"**.
```

- [ ] **Step 3: Full verification**

Run (from the repo root):

```bash
python3 tests/test_predict.py && python3 tests/test_live.py \
  && python3 tests/test_frontier.py && python3 tests/test_ui_only.py \
  && python3 tests/test_asof.py && python3 tests/test_payload.py
python3 refresh/build_page.py
npm --prefix tests test
python3 - <<'EOF'
import re
s = open('index.html').read()
print("classes:", len(re.findall(r'"n":"', s)))
print("entries:", len(re.findall(r'\["\d+","', s)))
print("asof:", re.search(r'"asof":"([^"]*)"', s).group(1))
EOF
git status --short
```

Expected: every suite prints ALL PASS / ALL TESTS PASSED; the verification snippet prints the class/entry counts and the asof (unchanged if the data is unchanged); `git status` shows only the intended files (no git-ignored intermediates staged — if `refresh/jar.txt` or the like appear, do not stage them).

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md README.md index.html payload.json
git commit -m "docs: predicted-pace model (AGENTS, README)"
```

(Include `index.html`/`payload.json` only if the Task 3–6 rebuilds left them changed; the asof policy keeps them byte-identical when the data is unchanged.)

---

## Self-Review

**Spec coverage:**
- §1 model (constants, functions, anchor, cap, determinism) → Task 2.
- §2 build integration (`ps`/`pe`, asof untouched) → Task 3.
- §3 client helpers (`onNowCls`/`upNextCls`/`isPendingCls`/`fmtShowTime`, `frontierNum` removed) → Tasks 4–5; tick (`TICK_MS`, `refreshStatus`, `visibilitychange`, no re-render) → Task 6.
- §4 UI (`.cnow` est text, `.cpend`, footnote, `dataset.num`) → Task 5.
- §5 tests: `test_predict.py` (items 1–8) → Task 2; `test_live.py` fold first-`at` → Task 1; `test.js` (frontier → up-next expectations, `.cpend` count, helper unit block, tick test) → Tasks 4–6; `test_payload.py` (integer `ps`/`pe`, non-decreasing, model equality) → Task 3.
- §6 docs/rollout/rollback → Task 7 (docs) + the rollout verification notes below.
- Observation-signal amendment (first-seen `at`, fold change, jitter rationale) → Tasks 1, 2 + AGENTS tip.

**Rollout note (post-merge, during the show):** the cron picks up the
rebuild within ~8 min. For a few cycles, verify (a) the highlighted card
tracks the live grid within ~1–2 classes, and (b) `git log` does not gain
"Refresh entries" commits while the data is unchanged (asof discipline
intact — the reason the anchor uses first-seen `at` stamps).

**Placeholder scan:** none — every step carries its code.

**Type consistency:** `build_windows` returns int epoch seconds (Task 2) →
payload `ps`/`pe` ints (Task 3) → JS `*1000` ms comparisons (Tasks 4–6) →
`fmtShowTime(epochSec)` takes seconds (Task 4). `classPill(c, nowMs, hotNum)`
is used identically in `makeClass` (Task 5) and `refreshStatus` (Task 6).
Test mirror `upNextOf` matches the page's `upNextCls` logic and is
cross-checked against it in the DOM section (Task 5, 1b).
