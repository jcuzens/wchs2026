# Live Page Updates Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or execute inline.
**Goal:** Make the open schedule page pull fresh data from `payload.json` every 30 s and re-render in place (up-next moves, done goes green) without ever bouncing the user's view.
**Architecture:** The cron pipeline additionally commits a compact `payload.json` at the repo root (GitHub Pages serves it). The page shell keeps the embedded snapshot for first paint, gains a poller (fetch + change-detection + full re-render with state preservation), a CSS-transition-animated countdown ring, and "no view bounce" rules (scroll/focus/day-collapse preservation, focus-deferred re-renders).
**Tech Stack:** Python 3 stdlib, bash, vanilla JS in a generated single-file page, jsdom (dev-only) for page tests.
**Spec:** `docs/superpowers/specs/2026-08-23--live-update-design.md`

## Execution state (update as tasks complete)

- Mode: **serial** subagent-driven development — exactly one subagent
  dispatched at a time (user constraint: no concurrent agents, VRAM limit).
  Continuous execution per the subagent-driven-development skill; review
  between tasks; no pausing for check-ins.
- Workspace: work directly in `/home/jcuzens/dev/test` (no worktree): the
  production cron runs in this very directory every 8 min, and git-ignored
  intermediates (`entries/`, `data.json`) would need duplication in a
  worktree with an `index.html` merge conflict on top. Mid-edit template
  state is a short risk window for a cron rebuild; the cron's safety checks
  bound it.
- **Do not push** until the user explicitly says so (Task 7 Step 6).
- Progress (BASE before Task 1: `81254d5`):

| Task | Status | Commit |
|---|---|---|
| 1 payload.json in the build | not started | — |
| 2 cron commits both files | not started | — |
| 3 `let DATA` + `buildIndexes()` | not started | — |
| 4 poller core | not started | — |
| 5 countdown ring | not started | — |
| 6 no view bounce | not started | — |
| 7 docs + final verification | not started | — |

## Global Constraints

- `index.html` is **generated** — all page markup/CSS/JS lives in the raw-string template in `refresh/build_page.py`; never hand-edit `index.html`. Keep the `r"""..."""` raw prefix on the template.
- The page stays one HTML file with **no external requests** (the `payload.json` fetch is same-origin); the pipeline stays Python stdlib + curl. jsdom remains a dev-only test dependency in `tests/`.
- The payload stays one compact JSON line in `index.html`; `payload.json` = the same bytes + one trailing newline.
- Git-ignored intermediates (`refresh/data.json`, `refresh/entries/`, `refresh/jar.txt`, `refresh/cron.log`, `refresh/cron.lock`, lists, `tests/node_modules/`) are never staged. Never print `git remote -v` (PAT in URL).
- Commit messages match repo style (imperative, descriptive, e.g. `Refresh entries 2026-08-23`).
- The show is live: every task must leave the repo in a buildable, testable, deployable state.
- Run all commands from the repo root `/home/jcuzens/dev/test`.

---

### Task 1: `build_page.py` publishes `payload.json` (TDD)

**Files:**
- Create: `tests/test_payload.py`
- Modify: `refresh/build_page.py:15` (regex), `refresh/build_page.py:41` (regex), `refresh/build_page.py:51` (after payload computation)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `payload.json` at repo root, byte-equal to the embedded payload minus newline; regular builds write it, `--ui-only` never touches it. Later tasks rely on the `(?:const|let)` payload-line regex shape.

- [ ] **Step 1: Write the failing test** — create `tests/test_payload.py`:

```python
#!/usr/bin/env python3
"""payload.json (the published data file the page polls) follows the same
asof policy as the embedded payload: written by a regular build,
byte-identical across rebuilds around unchanged data, asof bumped when the
data changes, untouched by --ui-only. Restores repo state at the end."""
import datetime, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
PLJ = os.path.join(ROOT, "payload.json")
DATA = os.path.join(ROOT, "refresh", "data.json")
BUILDER = os.path.join(ROOT, "refresh", "build_page.py")

def embedded_payload(path):
    s = open(path).read()
    m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
    assert m, "payload not found in " + path
    return m.group(1)

def asof_of_payload(p):
    return json.loads(p)["asof"]

def build(*args):
    subprocess.run([sys.executable, BUILDER, *args], check=True)

def wait_next_minute():
    time.sleep(60 - datetime.datetime.now().second + 1)

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

idx_backup = IDX + ".bak"
plj_backup = PLJ + ".bak"
plj_existed = os.path.exists(PLJ)
shutil.copyfile(IDX, idx_backup)
if plj_existed:
    shutil.copyfile(PLJ, plj_backup)
try:
    # 1. a regular build publishes payload.json equal to the embedded payload
    build()
    check("payload.json written by build", os.path.exists(PLJ))
    check("payload.json equals embedded payload",
          open(PLJ).read().rstrip("\n") == embedded_payload(IDX))
    a0 = asof_of_payload(open(PLJ).read())

    # 2. rebuild with unchanged data -> byte-identical (asof policy holds)
    p_before = open(PLJ).read()
    build()
    check("unchanged data keeps payload.json byte-identical",
          open(PLJ).read() == p_before, asof_of_payload(open(PLJ).read()) + " vs " + a0)

    # 3. changed data -> asof bumps (same pattern as test_asof.py)
    if a0 == datetime.datetime.now().strftime('%Y-%m-%d %H:%M'):
        wait_next_minute()
    backup = DATA + ".bak"
    shutil.copyfile(DATA, backup)
    try:
        d = json.load(open(DATA))
        d.append({"num": "999998", "name": "payload policy test class", "type": None, "division": "TEST",
                  "entries": [], "weekday": "Saturday", "period": "Morning", "date": "August 29", "time": "1:00 p.m."})
        json.dump(d, open(DATA, "w"), indent=1)
        build()
        check("changed data bumps payload.json asof",
              asof_of_payload(open(PLJ).read()) != a0, asof_of_payload(open(PLJ).read()) + " vs " + a0)
        check("changed data also bumps embedded asof",
              asof_of_payload(embedded_payload(IDX)) != a0)
    finally:
        shutil.move(backup, DATA)

    # 4. --ui-only never touches payload.json
    p_before = open(PLJ).read()
    build("--ui-only")
    check("--ui-only leaves payload.json untouched", open(PLJ).read() == p_before)

    # 5. restore: rebuild from real data, fake class gone
    build()
    check("restored build drops test class",
          "999998" not in open(IDX).read() and "999998" not in open(PLJ).read())
finally:
    shutil.move(idx_backup, IDX)
    if plj_existed:
        shutil.move(plj_backup, PLJ)
    elif os.path.exists(PLJ):
        os.remove(PLJ)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tests/test_payload.py`
Expected: FAIL — `payload.json written by build` fails (file not created by the build yet).

- [ ] **Step 3: Implement in `refresh/build_page.py`**

a) Both payload-line regexes (the `--ui-only` extraction near line 15 and the asof comparison near line 41) change from

```python
re.search(r"^const DATA = (\{.*\});\s*$", ...)
```

to

```python
re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", ...)
```

b) In the regular-build branch, immediately after `payload = json.dumps({"asof": asof, "classes": classes}, separators=(',', ':'))` (line 51), add:

```python
    with open(os.path.join(ROOT, "payload.json"), "w") as f:
        f.write(payload + "\n")
    print(f"payload.json: {os.path.getsize(os.path.join(ROOT, 'payload.json'))/1024:.0f} KB")
```

(`--ui-only` must NOT write it.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/test_payload.py`
Expected: ALL PASS (5 checks). Note: check 3 may wait up to 60 s (asof minute aliasing, same as `test_asof.py`).

- [ ] **Step 5: Run the rest of the suite**

Run: `python3 refresh/build_page.py && npm --prefix tests test && python3 tests/test_ui_only.py && python3 tests/test_asof.py && python3 tests/test_frontier.py`
Expected: all pass (the new `(?:const|let)` regex still matches the current `const DATA` line).

- [ ] **Step 6: Commit**

```bash
git add refresh/build_page.py tests/test_payload.py
git commit -m "Publish payload.json: compact data file for live page polling, same asof policy as the embedded payload; test"
```

---

### Task 2: `refresh_cron.sh` commits `index.html` + `payload.json`

**Files:**
- Modify: `refresh/refresh_cron.sh` (lines 8, 11, 38, 85, 100, 103)

**Interfaces:**
- Consumes: `payload.json` produced by Task 1's build.
- Produces: cron publishes both files; no-change detection covers both. No code interface for later tasks.

- [ ] **Step 1: Make the edits** (exact line changes):

Line 8:
```bash
# rebuilds index.html; commit and push only when the data actually changed.
```
→
```bash
# rebuilds index.html + payload.json; commit and push only when data changed.
```

Line 11:
```bash
# Only index.html is ever committed; the git-ignored intermediates
# (entries/, data.json, jar.txt) stay local.
```
→
```bash
# Only index.html and payload.json are ever committed; the git-ignored
# intermediates (entries/, data.json, jar.txt) stay local.
```

Line 38:
```bash
if [ -n "$(git -C "$ROOT" status --porcelain -- index.html)" ]; then
```
→
```bash
if [ -n "$(git -C "$ROOT" status --porcelain -- index.html payload.json)" ]; then
```

Line 85 (inside the safety heredoc):
```python
m = re.search(r'^const DATA = (\{.*\});\s*$',
              open(os.path.join('..', 'index.html')).read(), re.M)
```
→
```python
m = re.search(r'^(?:const|let) DATA = (\{.*\});\s*$',
              open(os.path.join('..', 'index.html')).read(), re.M)
```

Line 100:
```bash
if git -C "$ROOT" diff --quiet HEAD -- index.html; then
```
→
```bash
if git -C "$ROOT" diff --quiet HEAD -- index.html payload.json; then
```

Line 103:
```bash
  git -C "$ROOT" add index.html || die "git add failed"
```
→
```bash
  git -C "$ROOT" add index.html payload.json || die "git add failed"
```

- [ ] **Step 2: Verify syntax and diff**

Run: `bash -n refresh/refresh_cron.sh && git diff refresh/refresh_cron.sh`
Expected: no syntax error; the diff shows exactly the six changes above and nothing else. (Do NOT run `refresh_cron.sh` itself — it fetches from the network and pushes.)

- [ ] **Step 3: Commit**

```bash
git add refresh/refresh_cron.sh
git commit -m "Cron refresh: commit and publish payload.json alongside index.html"
```

---

### Task 3: `let DATA` + `buildIndexes()` refactor (verified refactor, no behavior change)

**Files:**
- Modify: `refresh/build_page.py` template — `const DATA` line (template line 185) and the index-build block (template lines 233-245)
- Modify: `tests/test.js:12` (payload-line regex)
- Modify: `tests/test_ui_only.py:14` (regex)
- Modify: `tests/test_frontier.py:117` (regex)

**Interfaces:**
- Consumes: nothing new.
- Produces: a reassignable top-level `DATA` binding and `buildIndexes()` — Task 4's poller reassigns `DATA` and calls `buildIndexes()` after each accepted update.

- [ ] **Step 1: Change the template in `refresh/build_page.py`**

`const DATA = __PAYLOAD__;` → `let DATA = __PAYLOAD__;`

Replace the block

```js
// ---- build name indexes
const NAMES = {trainer:{}, rider:{}, horse:{}, owner:{}};
const DIVS = {};
for (const c of DATA.classes){
  DIVS[norm(c.div)] = c.div;
  for (const e of c.e){
    const t = norm(e[3]); if (t) (NAMES.trainer[t] ||= {d:e[3], n:0}).n++;
    const r = norm(e[2]); if (r) (NAMES.rider[r]   ||= {d:e[2], n:0}).n++;
    const h = norm(e[1]); if (h) (NAMES.horse[h]   ||= {d:e[1], n:0}).n++;
    const o = norm(e[4]); if (o) (NAMES.owner[o]   ||= {d:e[4], n:0}).n++;
  }
}
const DIV_LIST = Object.values(DIVS).sort();
```

with

```js
// ---- build name indexes
const NAMES = {trainer:{}, rider:{}, horse:{}, owner:{}};
const DIVS = {};
let DIV_LIST = [];
function buildIndexes(){
  NAMES.trainer = {}; NAMES.rider = {}; NAMES.horse = {}; NAMES.owner = {};
  for (const k in DIVS) delete DIVS[k];
  for (const c of DATA.classes){
    DIVS[norm(c.div)] = c.div;
    for (const e of c.e){
      const t = norm(e[3]); if (t) (NAMES.trainer[t] ||= {d:e[3], n:0}).n++;
      const r = norm(e[2]); if (r) (NAMES.rider[r]   ||= {d:e[2], n:0}).n++;
      const h = norm(e[1]); if (h) (NAMES.horse[h]   ||= {d:e[1], n:0}).n++;
      const o = norm(e[4]); if (o) (NAMES.owner[o]   ||= {d:e[4], n:0}).n++;
    }
  }
  DIV_LIST = Object.values(DIVS).sort();
}
buildIndexes();
```

- [ ] **Step 2: Update the payload-line regexes in the three test files**

`tests/test.js` line 12:
```js
const PL = HTML.match(/^const DATA = (.*);$/m);
```
→
```js
const PL = HTML.match(/^(?:const|let) DATA = (.*);$/m);
```

`tests/test_ui_only.py` `payload_of()`:
```python
    m = re.search(r"^const DATA = (\{.*\});\s*$", s, re.M)
```
→
```python
    m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
```

`tests/test_frontier.py` (real-payload section):
```python
payload = json.loads(re.search(
    r'^const DATA = (\{.*\});\s*$',
    open(os.path.join(ROOT, "index.html")).read(), re.M).group(1))
```
→
```python
payload = json.loads(re.search(
    r'^(?:const|let) DATA = (\{.*\});\s*$',
    open(os.path.join(ROOT, "index.html")).read(), re.M).group(1))
```

- [ ] **Step 3: Rebuild and run the full suite**

Run: `python3 refresh/build_page.py && npm --prefix tests test && python3 tests/test_ui_only.py && python3 tests/test_asof.py && python3 tests/test_frontier.py && python3 tests/test_payload.py`
Expected: all pass. (`--ui-only` now round-trips a `let DATA` line via the updated regex; `test_ui_only.py`'s idempotency check proves it.)

- [ ] **Step 4: Commit**

```bash
git add refresh/build_page.py tests/test.js tests/test_ui_only.py tests/test_frontier.py
git commit -m "Page JS: make DATA a let binding and factor index building into buildIndexes() for live data swaps"
```

---

### Task 4: Poller core — fetch, change detection, re-render, Updated line (TDD)

**Files:**
- Modify: `refresh/build_page.py` template — `<div class="updated" ...>` (line 168), CSS `header .updated` (line 71), JS (new live-update block before `// ---- init`, new `restoreSearch()`, init tail lines 572-580)
- Modify: `tests/test.js` (live-update section; see Step 1)

**Interfaces:**
- Consumes: `let DATA`, `buildIndexes()` (Task 3); `renderFilters()`, `renderSchedule()`, `fmtAsof()`, `search` (existing).
- Produces: `pollingActive` (bool), `poll()` (async, self-rescheduling), `applyDataUpdate(p)` (swaps in payload `p` and re-renders), `setUpdatedLine(stale)` (writes `#updatedText`, ring display handled in Task 5), `restoreSearch()`, `POLL_MS` (overridable via `window.__POLL_MS`). Task 5 builds on `poll()`'s finally block; Task 6 extends `applyDataUpdate()` and `poll()`.

- [ ] **Step 1: Write the failing tests** — in `tests/test.js`:

a) Refactor `orderedClasses()` (lines 53-69) to a parameterized helper, keeping the existing call site working:

```js
// mirror of the page's display order: day -> session -> class number
const PER_ORDER = {Morning:0, Afternoon:1, Night:2, Evening:2};
function orderedClassesOf(cls){
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
const orderedClasses = () => orderedClassesOf(DATA.classes);
```

b) Replace the tail of the mobile-default `setTimeout` (the `console.log` + `process.exit` after the three mobile checks, current lines 256-266) with the live-update section. The mobile checks themselves stay; after the last mobile check (`schedule still renders on mobile default`), insert and end with:

```js
        // ---------- (10) live update: the shell polls payload.json ----------
        // (jsdom has no fetch; this dom stubs it. __POLL_MS=50 speeds the cycle.)
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const P1_ASOF = "2026-08-25 11:00";
        const liveDom = makeDom({
          url: "https://example.com/index.html",
          beforeParse: w => {
            pinDate(w);
            w.__POLL_MS = 50;
            Object.defineProperty(w, "scrollY", { value: 123, configurable: true });
            w.__scrollCalls = [];
            w.scrollTo = (x, y) => w.__scrollCalls.push([x, y]);
            // phase-1 payload: settle the current frontier class, bump asof
            const p1 = JSON.parse(JSON.stringify(DATA));
            const f1 = p1.classes.find(c => c.n === FRONTIER_NUM);
            if (f1 && f1.e.length) f1.e[0][6] = "1";
            p1.asof = P1_ASOF;
            w.__live = { current: p1, fail: false };
            w.fetch = async () => {
              if (w.__live.fail) throw new Error("network down");
              return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(w.__live.current)) };
            };
          },
        });
        const w4 = liveDom.window, d4 = w4.document;
        w4.addEventListener("error", e => { console.log("WINDOW ERROR (live):", e.message); failures++; });
        // expectations computed from the fetched payload (the show may be over
        // when this runs: FRONTIER_NUM can be null, then p1 differs only by asof)
        const P1 = w4.__live.current;
        const P1_DONE = P1.classes.filter(isDone).length;
        const P1_FRONTIER = orderedClassesOf(P1.classes).find(c => !isDone(c));
        const P1_FRONTIER_NUM = P1_FRONTIER ? P1_FRONTIER.n : null;

        (async () => {
          await sleep(250);   // several 50 ms polls have landed

          // check 1: the page re-rendered from the fetched data
          check("live: done count matches fetched data", d4.querySelectorAll(".cdone").length === P1_DONE, "got " + d4.querySelectorAll(".cdone").length + " vs " + P1_DONE);
          check("live: done cards tinted", d4.querySelectorAll("main .cls.done").length === P1_DONE, "got " + d4.querySelectorAll("main .cls.done").length);
          check("live: up-next card count", d4.querySelectorAll("main .cls.now").length === (P1_FRONTIER_NUM ? 1 : 0), "got " + d4.querySelectorAll("main .cls.now").length);
          if (P1_FRONTIER_NUM){
            const nowCard = d4.querySelector("main .cls.now");
            check("live: up-next moved to expected class", !!nowCard && nowCard.querySelector(".cnum").textContent === P1_FRONTIER_NUM, (nowCard && nowCard.querySelector(".cnum").textContent) + " vs " + P1_FRONTIER_NUM);
          }
          const upd4 = d4.getElementById("updatedLine");
          check("live: updated line shows fetched asof", /^Updated Aug 25, 2026 · 11:00 AM$/.test(upd4.textContent), upd4 ? upd4.textContent : "missing");

          // check 2: user state survives a re-render (selection + open cards)
          // open a trainer-matched card while no filter is active (pure openCls state)
          const SCN = DATA.classes.find(c => c.e.some(e => norm(e[3]) === tNorm)).n;
          const cardN = [...d4.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCN);
          check("live: trainer class card present pre-filter", !!cardN);
          cardN.querySelector(".cls-head").click();
          // apply the trainer selection
          const gT4 = d4.querySelectorAll("#filters .fgroup")[0];
          const si4 = gT4.querySelector(".fsearch");
          si4.value = "stachowski";
          si4.dispatchEvent(new w4.Event("input", { bubbles: true }));
          const target4 = [...gT4.querySelectorAll(".frow input")].find(cb => cb.closest(".frow").querySelector("label").textContent === TRAINER);
          if (target4) target4.click();
          check("live: selection chip shown", !!(gT4.querySelector(".chip") && gT4.querySelector(".chip").textContent.includes(TRAINER)));
          // context mode: muted cards show and never auto-open, which isolates
          // openCls persistence (matched cards auto-open and would confound it)
          d4.getElementById("contextBtn").click();
          const muted4 = d4.querySelector("main .cls.muted");
          check("live: context shows muted classes", !!muted4);
          const MNUM = muted4.querySelector(".cnum").textContent;
          muted4.querySelector(".cls-head").click();
          // serve one more update: settle the next frontier class
          const p2 = JSON.parse(JSON.stringify(w4.__live.current));
          const f2 = p2.classes.find(c => c.n === P1_FRONTIER_NUM);
          if (f2 && f2.e.length) f2.e[0][6] = "1";
          p2.asof = "2026-08-25 11:05";
          w4.__live.current = p2;
          await sleep(200);
          const P2 = w4.__live.current;
          const P2_FRONTIER = orderedClassesOf(P2.classes).find(c => !isDone(c));
          const P2_FRONTIER_NUM = P2_FRONTIER ? P2_FRONTIER.n : null;
          check("live: selection keeps its chip after re-render", !!(gT4.querySelector(".chip") && gT4.querySelector(".chip").textContent.includes(TRAINER)));
          check("live: context still shows all classes after re-render", d4.querySelectorAll("main .cls").length === TOTAL, "got " + d4.querySelectorAll("main .cls").length);
          const cardNb = [...d4.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCN);
          check("live: opened matched card stays open", !!cardNb && cardNb.classList.contains("open"));
          const mutedNb = [...d4.querySelectorAll("main .cls.muted")].find(x => x.querySelector(".cnum").textContent === MNUM);
          check("live: opened muted card stays open (openCls survives)", !!mutedNb && mutedNb.classList.contains("open"));
          const nowCard2 = d4.querySelector("main .cls.now");
          check("live: up-next reflects new data", !P2_FRONTIER_NUM ? !nowCard2 : (!!nowCard2 && nowCard2.querySelector(".cnum").textContent === P2_FRONTIER_NUM), (nowCard2 && nowCard2.querySelector(".cnum").textContent) + " vs " + P2_FRONTIER_NUM);
          // back to the filtered view: the count now follows the new data
          d4.getElementById("contextBtn").click();
          const P2_MATCHED = P2.classes.filter(c => c.e.some(e => norm(e[3]) === tNorm)).length;
          const P2_FRONTIER_MATCHED = P2_FRONTIER ? P2_FRONTIER.e.some(e => norm(e[3]) === tNorm) : false;
          const P2_FILTERED = P2_MATCHED + (P2_FRONTIER_NUM && !P2_FRONTIER_MATCHED ? 1 : 0);
          check("live: filtered count follows new data", d4.querySelectorAll("main .cls").length === P2_FILTERED, "got " + d4.querySelectorAll("main .cls").length + " vs " + P2_FILTERED);

          // check 3: an unchanged payload does not re-render (node identity)
          const firstChild = d4.querySelector("#schedule").firstChild;
          await sleep(150);
          check("live: unchanged payload does not re-render", d4.querySelector("#schedule").firstChild === firstChild);

          // check 4: repeated failures mark the line, recovery clears it
          w4.__live.fail = true;
          await sleep(250);
          check("live: 3+ failures show not-updating marker", upd4.textContent.endsWith(" · not updating"), upd4.textContent);
          w4.__live.fail = false;
          await sleep(150);
          check("live: recovery clears marker", !upd4.textContent.includes("not updating"), upd4.textContent);

          console.log("\n" + (checks - failures) + "/" + checks + " checks passed" + (failures ? "  —  " + failures + " FAILURES" : "  —  ALL TESTS PASSED"));
          process.exit(failures ? 1 : 0);
        })();
```

Remove the old `console.log(...)` + `process.exit(...)` that followed the mobile checks (they are now the last lines of the async IIFE above). Keep the closing `}, 300);` braces exactly as before (the live section lives inside the existing dom3 timeout).

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix tests test`
Expected: the existing checks pass; the new `live:` checks FAIL (no poller yet — `updated line shows fetched asof` shows the embedded asof, done count unchanged). The process still exits via the IIFE.

- [ ] **Step 3: Implement in the `build_page.py` template**

a) Markup (line 168): `<div class="updated" id="updatedLine"></div>` →

```html
  <div class="updated" id="updatedLine"><span id="updatedText"></span></div>
```

b) CSS (line 71): `header .updated { color: var(--muted); font-size: 12px; margin-top: 2px; }` →

```css
header .updated { color: var(--muted); font-size: 12px; margin-top: 2px; display: flex; align-items: center; gap: 6px; }
```

c) New JS block immediately before `// ---- init` (after the toast function):

```js
// ---- live update (polls payload.json; the embedded DATA is first paint)
const POLL_MS = (typeof window.__POLL_MS === "number") ? window.__POLL_MS : 30000;
const pollingActive = typeof fetch === "function" && location.protocol.indexOf("http") === 0;
let liveRaw = JSON.stringify(DATA);
let pollsFailed = 0, pollInFlight = false, pollTimer = null;
// asof is passed explicitly: while a re-render is focus-deferred, DATA is
// still the old payload but the header must show the newest asof
function setUpdatedLine(asof, stale){
  $("#updatedText").textContent = "Updated " + fmtAsof(asof) + (stale ? " · not updating" : "");
}
function restoreSearch(){
  const keys = ["trainer", "rider", "horse", "owner", "division"];
  document.querySelectorAll("#filters .fsearch").forEach((inp, i) => { inp.value = search[keys[i]] || ""; });
}
function applyDataUpdate(p){
  liveRaw = JSON.stringify(p);
  DATA = p;
  buildIndexes();
  renderFilters();
  restoreSearch();
  renderSchedule();
  setUpdatedLine(DATA.asof, false);
}
async function poll(){
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    const r = await fetch("payload.json?ts=" + Date.now(), {cache: "no-store"});
    if (!r.ok) throw new Error("http " + r.status);
    const p = await r.json();
    if (!p || !Array.isArray(p.classes)) throw new Error("bad payload");
    pollsFailed = 0;
    const raw = JSON.stringify(p);
    if (raw !== liveRaw) applyDataUpdate(p);
    else setUpdatedLine(DATA.asof, false);
  } catch (e) {
    pollsFailed++;
    if (pollsFailed >= 3) setUpdatedLine(DATA.asof, true);
  } finally {
    pollInFlight = false;
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, POLL_MS);
  }
}
```

d) Init tail (lines 572-580): `$("#updatedLine").textContent = "Updated " + fmtAsof(DATA.asof);` → `setUpdatedLine(DATA.asof, false);` and, after the final `if (src) toast("Restored your selection");`, add:

```js
if (pollingActive) pollTimer = setTimeout(poll, POLL_MS);
```

- [ ] **Step 4: Rebuild and run the suite**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: all checks pass (old 76 + new live checks). Then also `python3 tests/test_ui_only.py` (the `let`/span change must round-trip).

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js
git commit -m "Page polls payload.json every 30s and re-renders on change; Updated line goes live; no-op polls leave the DOM untouched"
```

---

### Task 5: Countdown ring (TDD)

**Files:**
- Modify: `refresh/build_page.py` template — `#updatedLine` markup (add SVG), CSS (ring styles, print hide-list), live-update JS block (ring consts + `ringReset()`, `setUpdatedLine` ring display, `poll()` finally, init)

**Interfaces:**
- Consumes: `pollingActive`, `POLL_MS`, `poll()` (Task 4).
- Produces: the visible countdown. No interface for Task 6.

- [ ] **Step 1: Write the failing tests** — in `tests/test.js`:

a) In the initial-render section (right after the `updated line formatted` check), add:

```js
  check("no ring when polling is inactive", !doc.querySelector(".ring"), "ring present in plain dom");
```

b) In the live section, extend check 4 and add check 5. Replace the Task 4 check-4 block's tail and insert before the summary — final state of that region:

```js
          // check 4: repeated failures mark the line (+ hide the ring), recovery clears
          w4.__live.fail = true;
          await sleep(250);
          check("live: 3+ failures show not-updating marker", upd4.textContent.endsWith(" · not updating"), upd4.textContent);
          const ringFg5 = d4.querySelector(".ring-fg");
          check("live: ring hidden while not updating", !!ringFg5 && ringFg5.style.display === "none", ringFg5 ? ringFg5.style.display : "missing");
          w4.__live.fail = false;
          await sleep(150);
          check("live: recovery clears marker", !upd4.textContent.includes("not updating"), upd4.textContent);
          check("live: recovery shows ring again", !!ringFg5 && ringFg5.style.display === "");

          // check 5: ring present, dasharray = circumference, transition spans one cycle
          check("live: ring present when polling", !!ringFg5);
          const dash = ringFg5 ? ringFg5.style.strokeDasharray : "";
          check("live: ring dasharray = circumference (2π·6 ≈ 37.7)", Math.abs(parseFloat(dash) - 2 * Math.PI * 6) < 0.1, dash);
          check("live: ring transition spans one poll cycle", !!ringFg5 && ringFg5.style.transition.indexOf("50ms") !== -1, ringFg5 ? ringFg5.style.transition : "missing");
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix tests test`
Expected: the live ring checks FAIL (`live: ring present when polling`, `ring hidden while not updating`, dasharray/transition — the SVG and ring JS don't exist yet); `no ring when polling is inactive` passes trivially (no ring element at all).

- [ ] **Step 3: Implement in the template**

a) Markup — the Task 4 line becomes:

```html
  <div class="updated" id="updatedLine">
    <svg class="ring" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <circle class="ring-track" cx="7" cy="7" r="6"></circle>
      <circle class="ring-fg" cx="7" cy="7" r="6"></circle>
    </svg>
    <span id="updatedText"></span>
  </div>
```

b) CSS — after the `header .updated { ... }` rule add:

```css
.ring { flex: none; transform: rotate(-90deg); }
.ring circle { fill: none; stroke-width: 2.5; }
.ring-track { stroke: var(--line); }
.ring-fg { stroke: var(--accent); stroke-linecap: round; }
```

and in `@media print`, add `.ring` to the hide-list:

```css
  header .actions, aside, #toast, .chev, .dchev, .call, .ring { display: none !important; }
```

c) Live-update JS block:

- After `let pollsFailed = 0, pollInFlight = false, pollTimer = null;` add:

```js
const RING_C = 2 * Math.PI * 6;
const ringFg = document.querySelector(".ring-fg");
if (ringFg){
  ringFg.style.strokeDasharray = RING_C;
  ringFg.style.strokeDashoffset = RING_C;
}
function ringReset(){
  if (!ringFg) return;
  ringFg.style.transition = "none";
  ringFg.style.strokeDashoffset = RING_C;
  void ringFg.getBoundingClientRect();
  ringFg.style.transition = "stroke-dashoffset " + POLL_MS + "ms linear";
  ringFg.style.strokeDashoffset = 0;
}
```

- `setUpdatedLine` becomes (signature from Task 4 unchanged):

```js
function setUpdatedLine(asof, stale){
  $("#updatedText").textContent = "Updated " + fmtAsof(asof) + (stale ? " · not updating" : "");
  if (ringFg) ringFg.style.display = stale ? "none" : "";
}
```

- In `poll()`'s `finally`, before `clearTimeout(pollTimer);` add `ringReset();`.

- The init tail's `if (pollingActive) ...` becomes:

```js
if (pollingActive) {
  ringReset();
  pollTimer = setTimeout(poll, POLL_MS);
} else {
  const ring = document.querySelector(".ring");
  if (ring) ring.remove();
}
```

(When the ring is removed, `ringFg` still references the detached node; style writes on it are no-ops.)

- [ ] **Step 4: Rebuild and run the suite**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: all pass, including `no ring when polling is inactive` (plain dom: no `fetch` → removed at init) and the live ring checks.

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js
git commit -m "Header countdown ring: CSS-transition-animated SVG fills over each 30s poll cycle; hidden while not updating, absent when polling is inactive"
```

---

### Task 6: No view bounce — scroll, focus deferral, day seeding (TDD)

**Files:**
- Modify: `refresh/build_page.py` template — `renderSchedule()` (tag day elements), live-update JS block (`applyDataUpdate`, `poll`, new `focusInBody`/`flushPending`, `focusout` listener, `visibilitychange` listener)
- Modify: `tests/test.js` (live section: checks 6, 7, 8)

**Interfaces:**
- Consumes: `applyDataUpdate()`, `poll()`, `pendingPayload` (Task 4/5), `dayState`, `renderSchedule()`.
- Produces: the final poller/render behavior. No later tasks depend on code interfaces (Task 7 is docs).

- [ ] **Step 1: Write the failing tests** — in the live section of `tests/test.js`, insert before the summary line (`console.log("\n" + ...`):

```js
          // check 6: window scroll restored after re-render
          check("live: scroll position restored after re-render", w4.__scrollCalls.some(c => c[0] === 0 && c[1] === 123), JSON.stringify(w4.__scrollCalls));

          // check 7: re-render deferred while a control has focus
          // (in filtered view the settled frontier may be filtered out, so
          //  assert via the up-next pill, not the done count)
          if (P2_FRONTIER_NUM){
            const si4b = d4.querySelectorAll("#filters .fgroup")[0].querySelector(".fsearch");
            si4b.focus();
            check("live: search input can take focus", d4.activeElement === si4b);
            const firstChildBefore = d4.querySelector("#schedule").firstChild;
            const daysBefore = [...d4.querySelectorAll("main .day")].map(el => el.classList.contains("collapsed"));
            // serve one more update: settle the next frontier class
            const p3 = JSON.parse(JSON.stringify(w4.__live.current));
            const f3 = p3.classes.find(c => c.n === P2_FRONTIER_NUM);
            if (f3 && f3.e.length) f3.e[0][6] = "1";
            p3.asof = "2026-08-25 11:10";
            const P3_FRONTIER = orderedClassesOf(p3.classes).find(c => !isDone(c));
            const P3_FRONTIER_NUM = P3_FRONTIER ? P3_FRONTIER.n : null;
            w4.__live.current = p3;
            await sleep(200);
            const nowWhileDeferred = d4.querySelector("main .cls.now");
            check("live: re-render deferred while focused (body unchanged)", d4.querySelector("#schedule").firstChild === firstChildBefore);
            check("live: body still shows old frontier while deferred", !!nowWhileDeferred && nowWhileDeferred.querySelector(".cnum").textContent === P2_FRONTIER_NUM, (nowWhileDeferred && nowWhileDeferred.querySelector(".cnum").textContent) + " vs " + P2_FRONTIER_NUM);
            check("live: header still shows newest asof while deferred", /^Updated Aug 25, 2026 · 11:10 AM/.test(upd4.textContent), upd4.textContent);
            si4b.blur();
            await sleep(100);
            const nowAfter = d4.querySelector("main .cls.now");
            check("live: blur applies the deferred update", d4.querySelector("#schedule").firstChild !== firstChildBefore);
            check("live: up-next advanced after deferred apply", !P3_FRONTIER_NUM ? !nowAfter : (!!nowAfter && nowAfter.querySelector(".cnum").textContent === P3_FRONTIER_NUM), (nowAfter && nowAfter.querySelector(".cnum").textContent) + " vs " + P3_FRONTIER_NUM);
            const gT4b = d4.querySelectorAll("#filters .fgroup")[0];
            check("live: selection survives the deferred re-render", !!(gT4b.querySelector(".chip") && gT4b.querySelector(".chip").textContent.includes(TRAINER)));
            // check 8: day collapse state survives the re-render
            const daysAfter = [...d4.querySelectorAll("main .day")].map(el => el.classList.contains("collapsed"));
            check("live: day collapse state survives re-render", JSON.stringify(daysAfter) === JSON.stringify(daysBefore), JSON.stringify(daysAfter) + " vs " + JSON.stringify(daysBefore));
          }
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix tests test`
Expected: `live: scroll position restored after re-render` FAILS (no `scrollTo` call — `__scrollCalls` is empty) and the focus-deferral checks FAIL (the body re-renders immediately while focused: the first child changes and the up-next pill advances during the "deferred" window).

- [ ] **Step 3: Implement in the template**

a) `renderSchedule()`: after `const dEl = el("section","day");` add:

```js
    dEl.dataset.day = d.day;
```

b) Replace `applyDataUpdate` with the view-preserving version:

```js
function applyDataUpdate(p){
  liveRaw = JSON.stringify(p);
  const x = window.scrollX || 0, y = window.scrollY || 0;
  const aside = $("#filters");
  const asy = aside ? (aside.scrollTop || 0) : 0;
  for (const dEl of document.querySelectorAll("#schedule .day")){
    const key = dEl.dataset.day;
    if (key != null && dayState[key] == null) dayState[key] = dEl.classList.contains("collapsed");
  }
  DATA = p;
  buildIndexes();
  renderFilters();
  restoreSearch();
  renderSchedule();
  setUpdatedLine(false);
  if (aside) aside.scrollTop = asy;
  if (x || y) window.scrollTo(x, y);
}
```

c) In the live-update block, add (after `applyDataUpdate`):

```js
let pendingPayload = null;
function focusInBody(){
  const a = document.activeElement;
  return !!a && a !== document.body &&
    ($("#filters").contains(a) || $("#schedule").contains(a));
}
function flushPending(){
  if (pendingPayload && !focusInBody()){
    const p = pendingPayload;
    pendingPayload = null;
    applyDataUpdate(p);
  }
}
document.addEventListener("focusout", flushPending);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { clearTimeout(pollTimer); }
  else { clearTimeout(pollTimer); poll(); }
});
```

d) In `poll()`: first line after the function brace becomes `flushPending();` (before the `pollInFlight` guard); and the changed-data branch becomes:

```js
    if (raw !== liveRaw){
      if (focusInBody()){
        pendingPayload = p;
        setUpdatedLine(p.asof, false);
      } else {
        applyDataUpdate(p);
      }
    } else {
      setUpdatedLine(DATA.asof, false);
    }
```

- [ ] **Step 4: Rebuild and run the full suite**

Run: `python3 refresh/build_page.py && npm --prefix tests test`
Expected: all checks pass (all live checks + all pre-existing checks — the plain dom never polls, so deferral/scroll code is inert there).

- [ ] **Step 5: Commit**

```bash
git add refresh/build_page.py tests/test.js
git commit -m "No view bounce on live updates: restore window/aside scroll, defer re-render while a control has focus (header stays live), freeze day-collapse defaults after first render"
```

---

### Task 7: Docs + final verification

**Files:**
- Modify: `AGENTS.md`, `README.md`, `refresh/README.md`

**Interfaces:**
- Consumes: everything (describes the finished feature).
- Produces: none.

- [ ] **Step 1: `AGENTS.md`**

- "## What this is" — after the sentence ending "...served by GitHub Pages from the `main` branch." add:
  `The page shell polls the published `payload.json` every 30 s and re-renders in place (no manual refresh); the embedded snapshot in `index.html` is the first-paint/offline fallback.`
- Commands section:
  - `python3 refresh/build_page.py               # data -> index.html (asof only changes if the data changed)` → `python3 refresh/build_page.py               # data -> index.html + payload.json (asof only changes if the data changed)`
  - `git add index.html && git commit -m "Refresh entries <date>" && git push` → `git add index.html payload.json && git commit -m "Refresh entries <date>" && git push`
  - Add after the `python3 tests/test_frontier.py` line: `python3 tests/test_payload.py              # verifies payload.json follows the asof policy`
- "## Auto-refresh (cron)" — `rebuilds `index.html`, and commits + pushes **only when the data actually changed**` → `rebuilds `index.html` + `payload.json`, and commits + pushes **only when the data actually changed**`; and `so `git diff` against HEAD is the no-change signal` stays as-is.
- "## Architecture" — after the "The payload is embedded..." bullet add:
  `- `payload.json` (repo root) is the same compact payload as a committed file, served by Pages; the page fetches it every 30 s (`?ts=` + `cache: "no-store"`) and re-renders when it changes. Re-renders preserve the user's view (selection, open cards, day collapse, scroll, focus — a re-render is deferred while a control has focus); a ring in the header counts down to the next check.`
  and change the asof-policy bullet's opening to `**asof policy: the "Updated" stamp changes only when the data actually changes** (both in `index.html` and `payload.json`).`
- "## Publishing" — `index.html` is ~380 KB and must go through `git push`.` → `index.html` (~385 KB) and `payload.json` (~370 KB) must go through `git push`.` and the following sentence becomes `The GitHub MCP tools take file contents inline and truncate above ~40 KB — do not attempt to push either file through them.`
- "## Verification" — in the jsdom paragraph, `(76 checks: filters, context/done toggles, day collapse, per-class show-all, entry numbers, persistence, mobile default)` → `(filters, context/done toggles, day collapse, per-class show-all, entry numbers, persistence, mobile default, live-update polling)`.
- "## Tips for AI Agents" — `The payload is one line: the embedded data in `index.html` is a single long line by design.` → `The payload is one line: the embedded data in `index.html` (and `payload.json`) is a single long line by design.`

- [ ] **Step 2: `README.md`**

- "Using the page" — after the print bullet add:
  `- The page checks for new results about every 30 seconds and updates in place — the small ring next to the "Updated" time fills as the next check approaches, and the timestamp moves when new data lands. No need to refresh.`
- Replace `The data snapshot date is in the page footer. Entries and placings change during the show — refresh it before the day your riders go (below).` with `Entries and placings change during the show — the page picks them up on its own (the "Updated" time in the header tells you how fresh the data is).`
- "## What's in the repo" — replace `One self-contained HTML file — no server, no dependencies, works offline. All data (210 classes, 3,471 entries at first snapshot) is embedded in the page itself.` with `Two generated files, no server, no dependencies. `index.html` is the page shell with an embedded data snapshot (first paint + offline fallback); `payload.json` is the live data the shell re-fetches about every 30 s while the page is open.`
- File table — after the `index.html` row add: `| `payload.json` | Live data the page polls every ~30 s. **Generated — don't edit by hand.** |`
- "## Refreshing the data during the show" — `Then commit `index.html` and push — GitHub Pages picks it up within a couple of minutes.` → `Then commit `index.html` and `payload.json` and push — GitHub Pages picks them up within a couple of minutes (cron does this automatically every 8 min).`

- [ ] **Step 3: `refresh/README.md`**

- Line 3: `` `../index.html` is a static snapshot (see "generated" date in the page footer). `` → `` `../index.html` is the page shell with an embedded data snapshot; the page polls `../payload.json` (same directory, served by GitHub Pages) about every 30 s for live data. ``
- In the bullet list, add after the `data.json` bullet: `- `payload.json` (repo root) is the compact published payload the page polls. A regular `build_page.py` writes it; `--ui-only` never touches it; cron commits it with `index.html`.`
- The asof paragraph: `...and `--ui-only` never touches it.` → `...and `--ui-only` never touches it. The same policy applies to `payload.json`.`
- Cron paragraph: `rebuilds `index.html`, and commits/pushes only when the data changed` → `rebuilds `index.html` + `payload.json`, and commits/pushes only when the data changed`.

- [ ] **Step 4: Final verification (full suite + payload sanity)**

Run:
```bash
python3 refresh/build_page.py
npm --prefix tests test
python3 tests/test_ui_only.py
python3 tests/test_asof.py
python3 tests/test_frontier.py
python3 tests/test_payload.py
python3 - <<'EOF'
import re, json
s = open('index.html').read()
emb = re.search(r'^(?:const|let) DATA = (\{.*\});\s*$', s, re.M).group(1)
plj = open('payload.json').read().rstrip("\n")
print("classes:", len(re.findall(r'"n":"', s)))
print("entries:", len(re.findall(r'\["\d+","', s)))
print("asof:", json.loads(emb)["asof"])
print("payload.json == embedded:", plj == emb)
EOF
```
Expected: every suite ALL PASS / ALL TESTS PASSED; sanity prints real class/entry counts (≥ 210 / ≥ 3471) and `payload.json == embedded: True`.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md refresh/README.md
git commit -m "Docs: live-update behavior, payload.json artifact, and updated commands/publishing/verification"
```

- [ ] **Step 6: (User decision) Deploy**

The feature ships when the accumulated commits (Tasks 1-7) are pushed; the rebuilt `index.html` + `payload.json` publish within 1-2 min. Old non-polling pages and new pages coexist; the cron keeps running. Push only when the user asks.

---

## Self-review

- **Spec coverage:** Section 1 → Tasks 1, 2. Section 2 data binding → Task 3; poller → Task 4; no-view-bounce → Task 6; updated line + ring → Tasks 4, 5. Section 3 docs → Task 7. Section 4: `test.js` live section (checks 1-8) → Tasks 4, 5, 6; `test_payload.py` → Task 1; regex touch-ups → Tasks 1, 3; verification → Task 7 Step 4. Non-goals respected (no backend, no toast, no manual button, no partial diff).
- **Placeholder scan:** none — every step carries its code or exact command.
- **Type/name consistency:** `applyDataUpdate`, `setUpdatedLine(asof, stale)`, `restoreSearch`, `focusInBody`, `flushPending`, `ringReset`, `pollingActive`, `POLL_MS`, `pendingPayload`, `liveRaw`, `buildIndexes`, `#updatedText`, `.ring-fg`, `dEl.dataset.day`, `w.__POLL_MS`, `w.__live`, `w.__scrollCalls` — defined once (tasks 4/5/6) and used consistently by the tests; `orderedClassesOf`/`orderedClasses` introduced in Task 4 Step 1 and used by its own section.
- **Known subtleties handled:** `setUpdatedLine` takes the asof explicitly because the focus-deferred path must show the newest asof while `DATA` is still the old payload (Task 6); check 2 isolates `openCls` persistence through context-mode muted cards (matched cards auto-open and would confound it); check 7 asserts via the up-next pill rather than the done count, because a settled non-matching frontier is filtered out of the filtered view; jsdom does not run CSS transitions, so the ring check asserts the transition string, not the animated offset (verified: jsdom supports `style.strokeDasharray`/`strokeDashoffset`, `scrollY` is overrideable, `focus()`/`blur()` track `activeElement`).
