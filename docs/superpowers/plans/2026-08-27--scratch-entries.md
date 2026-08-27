# Scratch Entries Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or execute inline.
**Goal:** Show scratched (withdrawn) entries on the WCHS 2026 schedule page with the site's pink + strikethrough treatment, and keep all upcoming classes' scratch state fresh via a 4-hour cron refresh.
**Architecture:** Scratched entries already sit on the entry pages the pipeline fetches (their `<tr>` carries `background-color:LightPink;...text-decoration: line-through`). Parse flags them, `build_page.py` emits a per-class `"sc"` entry-number list (only when non-empty), the template renders matching rows with a `scratch` class, and a new stateless cron job (`refresh_upcoming.sh`) re-fetches every unsettled class on a 4-hour cadence.
**Tech Stack:** Python 3 stdlib, bash + curl, one-file HTML page (no deps), jsdom smoke tests.
**Spec:** `docs/superpowers/specs/2026-08-27--scratch-entries-design.md`

## Global Constraints
- `index.html` is generated — edit the template raw string in `refresh/build_page.py`, never the file.
- The template is a `r"""..."""` raw string; never drop the `r` prefix or "clean up" escapes.
- Page stays dependency-free (one HTML file, no external requests); pipeline stays Python stdlib + curl.
- asof policy: the "Updated" stamp changes only when the data changes. `sc` flows through the classes JSON, so `h`/`check.json`/asof follow automatically — do not add special handling.
- Official placings always win; scratched entries never carry places; the live merge and predicted pace must not touch `sc`.
- Never commit git-ignored intermediates: `refresh/entries/`, `data.json`, `jar.txt`, `fetchlist.txt`, `refreshlist.txt`, `upcominglist.txt`, `cron.log`, `cron.lock`, `live.json`, `live_cache.json`, `tests/node_modules/`.
- Never print `git remote -v` (PAT in the URL).
- The 8-minute cron (`refresh_cron.sh`) commits + pushes from this working tree every 8 min; commit rebuilt files promptly so the cron's byte-identical-skip keeps them.
- The show is LIVE (2026-08-27, day 6): task 5 publishes to GitHub Pages by pushing to `main`.

---

### Task 1: Parse the scratch mark
**Files:**
- Modify: `refresh/parse_entries.py` (`parse_rows` lines 7–23, `parse_page` entry loops lines 42–63)
- Test: `tests/test_parse_entries.py`

**Interfaces:**
- Consumes: existing `parse_rows(page, grid)` / `parse_page(page, fallback_num, classes, sched_lookup)`.
- Produces: row dicts gain `"scratch": bool`; entry dicts gain `"scratch": True` **only when scratched** (key absent otherwise). Later tasks read `e.get("scratch")` in `data.json`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parse_entries.py`, after the final `shutil.rmtree(tmp)` of section 5 (the "neither file canonical" block, ~line 177) and before the final `print("\n" + ...)` line:

```python
# 6. scratch rows: the show site marks withdrawn entries with a LightPink +
#    line-through <tr> style; exactly those entries are flagged (both grids)
SCRATCH_PAGE = """
<html><body>
<span class="dxeBase bold" id="ctl00_dxdt230_grPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1</td><td>1044</td><td>WA-SO FAR LUCKY</td><td>WALKER, DARIEN</td><td></td>
<td>WALKER, DARIEN</td><td>SIMPSON, AMANDA</td><td>$360.00</td><td>$0.00</td>
<td>6</td><td>0.000</td><td>0.000</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr id="ctl00_dxdt230_grPlacing_DXDataRow1" class="dxgvDataRow_Office2010Blue"
 style="background-color:LightPink;font-size:8pt;text-decoration: line-through;">
<td>5</td><td>1060</td><td>SCRATCHED PLACED</td><td>SP, RIDER</td><td></td>
<td>SP, OWNER</td><td>SP, TRAINER</td><td>$0.00</td><td>$0.00</td>
<td>4</td><td>0.000</td><td>0.000</td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
<span class="dxeBase bold" id="ctl00_dxdt230_grNonPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grNonPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1050</td><td>HORSE B</td><td>RIDER B</td><td></td><td>OWNER B</td>
<td>TRAINER B</td><td>$0.00</td><td>7</td><td></td><td></td><td>&nbsp;</td>
<td>&nbsp;</td></tr>
<tr id="ctl00_dxdt230_grNonPlacing_DXDataRow1" class="dxgvDataRow_Office2010Blue"
 style="background-color:LightPink;font-size:8pt;text-decoration: line-through;">
<td>1055</td><td>SCRATCH HORSE</td><td>SCRATCH RIDER</td><td></td>
<td>OWNER S</td><td>TRAINER S</td><td>$0.00</td><td>9</td>
<td></td><td></td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
</body></html>
"""
rec = pe.parse_page(SCRATCH_PAGE, "89", CLASSES, SCHED_LOOKUP)
scratched = sorted(e["entry"] for e in rec["entries"] if e.get("scratch") is True)
check("exactly the line-through rows carry scratch=True",
      rec is not None and scratched == ["1055", "1060"], str(scratched))
check("plain rows carry no scratch key",
      rec is not None and all("scratch" not in e for e in rec["entries"]
                              if e["entry"] not in ("1055", "1060")),
      str(rec and rec["entries"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_parse_entries.py`
Expected: the two new checks FAIL with `scratched = []` (no scratch key parsed yet); everything else passes.

- [ ] **Step 3: Write minimal implementation**

In `refresh/parse_entries.py`, replace `parse_rows` (lines 7–23) with:

```python
def parse_rows(page, grid):
    pat = re.compile(r'<tr id="[^"]*_' + grid + r'_DXDataRow\d+"([^>]*)>(.*?)</tr>', re.S)
    out = []
    for m in pat.finditer(page):
        tag, row = m.group(1), m.group(2)
        # scratch (withdrawn) rows carry the site's LightPink + line-through
        # <tr> style; plain rows have none
        scratch = "line-through" in tag
        # only top-level tds (not nested header tables)
        tds = re.findall(r'<td[^>]*>(?:(?!</td>).)*</td>', row, re.S)
        cells = [cell_text(td) for td in tds]
        # capture GUIDs
        eg = re.search(r'EntryGUID=([0-9a-f-]{36})', row)
        hg = re.search(r'HorseGUID=([0-9a-f-]{36})', row)
        rg = re.search(r'RiderGUID=([0-9a-f-]{36})', row)
        out.append({"cells": cells, "scratch": scratch,
                    "entry_guid": eg.group(1) if eg else None,
                    "horse_guid": hg.group(1) if hg else None,
                    "rider_guid": rg.group(1) if rg else None})
    return out
```

In `parse_page`, change the placed loop (lines 42–52) to:

```python
    for r in placed:
        c = r["cells"]
        # Place Entry Horse Rider Cntry Owner Trainer Prize AddBack Start Score Percent USEF EC
        if len(c) < 12: continue
        e = {
            "place": c[0] or None,
            "entry": c[1], "horse": c[2], "rider": c[3], "country": c[4] or None,
            "owner": c[5], "trainer": c[6], "start": c[9] if len(c) > 9 else None,
            "score": c[10] if len(c) > 10 else None,
            "entry_guid": r["entry_guid"], "horse_guid": r["horse_guid"], "rider_guid": r["rider_guid"],
        }
        if r["scratch"]:
            e["scratch"] = True
        entries.append(e)
```

and the nonpl loop (lines 53–63) to:

```python
    for r in nonpl:
        c = r["cells"]
        # Entry Horse Rider Cntry Owner Trainer Prize Start Score Percent USEF EC
        if len(c) < 10: continue
        e = {
            "place": None,
            "entry": c[0], "horse": c[1], "rider": c[2], "country": c[3] or None,
            "owner": c[4], "trainer": c[5], "start": c[7] if len(c) > 7 else None,
            "score": c[8] if len(c) > 8 else None,
            "entry_guid": r["entry_guid"], "horse_guid": r["horse_guid"], "rider_guid": r["rider_guid"],
        }
        if r["scratch"]:
            e["scratch"] = True
        entries.append(e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_parse_entries.py`
Expected: `ALL PASS` (all prior checks + the two new scratch checks).

- [ ] **Step 5: Commit**

```bash
git add refresh/parse_entries.py tests/test_parse_entries.py
git commit -m "Parse scratch (line-through) entry rows"
```

---

### Task 2: Payload `sc` + page rendering
**Files:**
- Modify: `refresh/build_page.py` (payload build lines 23–35; `:root` vars line 115 area, `html.dark` vars line 124 area; `.erow` CSS after line 206; `makeClass` JS lines 589–603)
- Test: `tests/test.js`

**Interfaces:**
- Consumes: `data.json` entry dicts with `e.get("scratch")` (Task 1).
- Produces: payload classes gain `"sc": [entryNum, ...]` (only when non-empty) after `"e"`; DOM rows gain class `scratch`; CSS classes `--scratch-bg` / `--scratch-ink` and `.erow.scratch`. Task 5's rebuild ships this to the live page.

- [ ] **Step 1: Write the failing test**

In `tests/test.js`, after the line `const DATA = JSON.parse(PL[1]);` (~line 16) add:

```js
const DATA_JSON = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "refresh", "data.json"), "utf8"));
// classes whose source data has scratched entries -> expected "sc" payload lists
const SCRATCH_SRC = DATA_JSON
  .map(c => ({ n: c.num, sc: c.entries.filter(e => e.scratch).map(e => e.entry).sort() }))
  .filter(x => x.sc.length);
```

In the first `setTimeout` block, after the "other-row .place stays gold" check (~line 243) and before `// ---------- dark mode toggle ----------` (~line 245), insert:

```js
  // ---------- scratch entries (withdrawn before their class) ----------
  const scrPayload = DATA.classes.map(c => ({ n: c.n, sc: c.sc || [] }));
  check("payload carries sc for every class with scratched entries",
        SCRATCH_SRC.length === 0 ||
        SCRATCH_SRC.every(s => {
          const p = scrPayload.find(x => x.n === s.n);
          return p && p.sc.length === s.sc.length && s.sc.every(n => p.sc.includes(n));
        }),
        "src " + SCRATCH_SRC.length + " vs payload classes with sc: " + scrPayload.filter(x => x.sc.length).length);
  const SCR = DATA.classes.find(c => c.sc && c.sc.length);
  if (SCR){
    const scrCard = [...doc.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCR.n);
    scrCard.querySelector(".cls-head").click();
    const rows = [...scrCard.querySelectorAll(".erow")];
    const scrRows = rows.filter(r => r.classList.contains("scratch"));
    check("scratch entries render with the scratch class",
          scrRows.length === SCR.sc.length, scrRows.length + " vs " + SCR.sc.length);
    check("scratch rows are exactly the scratched entry numbers",
          scrRows.every(r => SCR.sc.includes(r.querySelector(".eentry").textContent.trim())) &&
          rows.filter(r => !r.classList.contains("scratch")).length === SCR.e.length - SCR.sc.length);
    check("scratch styling declares background + strikethrough",
          /\.erow\.scratch\s*\{[^}]*background[^}]*\}/.test(css) &&
          /\.erow\.scratch [^{]*\{[^}]*text-decoration\s*:\s*line-through[^}]*\}/.test(css));
  }
```

Note: `css` (the joined `<style>` text) is already in scope from the CSS audit block above; no filter is active at this point, so the card opens with all entries.

- [ ] **Step 2: Rebuild current state and run test to verify it fails**

```bash
(cd refresh && python3 parse_entries.py)   # parse_entries.py uses CWD-relative paths; cron runs it from refresh/
python3 refresh/build_page.py              # build_page.py resolves paths relative to its own file
npm --prefix tests test
```
Expected: `FAIL  payload carries sc for every class with scratched entries` (data.json now carries scratch flags from Task 1, but the payload has no `sc`); all other checks pass.

- [ ] **Step 3: Write minimal implementation**

In `refresh/build_page.py`, replace the classes build (lines 23–35) with:

```python
    classes = []
    for c in data:
        cc = {
            "n": c["num"],
            "name": c["name"],
            "div": c["division"],
            "wk": c.get("weekday"),
            "day": c.get("date"),
            "per": c.get("period"),
            "time": c.get("time"),
            "e": [[e["entry"], e["horse"], e["rider"], e["trainer"], e["owner"], e.get("start"), e.get("place")]
                  for e in c["entries"]],
        }
        # scratched (withdrawn) entries, by entry number; key only when non-empty
        sc = [e["entry"] for e in c["entries"] if e.get("scratch")]
        if sc:
            cc["sc"] = sc
        classes.append(cc)
```

CSS variables — add to the `:root` block after the `--now-bg: #fffbeb; --now-line: #f59e0b;` line:

```css
  --scratch-bg: #fbd0dc; --scratch-ink: #b91c1c;
```

and to the `html.dark` block after its `--now-bg: #33260a; --now-line: #f59e0b;` line:

```css
  --scratch-bg: #3b1522; --scratch-ink: #fca5a5;
```

Rules — add after the `.erow.other .eppl .place { ... }` line:

```css
.erow.scratch { background: var(--scratch-bg); }
.erow.scratch .eentry b, .erow.scratch .ehorse, .erow.scratch .eppl { color: var(--scratch-ink); text-decoration: line-through; }
```

JS — in `makeClass`, after `const on = active();` add:

```js
  const scr = new Set(c.sc || []);
```

and change the row creation line `const row = el("div","erow" + (other ? " other" : ""));` to:

```js
      const row = el("div","erow" + (other ? " other" : "") + (scr.has(e[0]) ? " scratch" : ""));
```

- [ ] **Step 4: Rebuild and run tests to verify they pass**

```bash
python3 refresh/build_page.py
npm --prefix tests test
python3 tests/test_parse_entries.py
python3 tests/test_asof.py
python3 tests/test_ui_only.py
python3 tests/test_payload.py
python3 tests/test_check.py
```
Expected: jsdom suite ALL PASS including the three new scratch checks (the real payload has scratched entries); all python suites ALL PASS.

- [ ] **Step 5: Commit**

Commit the feature files and the rebuilt artifacts together (the rebuild changed the data, so asof advanced — that is the intended publish). The 8-minute cron may have committed the same bytes moments earlier; check `git status` first and add only what is still modified:

```bash
git status --porcelain -- refresh/build_page.py tests/test.js index.html payload.json check.json
git add refresh/build_page.py tests/test.js index.html payload.json check.json
git commit -m "Render scratch entries (pink strikethrough) via per-class sc list"
```

---

### Task 3: `upcoming` class selection
**Files:**
- Modify: `refresh/select_frontier.py` (new function after `lookahead_nums` ~line 81; CLI choices ~line 85; dispatch ~line 112)
- Test: `tests/test_frontier.py`

**Interfaces:**
- Consumes: existing `is_settled(num, cj, data)`, `is_stale(num, sched, now)`, `fetch_nums_for(num, cj)`, `_order(sched)`.
- Produces: `upcoming_nums(sched, cj, data, now) -> [num, ...]` (schedule order, sections expanded, settled + stale excluded) and the `select_frontier.py upcoming` CLI (one num per line; prints nothing when empty). Task 4's script consumes the CLI.

- [ ] **Step 1: Write the failing test**

In `tests/test_frontier.py`, after the CLI checks of section 8 (after the `cli lookahead` check, ~line 111) and before the `# 9. property check against the real committed payload` header, insert:

```python
# 8b. upcoming: every not-yet-settled, not-stale schedule class in order,
#     sections expanded (the 4-hour scratch refresh fetches exactly these)
D_UP = [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 3), rec("4", [None] * 2),
        rec("5.1", [None] * 2), rec("5.2", ["1"])]
check("upcoming lists unsettled non-stale classes in schedule order",
      sf.upcoming_nums(SCHED, set(CLASSES), D_UP, NOW_A) == ["3", "4", "5.1", "5.2"],
      str(sf.upcoming_nums(SCHED, set(CLASSES), D_UP, NOW_A)))
check("upcoming excludes stale (presumed skipped) classes",
      sf.upcoming_nums(SCHED, set(CLASSES),
                       [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 2), rec("4", [None] * 2)],
                       NOW_LATE) == ["4"])
check("upcoming is empty when everything is settled",
      sf.upcoming_nums(SCHED, set(CLASSES), ALL_DONE, NOW_A) == [])
json.dump(D_UP, open(data_p, "w"))
rc, out = cli("upcoming")
check("cli upcoming prints fetchable nums in order", out == "3\n4\n5.1\n5.2", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_frontier.py`
Expected: `FAIL` on the first new check — `AttributeError: module 'select_frontier' has no attribute 'upcoming_nums'`.

- [ ] **Step 3: Write minimal implementation**

In `refresh/select_frontier.py`, after `lookahead_nums` add:

```python
def upcoming_nums(sched, cj, data, now):
    """All schedule classes not yet settled and not stale, in schedule order,
    each expanded to its fetchable sections. The 4-hour scratch refresh
    (refresh_upcoming.sh) fetches exactly these: settled classes' pages
    already contain every scratch they will ever have, and stale classes are
    presumed skipped (same rule as the frontier)."""
    out = []
    for num in _order(sched):
        if is_settled(num, cj, data):
            continue
        if is_stale(num, sched, now):
            continue
        out.extend(fetch_nums_for(num, cj))
    return out
```

Change the CLI choices line to:

```python
    ap.add_argument("cmd", choices=["frontier", "frontier-nums", "settled", "lookahead", "upcoming"])
```

and after the `elif a.cmd == "lookahead":` block add:

```python
    elif a.cmd == "upcoming":
        nums = upcoming_nums(sched, cj, data, now)
        if nums:
            print("\n".join(nums))
```

(The `if nums` guard matters: an empty print would write a newline and defeat the script's `[ -s "$LIST" ]` check.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_frontier.py`
Expected: `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add refresh/select_frontier.py tests/test_frontier.py
git commit -m "Add upcoming (unsettled non-stale) class selection for the scratch refresh"
```

---

### Task 4: `refresh_upcoming.sh` (the 4-hour job)
**Files:**
- Create: `refresh/refresh_upcoming.sh`
- Modify: `.gitignore` (add `refresh/upcominglist.txt`)

**Interfaces:**
- Consumes: `select_frontier.py upcoming` (Task 3), `fetch_entries.sh <list>` (no-skip list mode), `parse_entries.py`, `build_page.py`, `cron.lock` / `cron.log`.
- Produces: an executable cron script; cron line `0 */4 * * *  <repo>/refresh/refresh_upcoming.sh` (installed in Task 5).

- [ ] **Step 1: Create the script**

Write `refresh/refresh_upcoming.sh`:

```bash
#!/bin/bash
# 4-hour scratch refresh for the WCHS 2026 schedule page.
#
# Re-fetches the entry pages of every class that is not settled yet (no
# placings posted) so scratches (entries withdrawn before their class,
# shown on the site with a pink strikethrough row) stay current across the
# whole upcoming schedule. refresh_cron.sh (8-minute) keeps only the
# frontier + lookahead fresh; this pass covers the rest.
#
#   cron: 0 */4 * * *  <repo>/refresh/refresh_upcoming.sh
#
# Same lock/log/safety as refresh_cron.sh: a run that overlaps the 8-minute
# job (or another upcoming run) skips. The first run after deploy is the
# one-time "big refresh" of all unsettled classes.
set -u
export PATH=/usr/local/bin:/usr/bin:/bin
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
LOG="$HERE/cron.log"
LOCK="$HERE/cron.lock"
LIST="$HERE/upcominglist.txt"

exec >>"$LOG" 2>&1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*"; log "=== upcoming refresh aborted ==="; exit 1; }

log "=== upcoming refresh start (pid $$) ==="

# one run at a time, sharing the 8-minute job's lock
exec 9>"$LOCK"
if ! flock -n 9; then
  log "previous run still going, skipping"
  exit 0
fi

cd "$HERE" || die "cannot cd to $HERE"
git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || die "not a git repo"

# --- fetch phase
nfiles=$(ls entries/ 2>/dev/null | wc -l)
total=$(python3 -c "import json; print(len(json.load(open('classes.json'))))")
if [ "$nfiles" -lt 50 ]; then
  log "entries/ has $nfiles/$total pages -> full resumable fetch"
  bash fetch_entries.sh || log "WARNING: full fetch had failures (resumable; retries next run)"
  python3 parse_entries.py >/dev/null
else
  python3 select_frontier.py upcoming > "$LIST"
  if [ ! -s "$LIST" ]; then
    log "nothing upcoming (all classes settled); nothing to do"
    log "=== upcoming refresh done ==="
    exit 0
  fi
  log "upcoming: $(tr '\n' ' ' < "$LIST")"
  bash fetch_entries.sh "$LIST" || log "WARNING: upcoming fetch had failures"
  python3 parse_entries.py >/dev/null
fi

# --- safety: refuse to publish a catastrophic data loss
counts=$(python3 - <<'PY'
import json, os, re
new = json.load(open('data.json'))
new_n = sum(len(c['entries']) for c in new)
m = re.search(r'^(?:const|let) DATA = (\{.*\});\s*$',
              open(os.path.join('..', 'index.html')).read(), re.M)
old_n = sum(len(c['e']) for c in json.loads(m.group(1))['classes']) if m else 0
print(new_n, old_n)
PY
)
new_n=${counts%% *}
old_n=${counts##* }
log "entries: $old_n -> $new_n"
if [ "$old_n" -gt 0 ] && [ "$new_n" -lt $((old_n / 2)) ]; then
  die "entry count dropped to $new_n (was $old_n); refusing to publish"
fi

# --- build + publish (asof only changes when the data changed)
python3 build_page.py || die "build failed"
if git -C "$ROOT" diff --quiet HEAD -- index.html payload.json check.json; then
  log "unchanged; nothing to publish"
else
  git -C "$ROOT" add index.html payload.json check.json || die "git add failed"
  git -C "$ROOT" commit -m "Refresh upcoming entries $(date +%F)" || die "git commit failed"
  git -C "$ROOT" push || die "git push failed"
  log "committed and pushed"
fi
log "=== upcoming refresh done ==="
```

- [ ] **Step 2: Make it executable and syntax-check it**

```bash
chmod +x refresh/refresh_upcoming.sh
bash -n refresh/refresh_upcoming.sh && echo SYNTAX_OK
```
Expected: `SYNTAX_OK`.

- [ ] **Step 3: Add the list file to .gitignore**

In `.gitignore`, after the `refresh/refreshlist.txt` line add:

```
refresh/upcominglist.txt
```

- [ ] **Step 4: Verify the selection against live data (no network)**

```bash
python3 refresh/select_frontier.py frontier
python3 refresh/select_frontier.py upcoming
```
Expected: `upcoming` prints a non-empty list whose FIRST line equals the `frontier` output, all lines present in `refresh/classes.json`, in schedule order (roughly the frontier class through the end of the show, sections included).

- [ ] **Step 5: Commit**

```bash
git add refresh/refresh_upcoming.sh .gitignore
git commit -m "Add 4-hour upcoming-class scratch refresh (refresh_upcoming.sh)"
```

---

### Task 5: Rollout — full test gate, big refresh, cron install, docs
**Files:**
- Modify: `AGENTS.md`, `refresh/README.md`
- No code changes; this task publishes the feature.

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: the live page shows scratches; the 4-hour cron is installed; docs are current.

- [ ] **Step 1: Run the full test suite**

```bash
python3 tests/test_parse_entries.py
python3 tests/test_frontier.py
python3 tests/test_predict.py
python3 tests/test_asof.py
python3 tests/test_ui_only.py
python3 tests/test_payload.py
python3 tests/test_check.py
python3 tests/test_live.py
python3 tests/test_class_list.py
npm --prefix tests test
```
Expected: every suite prints `ALL PASS` / no failures. Fix anything that fails before proceeding (if it is a real bug, stop and debug — do not weaken a test to pass).

- [ ] **Step 2: Re-parse, rebuild, sanity-check the payload**

```bash
(cd refresh && python3 parse_entries.py)
python3 refresh/build_page.py
python3 - <<'EOF'
import re
s = open('index.html').read()
print("classes:", len(re.findall(r'"n":"', s)))
print("entries:", len(re.findall(r'\["\d+","', s)))
print("asof:", re.search(r'"asof":"([^"]*)"', s).group(1))
print("sc classes:", len(re.findall(r'"sc":\[', s)))
import json
print("check:", open('check.json').read().strip())
EOF
```
Expected: classes count ≈ 241 (grows during the show), entries ≈ 3500, `sc classes` > 0, and the `check.json` line matches the printed asof. If `sc classes` is 0, something is wrong in Tasks 1–2 — stop and debug.

- [ ] **Step 3: Run the big refresh (first run of the new job)**

```bash
bash refresh/refresh_upcoming.sh
tail -30 refresh/cron.log
```
Expected in `cron.log`: `=== upcoming refresh start`, `upcoming: <frontier> ... <last class>`, `FETCHED ok=N failed=0` (N = unsettled class count), the build lines, and either `committed and pushed` or `unchanged; nothing to publish` (both are correct — a changed push publishes the freshly re-fetched upcoming pages). Then `git log --oneline -3` shows the new commit (if any) and `git status --porcelain -- index.html payload.json check.json` is clean.

- [ ] **Step 4: Install the cron line (present to the user; install only after explicit OK)**

Present this line and ask the user to confirm before running:

```bash
(crontab -l 2>/dev/null; echo "0 */4 * * *  /home/jcuzens/dev/test/refresh/refresh_upcoming.sh") | crontab -
crontab -l
```
Expected: both cron entries (the existing `*/8 ... refresh_cron.sh` and the new `0 */4 ... refresh_upcoming.sh`) are listed.

- [ ] **Step 5: Update AGENTS.md**

In the Commands section, after the `python3 refresh/parse_live.py` line add:

```
bash refresh/refresh_upcoming.sh               # one 4-hour scratch-refresh cycle, manually (cron: 0 */4 * * *)
```

In the "## Auto-refresh (cron)" section, after the paragraph ending with "masked by git, but never copy log lines containing URLs)." add:

```
**Scratch refresh (separate 4-hour cron):** `refresh/refresh_upcoming.sh`
re-fetches the entry pages of every class that is not settled yet (no
placings) and rebuilds + publishes on change. Scratch marks (entries
withdrawn before their class) can appear hours before a class, so the
8-minute frontier + lookahead alone would miss them further down the
schedule. The first run after deploy is the one-time full refresh of all
unsettled classes; settled classes' pages already contain every scratch
they will ever have (they were re-fetched when their results posted).
Stale (presumed skipped) classes are excluded, same rule as the frontier.
It shares `cron.lock` and `cron.log` with the 8-minute job, so the two
never run at once; an overlapping run just skips.
```

In the "## Architecture" section, after the **Live scores** bullet add:

```
- **Scratch entries:** withdrawn entries sit on the same ClassResults.aspx
  pages the pipeline already fetches, marked on the `<tr>` with
  `background-color:LightPink;…text-decoration: line-through`.
  `parse_entries.py` flags them, `build_page.py` emits a per-class
  `"sc": [entry numbers]` (only when non-empty), and the page renders
  those rows with a pink background + strikethrough. No separate source
  or fetcher — the 4-hour upcoming refresh (above) is the only new
  moving part.
```

In "## Tips for AI Agents", after the "The master grid is the class universe" tip add:

```
**Scratch marks are on the pages we already fetch:** the line-through
`<tr>` style on an entry page is the whole signal. Settled classes' pages
were re-fetched when their results posted, so they already contain all
their scratches; only unsettled classes need periodic re-fetching (the
4-hour upcoming refresh).
```

- [ ] **Step 6: Update refresh/README.md**

In the "### Auto-refresh (cron)" section, after the paragraph ending with "no state file." add:

```
A second job, `refresh_upcoming.sh`, runs every 4 hours and re-fetches the
pages of every class that is not settled yet — scratch (withdrawn) entries
can appear hours before a class, and the 8-minute job only keeps the
frontier + lookahead fresh. It shares the lock and log with `refresh_cron.sh`
and publishes only when the data changed. Scratch rows render on the page
with a pink background and strikethrough, like the main site.
```

- [ ] **Step 7: Commit docs**

```bash
git add AGENTS.md refresh/README.md
git commit -m "docs: scratch entries + 4-hour upcoming refresh"
```

- [ ] **Step 8: Push everything**

```bash
git status --porcelain
git push
git log --oneline -6
```
Expected: working tree clean (tracked files) and the local commits (dedupe fix, scratch feature, upcoming selection, script, docs — any not yet pushed by the 8-minute cron) are on `main`. The page at https://jcuzens.github.io/wchs2026/ shows scratched entries within 1–2 minutes.
