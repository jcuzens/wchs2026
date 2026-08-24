# Live Scores Integration Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or execute inline.
**Goal:** Pull the show's Live Scores tab (LiveScoring.aspx) into the pipeline so placings land within minutes of scoring and classes with fresh live activity get a gold "live" pill.
**Architecture:** A pure-function protocol/parse module (`refresh/live_scores.py`) driven by a thin network CLI (`refresh/fetch_live.py`) that walks the DevExpress ASPxGridView callback protocol (one `SHOWDETAILROW` callback per class row). A second CLI (`refresh/parse_live.py`) folds results into an accumulating git-ignored cache; `build_page.py` merges cached placings into entries that have no official place and stamps fresh classes with a `live` payload field that the template renders as a pill.
**Tech Stack:** Python 3 stdlib only (urllib, re, json, html, http.cookiejar); the page stays one dependency-free HTML file; jsdom (dev-only) for page smoke tests.
**Spec:** `docs/superpowers/specs/2026-08-24--live-scores-design.md`

## Global Constraints

- Python stdlib only in `refresh/`; no new runtime dependencies anywhere.
- `index.html` is generated — all markup/CSS/JS changes go into the `r"""..."""`
  template inside `refresh/build_page.py` (keep the `r` prefix; it is load-bearing).
- The live feature must degrade to today's exact behavior when
  `refresh/live.json` / `refresh/live_cache.json` are absent (fresh clone, failed fetch).
- Never commit git-ignored intermediates; `refresh/live.json` and
  `refresh/live_cache.json` must be git-ignored (Task 6 adds them).
- Never run `git remote -v` (the origin URL embeds a PAT).
- The `c0:` prefix, `FR|1;0;` and `CT|2;{};` segments of `__CALLBACKPARAM` are
  required by the server — do not "simplify" them away.
- Merge rule is monotonic: official placings are never overwritten by live;
  live fills gaps only.
- Test suites live in `tests/` and run as plain scripts (exit 1 on failure),
  matching `tests/test_frontier.py`'s style: `python3 tests/test_live.py`.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `refresh/live_scores.py` | Create | Pure protocol + parse + merge functions (no network, no file I/O) |
| `refresh/fetch_live.py` | Create | Network driver: session warm-up, GET, `SHOWDETAILROW` loop; writes `refresh/live.json` |
| `refresh/parse_live.py` | Create | CLI: fold `refresh/live.json` into `refresh/live_cache.json` (paths overridable for tests) |
| `refresh/build_page.py` | Modify | Merge cache into `classes`; add `live` payload field; `.clive` pill in template |
| `refresh/refresh_cron.sh` | Modify | Non-fatal live phase after the class-fetch phase |
| `.gitignore` | Modify | `refresh/live.json`, `refresh/live_cache.json` |
| `tests/test_live.py` | Create | stdlib tests: fixtures, protocol strings, parse, merge, cache, build wiring, CLI |
| `tests/fixtures/live_page.html` | Create (commit) | Real GET of LiveScoring.aspx (form fields + grid state) |
| `tests/fixtures/live_showall.txt` | Create (commit) | Real callback response, one expanded detail row (class 48) |
| `tests/test.js` | Modify | Pill / live-filled place / up-next-follows-merged-data checks |
| `AGENTS.md` | Modify | Commands, architecture, gitignore list, protocol tip |
| `refresh/README.md` | Modify | Live stage in the pipeline docs |

Both fixtures already exist (untracked) in `tests/fixtures/` — Task 1 commits them.

### Fixture ground truth (verified 2026-08-24)

`live_showall.txt` is one callback response (`236|<state blob>...{'result':
{'html':..., 'stateObject':...}}`):

- 8 parent classes: `48, 49, 50, 51, 52, 53.1, 53.2, 54` (all `Ring 1`).
- Class 48 row: name `48 - Equitation - Open Class Rider 11 Years Old`,
  progress `11 / 11`, placed `7`, not_placed `4`, updated `2 hours, 2 min`,
  source `Show Secretary`.
- Class 54 row: placed `8`, updated `43 min`.
- Detail row `DXDRow0` (class 48): 7 placed entries, in order:
  `["1158","TWENTY FOUR KARAT MAGIC","WITMER, HAYLEN",6,1]`,
  `["958","MAN IN CHARGE","PHILPOTT, REID",7,2]`,
  `["1607","EAC ZACH ATTACK","ROWE, MADELYN",4,3]`,
  `["1477","VIVE LA FANTASIA","MOLLICA, MADDALENA",5,4]`,
  `["1379","SOMETHING JUSTT LIKE THIS","VERRILL, TAYLOR",1,5]`,
  `["831","AMANYARA","HAWKINS, TAYLOR",9,6]`,
  `["935","SH LYNN'S LICORICE","HUGHES, MADDIE",8,7]`
  (format `[entry, horse, rider, ord, place]`; plus 4 non-placed rows, ignored).
- Envelope `stateObject`: 8 keys (UUIDs), `groupLevelState` `{}`.
- `live_page.html` (GET): 7 form fields in DOM order (`__EVENTTARGET`,
  `__EVENTARGUMENT`, `__VIEWSTATE`, `__VIEWSTATEGENERATOR`,
  `__EVENTVALIDATION`, `...grMain$DXSE`, `ctl00$ctl00$ASPxDateEditMaster`),
  callback id `ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain`,
  8 keys, `__EVENTVALIDATION` > 100 chars.

---

### Task 1: Fixtures + protocol/parse core (`refresh/live_scores.py`)

**Files:**
- Create: `refresh/live_scores.py`
- Test: `tests/test_live.py`
- Create (commit existing untracked files): `tests/fixtures/live_page.html`, `tests/fixtures/live_showall.txt`

**Interfaces:**
- Consumes: the two fixtures.
- Produces (exact signatures, used by later tasks):
  - `unescape_js(s: str) -> str`
  - `clean_cell(x: str) -> str`
  - `top_rows(grid_html: str) -> dict[str, str]` — `{row_id_suffix: row_html}` where the suffix is e.g. `DXDataRow3`, `DXDRow0`, `DXHeadersRow0`, `DXADRow`
  - `parse_parent_row(row: str) -> dict | None` — keys `num, name, ring, ord, shown, total, placed, not_placed, updated, source` (ints where noted; `None` when absent)
  - `parse_detail_entries(detail_row: str) -> list[list]` — rows `[entry, horse, rider, ord, place]` (str, str, str, int, int) from the `grPlaced` sub-grid only
  - `parse_envelope_state(response: str) -> dict | None` — `{"keys": [str], "callbackState": str, "groupLevelState": str}`
  - `response_html(response: str) -> str | None` — unescaped `result.html`; `None` on fault envelopes
  - `parse_get_page(page: str) -> dict | None` — `{"callback_id": str, "fields": [(name, value), ...], "keys": [str], "callbackState": str, "groupLevelState": str}`; `None` when no grid block (dead session)
  - `updated_to_minutes(s: str | None) -> int | None`

- [ ] **Step 1: Commit the fixtures**

Run: `git add tests/fixtures/live_page.html tests/fixtures/live_showall.txt && git commit -m "Add LiveScoring fixtures for live scores tests"`
Expected: commit created; `git status --short` no longer shows `tests/fixtures/`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_live.py`:

```python
#!/usr/bin/env python3
"""Live Scores protocol + parsing (refresh/live_scores.py) against real
fixtures captured from LiveScoring.aspx on 2026-08-24. Also covers the
merge/cache rules, the parse_live.py CLI, and build_page.py wiring."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import live_scores as ls

PAGE = open(os.path.join(HERE, "fixtures", "live_page.html")).read()
RESP = open(os.path.join(HERE, "fixtures", "live_showall.txt")).read()

# --- GET page bootstrap
boot = ls.parse_get_page(PAGE)
check("get: grid found", boot is not None)
check("get: callback id",
      boot["callback_id"] == "ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain")
check("get: 7 form fields in DOM order",
      [f[0] for f in boot["fields"]] == [
          "__EVENTTARGET", "__EVENTARGUMENT", "__VIEWSTATE",
          "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
          "ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain$DXSE",
          "ctl00$ctl00$ASPxDateEditMaster"])
check("get: event validation present",
      len(dict(boot["fields"])["__EVENTVALIDATION"]) > 100)
check("get: 8 row keys", len(boot["keys"]) == 8)
check("get: callback state token", len(boot["callbackState"]) > 100)
check("get: dead session -> None", ls.parse_get_page("<html>login shell</html>") is None)

# --- callback response envelope
check("resp: fault -> None",
      ls.response_html("0|/*DX*/({'generalError':'boom'})") is None)
html = ls.response_html(RESP)
check("resp: html unescaped",
      html is not None and "dxgvDataRow_Office2010Blue" in html)
st = ls.parse_envelope_state(RESP)
check("env: 8 keys", st is not None and len(st["keys"]) == 8)
check("env: callback state", len(st["callbackState"]) > 100)
check("env: group level state", st["groupLevelState"] == "{}")

# --- top-level rows
rows = ls.top_rows(html)
check("rows: headers + adaptive + 8 data + 1 detail",
      sorted(rows.keys()) == sorted(
          ["DXHeadersRow0", "DXADRow"] + ["DXDataRow%d" % i for i in range(8)] + ["DXDRow0"]))

# --- parent rows (class 48 is the expanded row in this capture)
p48 = ls.parse_parent_row(rows["DXDataRow0"])
check("parent: class 48 identity",
      p48["num"] == "48"
      and p48["name"] == "48 - Equitation - Open Class Rider 11 Years Old"
      and p48["ring"] == "Ring 1" and p48["ord"] == 1)
check("parent: progress + counts",
      p48["shown"] == 11 and p48["total"] == 11
      and p48["placed"] == 7 and p48["not_placed"] == 4)
check("parent: updated + source",
      p48["updated"] == "2 hours, 2 min" and p48["source"] == "Show Secretary")
p54 = ls.parse_parent_row(rows["DXDataRow7"])
check("parent: last row (54)",
      p54["num"] == "54" and p54["placed"] == 8 and p54["updated"] == "43 min")
p531 = ls.parse_parent_row(rows["DXDataRow5"])
check("parent: subclass number kept", p531["num"] == "53.1")

# --- detail (class 48's placed entries)
ents = ls.parse_detail_entries(rows["DXDRow0"])
check("detail: 7 placed entries", len(ents) == 7)
check("detail: first entry",
      ents[0] == ["1158", "TWENTY FOUR KARAT MAGIC", "WITMER, HAYLEN", 6, 1])
check("detail: apostrophe horse name",
      ents[6][1] == "SH LYNN'S LICORICE" and ents[6][0] == "935")
check("detail: places are 1..7", sorted(e[4] for e in ents) == [1, 2, 3, 4, 5, 6, 7])

# --- updated-string -> minutes
for s, want in [("53 min", 53), ("1 hour, 51 min", 111), ("2 hours, 2 min", 122),
                ("43 min", 43), ("Just now", 0), ("1 hour", 60)]:
    check("minutes: %r" % s, ls.updated_to_minutes(s) == want, str(ls.updated_to_minutes(s)))
check("minutes: empty -> None",
      ls.updated_to_minutes(None) is None and ls.updated_to_minutes("") is None)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 tests/test_live.py`
Expected: FAIL (ModuleNotFoundError: No module named 'live_scores').

- [ ] **Step 4: Implement `refresh/live_scores.py`**

Create `refresh/live_scores.py`:

```python
#!/usr/bin/env python3
"""Pure protocol + parse helpers for the show's Live Scores grid
(DevExpress ASPxGridView WebForms callbacks). No network I/O and no file
I/O here: fetch_live.py drives the requests, build_page.py does the merge.
Protocol details: docs/superpowers/specs/2026-08-24--live-scores-design.md
(section "Callback protocol")."""
import html as H
import re

GRID_TR = re.compile(r'<tr id="[^"]*_grMain_DX[A-Za-z]')

def unescape_js(s):
    """Unescape a JS string-literal body (the response's result.html)."""
    return (s.replace("\\'", "'").replace("\\\\", "\\")
             .replace("\\n", "\n").replace("\\r", "\r").replace("\\/", "/"))

def clean_cell(x):
    """Strip tags, unescape entities, squash whitespace."""
    x = re.sub(r'<[^>]+>', '', x)
    return H.unescape(x).replace('\r', ' ').replace('\n', ' ').strip()

def top_rows(grid_html):
    """Split a grid's HTML into its top-level rows.

    Every top-level row (headers, DXADRow, DXDataRowN, DXDRowN) carries an
    id ending in _grMain_DX*; nested rows (progress bars, the detail
    sub-grids) have no ids and stay inside their parent row. Returns
    {row_id_suffix: row_html}.
    """
    marks = [m.start() for m in GRID_TR.finditer(grid_html)]
    rows = {}
    for a, b in zip(marks, marks[1:] + [len(grid_html)]):
        m = re.search(r'<tr id="([^"]+)"', grid_html[a:b])
        rows[m.group(1).rsplit('_grMain_', 1)[1]] = grid_html[a:b]
    return rows

def parse_parent_row(row):
    """Parse a class-summary row (DXDataRowN). Returns a dict with
    num, name, ring, ord, shown, total, placed, not_placed, updated,
    source (None when a cell is absent), or None when the row has no
    class name at all."""
    name_m = re.search(r'dxeBase[^>]*>\s*([^<]+?)\s*<', row)
    if not name_m:
        return None
    name = H.unescape(name_m.group(1)).strip()
    tci = row.find('tccell')   # the name+progress cell; its tag starts with an id, so the plain-cell regex below skips it
    tail = [clean_cell(t) for t in re.findall(r'<td class="dxgv"[^>]*>([^<]*)</td>', row[tci:])]

    def toi(x):
        x = (x or '').strip()
        return int(x) if x.isdigit() else None

    prog = re.search(r'(\d+)\s*/\s*(\d+)', row)
    cells = re.findall(r'<td class="dxgv"[^>]*>([^<]*)</td>', row)
    return {
        "num": name.split(' - ')[0].strip(),
        "name": name,
        "ring": clean_cell(cells[0]) if cells else None,
        "ord": toi(cells[1]) if len(cells) > 1 else None,
        "shown": int(prog.group(1)) if prog else None,
        "total": int(prog.group(2)) if prog else None,
        "placed": toi(tail[0]) if len(tail) > 0 else None,
        "not_placed": toi(tail[1]) if len(tail) > 1 else None,
        "updated": tail[2] if len(tail) > 2 else None,
        "source": tail[3] if len(tail) > 3 else None,
    }

def parse_detail_entries(detail_row):
    """Parse the placed-entries sub-grid (grPlaced_*) of a detail row into
    [entry, horse, rider, ord, place] rows. The grNonPlaced sub-grid is
    ignored (no placings)."""
    entries = []
    pm = [m.start() for m in re.finditer(r'<tr id="[^"]*grPlaced_\d+_(DXDataRow\d+)"', detail_row)]
    for a, b in zip(pm, pm[1:] + [len(detail_row)]):
        row = detail_row[a:b]

        def sp(nm):
            m = re.search(r'id="[^"]*' + nm + r'_\d+"[^>]*>([^<]+)<', row)
            return H.unescape(m.group(1)).strip() if m else None

        rider = re.search(r'<td class="dxgv" style="font-weight:bold;">([^<]+)</td>', row)
        nums = re.findall(r'<td class="dxgv" align="right" style="font-weight:bold;">([^<]+)</td>', row)
        entries.append([
            sp("lbEntryNo"),
            sp("lbEntryName"),
            H.unescape(rider.group(1)).strip() if rider else None,
            int(nums[0]) if len(nums) > 0 else None,
            int(nums[1]) if len(nums) > 1 else None,
        ])
    return entries

def parse_envelope_state(response):
    """keys/callbackState/groupLevelState from a callback response's
    envelope stateObject — the source of truth for the next request. The
    response HTML must not be used: it re-initializes the main grid via
    PostponeInitialize (no createControl) and also embeds the detail
    sub-grids' own state objects."""
    m = re.search(r"'stateObject':", response)
    if not m:
        return None
    k = response.find('{', m.end())
    depth = 0
    for i in range(k, len(response)):
        c = response[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
    lit = response[k:i + 1]
    keys = re.findall(r"'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'", lit)
    cb_m = re.search(r"'callbackState':'([^']+)'", lit)
    gl_m = re.search(r"'groupLevelState':(\{[^}]*\})", lit)
    if not cb_m:
        return None
    return {"keys": keys, "callbackState": cb_m.group(1),
            "groupLevelState": gl_m.group(1) if gl_m else "{}"}

def response_html(response):
    """Unescaped result.html of a callback response; None when the
    envelope is a fault (generalError / error.message) or malformed."""
    if re.search(r"'generalError':", response) or re.search(r"'message':", response):
        return None
    m = re.search(r"'html':'((?:[^'\\]|\\.)*)'", response)
    return unescape_js(m.group(1)) if m else None

def parse_get_page(page):
    """Bootstrap state from a GET of LiveScoring.aspx: the grid's callback
    id, all form fields (DOM order), and the grid's stateObject. Returns
    None when the page has no grid block (dead session / login shell)."""
    m = re.search(r"ASPx\.createControl\(ASPxClientGridView,'([^']+)'", page)
    if not m:
        return None
    js_name = m.group(1)
    i2 = page.find("ASPx.createControl(ASPxClientGridView,'" + js_name + "'")
    cb_m = re.search(r"WebForm_DoCallback\('([^']+)'", page[i2:i2 + 800])
    if not cb_m:
        return None
    j2 = page.find('stateObject', i2)
    seg = page[j2:j2 + 400000]
    keys_m = re.search(r"'keys':\[(.*?)\]", seg)
    cb2 = re.search(r"'callbackState':'([^']+)'", seg)
    if not keys_m or not cb2:
        return None
    gl_m = re.search(r"'groupLevelState':(\{[^}]*\})", seg)
    fields = []
    fi = page.find('<form')
    fj = page.find('</form>', fi)
    for fm in re.finditer(r'<(?:input|select|textarea)[^>]*?(?:/>|>)', page[fi:fj], re.S):
        tag = fm.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        if not n:
            continue
        typ_m = re.search(r'type="([^"]+)"', tag)
        typ = typ_m.group(1) if typ_m else ''
        if typ in ('checkbox', 'radio') and 'checked' not in tag:
            continue
        if typ in ('submit', 'button', 'image', 'reset', 'file'):
            continue
        v = re.search(r'value="([^"]+)"', tag)
        fields.append((n.group(1), H.unescape(v.group(1)) if v else ''))
    return {
        "callback_id": cb_m.group(1),
        "fields": fields,
        "keys": re.findall(r"'([^']+)'", keys_m.group(1)),
        "callbackState": cb2.group(1),
        "groupLevelState": gl_m.group(1) if gl_m else "{}",
    }

def updated_to_minutes(s):
    """'53 min' -> 53; '1 hour, 51 min' -> 111; '2 hours, 2 min' -> 122;
    'Just now' -> 0; None/''/unparseable -> None."""
    if not s:
        return None
    s = s.lower()
    if 'just now' in s:
        return 0
    h = re.search(r'(\d+)\s*hours?', s)
    m = re.search(r'(\d+)\s*min', s)
    if not h and not m:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 tests/test_live.py`
Expected: all PASS (24 checks), `ALL PASS`.

- [ ] **Step 6: Commit**

```bash
git add refresh/live_scores.py tests/test_live.py
git commit -m "Add live scores protocol/parse module with fixture tests"
```

---

### Task 2: Protocol string builders + merge/cache + `parse_live.py` CLI

**Files:**
- Modify: `refresh/live_scores.py` (append 4 functions)
- Create: `refresh/parse_live.py`
- Test: `tests/test_live.py` (append sections)

**Interfaces:**
- Consumes: Task 1 functions.
- Produces:
  - `ls.grid_state_field(callback_id: str, state: dict) -> tuple[str, str]` — the grid's hidden state input (name, HTML-escaped compact JSON value)
  - `ls.build_param(state: dict, key: str) -> str` — the `__CALLBACKPARAM` for a `SHOWDETAILROW` on `key`
  - `ls.merge_live_places(classes: list[dict], cache: dict) -> list[dict]` — in place; `classes` = payload-shape dicts with `n` and `e` (`e[0]` entry string, `e[6]` place or None); `cache` = `{num: {entry: {"p": int, "at": str}}}`
  - `ls.fold_live_cache(cache: dict, live: dict) -> dict` — in place; `live` = live.json shape
  - `refresh/parse_live.py [live.json [cache.json]]` — CLI, exit 0 on success, non-zero (with message) when live.json is missing/unreadable; never touches the cache on failure.

- [ ] **Step 1: Write the failing tests (append to `tests/test_live.py`, before the final `print`)**

```python
# --- protocol strings (what fetch_live.py sends)
state = {"keys": ["aaaa", "bbbb"], "callbackState": "xyz", "groupLevelState": "{}"}
p = ls.build_param(state, "bbbb")
check("param: c0 KV FR CT GB shape",
      p == "c0:KV|16;[\"aaaa\",\"bbbb\"];FR|1;0;CT|2;{};GB|23|SHOWDETAILROW4|bbbb;", p)
name, val = ls.grid_state_field("GRID", state)
check("state field: name is the grid uniqueID", name == "GRID")
check("state field: html-escaped compact json",
      val == ("&quot;keys&quot;:[&quot;aaaa&quot;,&quot;bbbb&quot;],"
              "&quot;groupLevelState&quot;:{},&quot;callbackState&quot;:&quot;xyz&quot;,"
              "&quot;focusedRow&quot;:0,&quot;selection&quot;:&quot;&quot;,"
              "&quot;toolbar&quot;:&quot;{}&quot;"), val)

# --- merge rule: official wins, live fills gaps
def mcls(n, entries):    # entries: [(entry, place_or_None)]
    return {"n": n, "name": "t", "e": [[e, "h", "r", "t", "o", None, p] for e, p in entries]}
def mcache(num, places): # places: {entry: place}
    return {num: {str(k): {"p": v, "at": "2026-08-24 09:20"} for k, v in places.items()}}

d = [mcls("48", [("1158", None), ("958", "1")]), mcls("49", [("1", None)])]
ls.merge_live_places(d, mcache("48", {"1158": 1, "958": 5}))
check("merge: live fills the gap", d[0]["e"][0][6] == "1")
check("merge: official place wins over live", d[0]["e"][1][6] == "1")
check("merge: class not in cache untouched", d[1]["e"][0][6] is None)
d2 = [mcls("48", [("1158", "2")])]
ls.merge_live_places(d2, mcache("48", {"1158": 7}))
check("merge: never overwrites an official place", d2[0]["e"][0][6] == "2")
d3 = [mcls("48", [("1158", None)])]
ls.merge_live_places(d3, {})
check("merge: empty cache is a no-op", d3[0]["e"][0][6] is None)

# --- cache: accumulate across runs, idempotent
c = {}
live1 = {"fetched": "2026-08-24 09:20",
         "classes": [{"num": "48", "entries": [["1158", "H", "R", 1]]}]}
live2 = {"fetched": "2026-08-24 09:28",
         "classes": [{"num": "48", "entries": [["958", "H", "R", 2]]},
                     {"num": "49", "entries": [["1", "H", "R", 3]]}]}
ls.fold_live_cache(c, live1)
ls.fold_live_cache(c, live2)
check("cache: accumulates across runs",
      c["48"]["1158"]["p"] == 1 and c["48"]["958"]["p"] == 2 and c["49"]["1"]["p"] == 3)
check("cache: run timestamp stamped", c["48"]["958"]["at"] == "2026-08-24 09:28")
snapshot = json.loads(json.dumps(c))
ls.fold_live_cache(c, live2)
check("cache: idempotent on re-run", c == snapshot)

# --- parse_live.py CLI (temp files; the repo's live files are never touched)
import tempfile
tmp = tempfile.mkdtemp(prefix="livetest_")
lp, cp = os.path.join(tmp, "live.json"), os.path.join(tmp, "cache.json")
json.dump(live2, open(lp, "w"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"), lp, cp],
                   capture_output=True, text=True)
check("cli: exits 0", r.returncode == 0, r.stderr.strip())
c1 = json.load(open(cp))
check("cli: wrote the folded cache", c1["48"]["958"]["p"] == 2 and c1["49"]["1"]["p"] == 3)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"), lp, cp],
                   capture_output=True, text=True)
check("cli: re-run is idempotent", json.load(open(cp)) == c1)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"),
                    os.path.join(tmp, "nope.json"), cp], capture_output=True, text=True)
check("cli: missing live.json -> non-zero, cache untouched",
      r.returncode != 0 and json.load(open(cp)) == c1, r.stderr.strip())
```

Also add to the top-of-file imports (merge with existing): nothing new needed beyond `tempfile` (imported inline above).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/test_live.py`
Expected: new checks FAIL with `AttributeError: module 'live_scores' has no attribute 'build_param'` (and the CLI checks fail: file not found).

- [ ] **Step 3: Implement**

Append to `refresh/live_scores.py`:

```python
def grid_state_field(callback_id, state):
    """(name, value) for the grid's hidden state input. The grid renders
    this hidden input (named with its uniqueID) at JS runtime; the server
    needs it on every callback. Value is HTML-escaped compact JSON."""
    import html as H
    import json
    gs = H.escape(json.dumps({"keys": state["keys"],
                              "groupLevelState": json.loads(state["groupLevelState"]),
                              "callbackState": state["callbackState"],
                              "focusedRow": 0, "selection": "", "toolbar": "{}"},
                             separators=(',', ':')), quote=True)
    return (callback_id, gs)

def build_param(state, key):
    """__CALLBACKPARAM for a SHOWDETAILROW callback on row key `key`.
    The c0: prefix and the FR/CT segments are required by the server."""
    import json
    kv = json.dumps(state["keys"], separators=(',', ':'))
    ser = "13|SHOWDETAILROW%d|%s" % (len(key), key)
    return ("c0:" + "KV|%d;%s;" % (len(kv), kv)
            + "FR|1;0;" + "CT|2;{};" + "GB|%d;%s;" % (len(ser), ser))

def merge_live_places(classes, cache):
    """In place: fill e[6] from the live cache where the official place is
    missing. Official places are never overwritten; class numbers absent
    from the cache (including live sub-classes the page doesn't know) are
    untouched."""
    for c in classes:
        cc = cache.get(c["n"])
        if not cc:
            continue
        for e in c["e"]:
            if e[6] is None and e[0] in cc:
                e[6] = str(cc[e[0]]["p"])
    return classes

def fold_live_cache(cache, live):
    """In place: fold a live.json payload into the accumulating cache.
    Grows only — no deletes during the show; re-folding is idempotent."""
    fetched = live.get("fetched", "")
    for c in live.get("classes", []):
        cls = cache.setdefault(c["num"], {})
        for entry, _horse, _rider, place in c.get("entries", []):
            cls[str(entry)] = {"p": place, "at": fetched}
    return cache
```

Move the `import html as H` / `import json` to the top of the file (the file header already imports `re`; add `import json` next to it — then remove the local imports from `grid_state_field`). Final top-of-file imports:

```python
import html as H
import json
import re
```

Create `refresh/parse_live.py`:

```python
#!/usr/bin/env python3
"""Fold refresh/live.json into refresh/live_cache.json (git-ignored).

The cache grows only during the show so a class doesn't "un-place" when it
ages out of the live window before its official results page re-fetches.
The merge into the page happens in build_page.py.

Usage: parse_live.py [live.json [cache.json]]
  (defaults: refresh/live.json and refresh/live_cache.json)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_scores as ls


def main():
    live_p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "live.json")
    cache_p = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "live_cache.json")
    try:
        live = json.load(open(live_p))
    except (OSError, ValueError) as e:
        sys.exit("parse_live.py: cannot read %s: %s" % (live_p, e))
    try:
        cache = json.load(open(cache_p))
    except (OSError, ValueError):
        cache = {}
    ls.fold_live_cache(cache, live)
    with open(cache_p, "w") as f:
        json.dump(cache, f, separators=(',', ':'))
    print("live_cache.json: %d classes, %d placings"
          % (len(cache), sum(len(v) for v in cache.values())))


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/test_live.py`
Expected: all PASS (39 checks), `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add refresh/live_scores.py refresh/parse_live.py tests/test_live.py
git commit -m "Add live scores merge/cache rules and parse_live CLI"
```

---

### Task 3: `refresh/fetch_live.py` network driver

**Files:**
- Create: `refresh/fetch_live.py`

**Interfaces:**
- Consumes: `ls.parse_get_page`, `ls.grid_state_field`, `ls.build_param`,
  `ls.response_html`, `ls.parse_envelope_state`, `ls.top_rows`,
  `ls.parse_parent_row`, `ls.parse_detail_entries`, `ls.updated_to_minutes`;
  `refresh/jar.txt` (Netscape cookie jar, shared with `fetch_entries.sh`).
- Produces: `refresh/live.json` —
  `{"fetched": "YYYY-MM-DD HH:MM", "classes": [{"num", "name", "ring", "ord",
  "shown", "total", "placed", "not_placed", "updated", "updated_min",
  "source", "entries": [[entry, horse, rider, place], ...]}, ...]}`.
  Exit 0 on success; non-zero with a message on any failure, and on failure
  `live.json` is left untouched (fail-safe: the page degrades to
  official-only with the cache retained).

- [ ] **Step 1: Implement `refresh/fetch_live.py`**

```python
#!/usr/bin/env python3
"""Fetch the show's Live Scores grid (summary + per-class placed entries)
via the DevExpress ASPxGridView callback protocol.

The detail view is an accordion: the server keeps at most one detail row
expanded per response, so the fetcher sends one SHOWDETAILROW callback per
row key and parses that row's placed entries from the response. Each
response also re-renders every parent row (ring/ord/progress/placed/
updated/source), so parent info is collected from all responses. New
classes can join the window mid-run (the show is live), so the key set is
re-checked from each response's envelope and the loop repeats until stable.

Writes refresh/live.json. On any failure exits non-zero and leaves
live.json (and live_cache.json) untouched, so the page degrades to
official-only data. Uses refresh/jar.txt (same session as fetch_entries.sh).

Protocol details: docs/superpowers/specs/2026-08-24--live-scores-design.md
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_scores as ls

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SHOW_GUID = "46c298a5-6bac-44e0-a711-56695c992e12"
SHOW_URL = "https://horseshowsonline.com/ShowDetails?ShowGUID=" + SHOW_GUID
LIVE_URL = "https://horseshowsonline.com/LiveScoring.aspx?ShowGUID=" + SHOW_GUID
JAR = os.path.join(HERE, "jar.txt")
LIVE_JSON = os.path.join(HERE, "live.json")
PACING = 0.7      # seconds between callbacks
MAX_ROUNDS = 5    # bound on key-set re-check rounds


def enc(x):
    return urllib.parse.quote(str(x), safe='')


def num_key(n):
    return tuple(int(p) for p in n.split('.'))


def main():
    if not os.path.exists(JAR):
        sys.exit("fetch_live.py: no %s (run fetch_entries.sh first)" % JAR)
    cj = http.cookiejar.MozillaCookieJar(JAR)
    cj.load(ignore_discard=True, ignore_expires=True)
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA)]

    def http_get(url):
        return op.open(url, timeout=90).read().decode('utf-8', 'replace')

    def http_post(url, body):
        req = urllib.request.Request(
            url, data=body,
            headers={'User-Agent': UA,
                     'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'})
        return op.open(req, timeout=120).read().decode('utf-8', 'replace')

    http_get(SHOW_URL)  # session warm-up (mirrors fetch_entries.sh)
    boot = ls.parse_get_page(http_get(LIVE_URL))
    if not boot:
        sys.exit("fetch_live.py: no grid in LiveScoring.aspx (dead session?)")
    fields = boot["fields"]
    ev = dict(fields).get("__EVENTVALIDATION", "")
    state = {"keys": boot["keys"], "callbackState": boot["callbackState"],
             "groupLevelState": boot["groupLevelState"]}

    classes = {}
    expanded = set()
    for _round in range(MAX_ROUNDS):
        pending = [k for k in state["keys"] if k not in expanded]
        if not pending:
            break
        for key in pending:
            name, val = ls.grid_state_field(boot["callback_id"], state)
            body = ("&".join("%s=%s" % (enc(k), enc(v))
                             for k, v in [(name, val)] + fields if k != "__EVENTVALIDATION")
                    + "&__CALLBACKID=" + enc(boot["callback_id"])
                    + "&__CALLBACKPARAM=" + enc(ls.build_param(state, key))
                    + "&__EVENTVALIDATION=" + enc(ev)).encode()
            resp = http_post(LIVE_URL, body)
            html = ls.response_html(resp)
            if html is None:
                m = (re.search(r"'generalError':'([^']*)'", resp)
                     or re.search(r"'message':'([^']*)'", resp))
                sys.exit("fetch_live.py: callback failed: %s"
                         % (m.group(1) if m else "unknown envelope"))
            ns = ls.parse_envelope_state(resp)
            if ns:
                state = ns
            rows = ls.top_rows(html)
            for rk, row in rows.items():
                if re.match(r'DXDataRow\d+$', rk):
                    info = ls.parse_parent_row(row)
                    if info:
                        prev = classes.get(info["num"])
                        # a later response re-renders this row without its
                        # detail; keep entries already collected for it
                        if prev and prev.get("entries") and not info.get("entries"):
                            info["entries"] = prev["entries"]
                        classes[info["num"]] = info
            detail = next((row for rk, row in rows.items()
                           if rk.startswith('DXDRow')), None)
            if detail:
                try:
                    kidx = state["keys"].index(key)
                    prow = rows.get("DXDataRow%d" % kidx)
                    info = ls.parse_parent_row(prow) if prow else None
                    if info:
                        info["entries"] = ls.parse_detail_entries(detail)
                        classes[info["num"]] = info
                except ValueError:
                    pass  # row left the window mid-flight; parent already captured
            expanded.add(key)
            time.sleep(PACING)
        if set(state["keys"]) <= expanded:
            break

    out_classes = []
    for num in sorted(classes, key=num_key):
        c = classes[num]
        out_classes.append({
            "num": c["num"], "name": c["name"], "ring": c["ring"], "ord": c["ord"],
            "shown": c["shown"], "total": c["total"],
            "placed": c["placed"], "not_placed": c["not_placed"],
            "updated": c["updated"],
            "updated_min": ls.updated_to_minutes(c["updated"]),
            "source": c["source"],
            "entries": c.get("entries", []),
        })
    if not out_classes:
        sys.exit("fetch_live.py: no classes parsed (page layout change?)")
    with open(LIVE_JSON, 'w') as f:
        json.dump({"fetched": datetime.now().strftime('%Y-%m-%d %H:%M'),
                   "classes": out_classes}, f, separators=(',', ':'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print("live.json: %d classes, %d placings"
          % (len(out_classes), sum(len(c["entries"]) for c in out_classes)))


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify the protocol strings are unit-covered and the script is syntactically valid**

Run: `python3 -m py_compile refresh/fetch_live.py && python3 tests/test_live.py`
Expected: no syntax error; all existing checks still PASS.

- [ ] **Step 3: Live verification against the show (requires the local `refresh/jar.txt`)**

Run: `python3 refresh/fetch_live.py`
Expected: exit 0, prints `live.json: N classes, M placings` (N ≈ 8–15). Then:

```bash
python3 - <<'EOF'
import json
d = json.load(open('refresh/live.json'))
assert d["fetched"] and isinstance(d["classes"], list) and d["classes"]
c = d["classes"][0]
for k in ("num", "name", "ring", "shown", "total", "placed", "not_placed",
          "updated", "updated_min", "source", "entries"):
    assert k in c, k
for e in c["entries"]:
    assert len(e) == 4 and e[0] and e[3]  # [entry, horse, rider, place]
print("live.json OK:", [x["num"] for x in d["classes"]])
EOF
```

Expected: `live.json OK: [...]` with plausible class numbers (the show's current window).
If the session cookie is dead (fetch fails with "no grid ... dead session?"),
run `bash refresh/fetch_entries.sh` first to refresh `jar.txt`, then retry.

- [ ] **Step 4: Commit**

```bash
git add refresh/fetch_live.py
git commit -m "Add fetch_live.py: live scores grid fetcher (callback protocol)"
```

---

### Task 4: `build_page.py` — merge, `live` payload field, `.clive` pill

**Files:**
- Modify: `refresh/build_page.py` (3 edits: merge block after `classes` is built; `.clive` CSS after the `.cnow` rule; pill render in `makeClass`)
- Test: `tests/test_live.py` (append a build-wiring section)

**Interfaces:**
- Consumes: `refresh/live_cache.json` (optional), `refresh/live.json` (optional), the Task 1–2 functions (merge inlined here per the spec's "merge happens in build_page.py" — the *logic* lives in `ls.merge_live_places`... see Step 3 note).
- Produces: payload classes gain `e[6]` filled from the cache where null, and
  `"live": <minutes-ago>` (int) on classes present in the current `live.json`
  with `updated_min < 60`. The template renders a `.clive` pill
  (`clivedot` span + text "live") in the card head for such classes.
  Missing live files ⇒ byte-identical output to today.

- [ ] **Step 1: Write the failing test (append to `tests/test_live.py`, before the final `print`)**

```python
# --- build_page.py wiring (temp repo copy: merge + live flag)
import shutil
tmp = tempfile.mkdtemp(prefix="livebuild_")
os.makedirs(os.path.join(tmp, "refresh"))
shutil.copyfile(os.path.join(ROOT, "refresh", "build_page.py"),
                os.path.join(tmp, "refresh", "build_page.py"))
mini = [{"num": "48", "name": "Equitation", "type": None, "division": "EQ",
         "weekday": "Saturday", "period": "Morning", "date": "August 22",
         "time": "10:00 a.m.",
         "entries": [
             {"entry": "1158", "horse": "H1", "rider": "R1", "trainer": "T1",
              "owner": "O1", "start": "6", "place": None},
             {"entry": "958", "horse": "H2", "rider": "R2", "trainer": "T2",
              "owner": "O2", "start": "7", "place": "1"}]}]
json.dump(mini, open(os.path.join(tmp, "refresh", "data.json"), "w"))
json.dump(mcache("48", {"1158": 1}), open(os.path.join(tmp, "refresh", "live_cache.json"), "w"))
json.dump({"fetched": "2026-08-24 09:20",
           "classes": [{"num": "48", "updated": "43 min", "updated_min": 43}]},
          open(os.path.join(tmp, "refresh", "live.json"), "w"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
check("build: exits 0", r.returncode == 0, r.stderr.strip())
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
c48 = b["classes"][0]
check("build: live gap filled from cache",
      c48["e"][0][6] == "1" and c48["e"][1][6] == "1")
check("build: live flag from fresh live.json", c48.get("live") == 43)

json.dump({"fetched": "2026-08-24 09:20",
           "classes": [{"num": "48", "updated": "2 hours, 2 min", "updated_min": 122}]},
          open(os.path.join(tmp, "refresh", "live.json"), "w"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
check("build: stale live class -> no flag", b["classes"][0].get("live") is None)

# missing live files -> exactly today's behavior (no live key at all)
os.remove(os.path.join(tmp, "refresh", "live_cache.json"))
os.remove(os.path.join(tmp, "refresh", "live.json"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
check("build: no live files -> no merge, no flag",
      r.returncode == 0 and b["classes"][0]["e"][0][6] is None
      and "live" not in b["classes"][0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/test_live.py`
Expected: the `build:` checks FAIL (e[0][6] stays None, no `live` key).

- [ ] **Step 3: Implement the merge + live flag**

In `refresh/build_page.py`, inside the `else:` branch, insert after the
`classes = [...]` loop (i.e. after the line `        })` that closes the
append, before the comment `    # The "Updated" timestamp only changes...`):

```python
    # Live scores (git-ignored intermediates): official placings win, live
    # fills gaps; classes with fresh live activity (< 60 min) get "live".
    # Missing files -> exactly today's behavior.
    # See docs/superpowers/specs/2026-08-24--live-scores-design.md
    sys.path.insert(0, HERE)
    import live_scores as ls
    cache = {}
    try:
        cache = json.load(open(os.path.join(HERE, 'live_cache.json')))
    except (OSError, ValueError):
        pass
    live_fresh = {}
    try:
        for c in json.load(open(os.path.join(HERE, 'live.json'))).get("classes", []):
            u = c.get("updated_min")
            if u is not None and u < 60:
                live_fresh[c["num"]] = u
    except (OSError, ValueError):
        pass
    if cache or live_fresh:
        ls.merge_live_places(classes, cache)
        for c in classes:
            if c["n"] in live_fresh:
                c["live"] = live_fresh[c["n"]]
```

- [ ] **Step 4: Run tests to verify the build wiring passes**

Run: `python3 tests/test_live.py`
Expected: all build checks PASS.

- [ ] **Step 5: Add the `.clive` pill to the template**

In `refresh/build_page.py`'s template, after the `.cnow` rule (the line
`.cnow { background: #f59e0b; ... }`), add:

```css
.clive { display: inline-flex; align-items: center; gap: 4px; background: var(--now-bg); color: var(--gold); border: 1px solid var(--now-line); border-radius: 6px; font-size: 11px; font-weight: 600; padding: 1px 6px; flex: none; }
.clivedot { width: 6px; height: 6px; border-radius: 50%; background: var(--gold); animation: clivepulse 2s ease-in-out infinite; }
@keyframes clivepulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .clivedot { animation: none; } }
```

In `makeClass`, after the line
`  if (isFrontier) head.appendChild(el("span","cnow","up next"));`, add:

```js
  if (c.live != null){
    const lv = el("span","clive");
    lv.appendChild(el("span","clivedot"));
    lv.appendChild(document.createTextNode("live"));
    head.appendChild(lv);
  }
```

- [ ] **Step 6: Rebuild the real page and run the existing suites**

```bash
python3 refresh/build_page.py
npm --prefix tests test
python3 tests/test_ui_only.py
python3 tests/test_asof.py
python3 tests/test_payload.py
python3 tests/test_frontier.py
python3 tests/test_live.py
```

Expected: all green. (The committed payload has no `live` field unless
`refresh/live.json` happens to exist locally with fresh classes — either way
the suites pass because the build is deterministic given the local files.)

- [ ] **Step 7: Commit**

```bash
git add refresh/build_page.py tests/test_live.py
git commit -m "Merge live placings in build_page.py and add live pill to the template"
```

---

### Task 5: `tests/test.js` — pill, live-filled place, up-next follows merged data

**Files:**
- Modify: `tests/test.js` (one new "check 9" block inside the section-10
  async function, after the `if (P2_FRONTIER_NUM){ ... }` block and before
  the final `console.log`/`process.exit`)

**Interfaces:**
- Consumes: the `__live` payload stub infrastructure already in section 10
  (`w4.__live.current`, `w4.fetch`, `sleep`, `d4`, `orderedClassesOf`,
  `isDone`).
- Produces: three new checks (pill set, live-filled place on its entry
  row, up-next follows merged data).

- [ ] **Step 1: Rebuild the page (so the template under test has the pill)**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: the suite still passes (no `live` classes in the committed
payload, so no pills — the new checks are added next).

- [ ] **Step 2: Add the checks**

In `tests/test.js`, inside the `(async () => { ... })()` block, insert
after the closing `}` of the `if (P2_FRONTIER_NUM){ ... }` block (the
"check 8: day collapse state survives" section) and before the final
`console.log("\n" + ...)` line:

```js
          // check 9: live pill + live-filled place + up-next follows merged data
          // (scope mode so every class card is rendered regardless of filters)
          d4.getElementById("scopeBtn").click();
          const p4 = JSON.parse(JSON.stringify(w4.__live.current));
          const f4 = orderedClassesOf(p4.classes).find(c => !isDone(c));
          if (f4){
            if (f4.e.length) f4.e[0][6] = "1";   // live places the frontier class's first entry
            f4.live = 12;                        // fresh live activity (minutes ago)
            p4.asof = "2026-08-25 11:15";
            w4.__live.current = p4;
            await sleep(200);
            const P4_LIVE_NUMS = p4.classes.filter(c => c.live != null).map(c => c.n).sort();
            const pills = [...d4.querySelectorAll("main .cls .clive")]
              .map(n => n.closest(".cls").querySelector(".cnum").textContent).sort();
            check("live: pill rendered exactly for live classes",
                  JSON.stringify(pills) === JSON.stringify(P4_LIVE_NUMS),
                  pills.join() + " vs " + P4_LIVE_NUMS.join());
            const card4 = [...d4.querySelectorAll("main .cls")]
              .find(x => x.querySelector(".cnum").textContent === f4.n);
            if (card4 && f4.e.length){
              card4.querySelector(".cls-head").click();
              const en4 = String(f4.e[0][0]);
              const row4 = [...card4.querySelectorAll(".erow")]
                .find(r => r.querySelector(".eentry")
                           && r.querySelector(".eentry").textContent.trim() === en4);
              check("live: live-filled place renders on its entry row",
                    !!row4 && !!row4.querySelector(".place")
                    && row4.querySelector(".place").textContent.includes("1st"),
                    row4 ? row4.textContent.trim() : "row missing");
            }
            const P4_FRONT = orderedClassesOf(p4.classes).find(c => !isDone(c));
            const nowCard4 = d4.querySelector("main .cls.now");
            check("live: up-next follows merged data",
                  P4_FRONT
                    ? (!!nowCard4 && nowCard4.querySelector(".cnum").textContent === P4_FRONT.n)
                    : !nowCard4,
                  (nowCard4 && nowCard4.querySelector(".cnum").textContent) + " vs " + (P4_FRONT && P4_FRONT.n));
          }
```

- [ ] **Step 3: Run the suite**

Run: `npm --prefix tests test`
Expected: ALL TESTS PASSED, including the 3 new checks (2/3 when the
frontier class has no entries — the place check is then skipped by design,
matching the existing suite's pattern for entry-less classes).

- [ ] **Step 4: Commit**

```bash
git add tests/test.js
git commit -m "Test the live pill, live-filled places and merged up-next in the page suite"
```

---

### Task 6: Cron wiring, gitignore, docs, full verification

**Files:**
- Modify: `refresh/refresh_cron.sh`, `.gitignore`, `AGENTS.md`, `refresh/README.md`

**Interfaces:**
- Consumes: `python3 fetch_live.py` / `python3 parse_live.py` (Tasks 2–3).
- Produces: cron runs the live phase non-fatally every cycle; the two
  intermediate files are git-ignored; docs reflect the new stage.

- [ ] **Step 1: Add the live phase to `refresh/refresh_cron.sh`**

After the closing `fi` of the fetch phase (the line after the lookahead
`if [ -s "$LIST" ]; then ... fi` block, i.e. just before the
`# --- safety: refuse to publish a catastrophic data loss` comment), insert:

```bash
# --- live scores (additive source; a failure never blocks the pipeline) ---
python3 fetch_live.py && python3 parse_live.py \
  || log "WARNING: live scores fetch failed (cache retained)"
```

- [ ] **Step 2: Syntax-check the cron script**

Run: `bash -n refresh/refresh_cron.sh`
Expected: no output (valid syntax).

- [ ] **Step 3: Update `.gitignore`**

Append:

```
refresh/live.json
refresh/live_cache.json
```

- [ ] **Step 4: Verify the ignore rules**

Run: `touch refresh/live.json refresh/live_cache.json && git status --porcelain -- refresh/ && rm refresh/live.json refresh/live_cache.json`
Expected: empty output (neither file shows as untracked). (If the real
files already exist on this machine, skip the `touch`/`rm` and just confirm
`git status --porcelain -- refresh/` does not list them.)

- [ ] **Step 5: Update `AGENTS.md`**

In the Commands fenced block, after the `python3 refresh/build_page.py --ui-only` line, add:

```bash
python3 refresh/fetch_live.py               # live scores fetch -> refresh/live.json
python3 refresh/parse_live.py               # fold live.json into refresh/live_cache.json
```

and after the `python3 tests/test_payload.py` line, add:

```bash
python3 tests/test_live.py                  # live protocol/parse/merge tests (fixtures)
```

In the "Auto-refresh (cron)" bullet list, after the frontier bullet, add:

```
- also fetches the **live scores** grid (one callback per class row;
  placings land minutes after scoring) into `refresh/live.json` and folds
  it into the accumulating `refresh/live_cache.json`; a live failure is a
  warning only — the page degrades to official-only data;
```

In the Architecture bullet that lists git-ignored intermediates
(`data.json`, `entries/`, `jar.txt`, ...), replace
`cron.lock`, `tests/node_modules/` are git-ignored
with
`cron.lock`, `live.json`, `live_cache.json`, `tests/node_modules/` are
git-ignored

In the same Architecture section, after the "Data flow: ..." bullet, add:

```
- **Live scores:** `LiveScoring.aspx` (same session as the entry fetcher)
  is a second, faster data source. `fetch_live.py` walks its
  reverse-engineered DevExpress callback protocol (see the spec
  `docs/superpowers/specs/2026-08-24--live-scores-design.md` for the wire
  format) into `refresh/live.json`; `parse_live.py` accumulates placings in
  `refresh/live_cache.json`; `build_page.py` merges them: **official
  class-results placings always win, live fills gaps only**, and classes
  with live activity fresher than 60 min get a gold **live pill** on the
  page. If the live source fails or the files are missing, the page is
  byte-identical to official-only.
```

In "Tips for AI Agents", after the "The payload is one line" bullet, add:

```
**Live protocol is reverse-engineered:** `refresh/fetch_live.py` drives a
DevExpress ASPxGridView callback protocol that is not documented anywhere;
the wire format (c0: prefix, KV/FR/CT/GB segments, envelope stateObject)
is in the spec above. If it breaks, nothing is lost — the fetch fails
softly and the page degrades to official-only. Don't "simplify" the
callback param; every segment is load-bearing.
```

- [ ] **Step 6: Update `refresh/README.md`**

In the main command block, after `python3 parse_entries.py`, add:

```bash
python3 fetch_live.py    # fetch the live scores grid -> live.json (minutes after scoring)
python3 parse_live.py    # fold live.json into live_cache.json (accumulating)
```

After the bullet list (after the `payload.json` bullet), add:

```
- `live.json` / `live_cache.json` are git-ignored live-scores
  intermediates. `build_page.py` merges cached placings into entries that
  have no official place yet (official results always win) and puts a gold
  "live" pill on classes with live activity fresher than 60 min. If the
  live fetch fails — or the files are absent — the build output is exactly
  the official-only page.
```

- [ ] **Step 7: Full verification**

```bash
python3 tests/test_live.py
python3 tests/test_ui_only.py
python3 tests/test_asof.py
python3 tests/test_payload.py
python3 tests/test_frontier.py
npm --prefix tests test
bash -n refresh/refresh_cron.sh
git status --porcelain   # must not list refresh/live.json, refresh/live_cache.json, or any other intermediate
```

Expected: all suites green; clean status.

- [ ] **Step 8: One live cron cycle (publishes a real refresh to the site)**

Run: `bash refresh/refresh_cron.sh`
Expected: `refresh/cron.log` tail shows the live phase (no WARNING line) and
either "committed and pushed" (live placings changed the payload) or
"unchanged; nothing to publish". Then sanity-check the published payload:

```bash
python3 - <<'EOF'
import re
s = open('index.html').read()
print("classes:", len(re.findall(r'"n":"', s)))
print("entries:", len(re.findall(r'\["\d+","', s)))
print("live pills in payload:", len(re.findall(r'"live":', s)))
print("asof:", re.search(r'"asof":"([^"]*)"', s).group(1))
EOF
```

Expected: same class/entry counts as before (live fills places, never adds
entries), `live pills in payload` ≥ 0 (small integer; > 0 during an active
show), asof changed only if the data changed.
Note: never copy cron.log lines containing URLs into chat (they include the
`git push` remote).

- [ ] **Step 9: Commit**

```bash
git add refresh/refresh_cron.sh .gitignore AGENTS.md refresh/README.md
git commit -m "Run the live scores phase in cron and document it"
```

---

## Self-Review

**Spec coverage:**
- Callback protocol (spec §1) → Task 1 (parse/bootstrap/state), Task 3 (driver).
- `fetch_live.py` fail-safe + pacing → Task 3 (exit paths, `PACING`, untouched
  `live.json`).
- `parse_live.py` accumulating cache → Task 2.
- `build_page.py` merge + `live` field + asof unchanged → Task 4.
- `.clive` pill (gold family, pulse, reduced-motion, no emoji) → Task 4
  Step 5.
- Cron non-fatal live phase → Task 6 Step 1.
- Tests: fixture parse, minutes parsing, merge rule, cache behavior,
  freshness cutoff (59/61 via `updated_min` < 60 in the build test: 43 →
  present, 122 → absent), pill/place/up-next in jsdom → Tasks 1, 2, 4, 5.
- Docs (AGENTS.md, refresh/README.md) + gitignore → Task 6.
- Out of scope respected: no score display, no time text on the pill, no
  frontier change, not-placed ignored.

**Known deviations from the spec text (both intentional, noted in the
spec's corrected protocol section):**
- The spec's `fetch_live.py` bullet predates verification; the plan
  implements the verified per-row `SHOWDETAILROW` loop (spec §1 was updated
  to match).
- `live` payload field: the spec says `<minutes-ago>`; the plan implements
  exactly that (int minutes from `updated_min`), rendered as a pill with no
  time text.
