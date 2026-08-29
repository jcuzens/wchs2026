# AGENTS.md

Guidance for AI agents working in this repository.

## Memory MCP

If the memory MCP is available, use it to persist and retrieve project knowledge
across sessions. Store key facts about architecture, conventions, tooling, and
decisions. Query it before answering questions about the project to recall
context from prior conversations.

Discipline:
- **Read before answering status/planning questions** (e.g. "where are the
  milestones?") — search the graph first; do not re-derive state from the repo
  alone.
- **Write when state changes** — milestone done/deferred, decision made,
  convention or architecture changed: update the graph in the same session.
- **Prune stale entries** — delete superseded observations instead of
  accumulating contradictions.
- Example: the `milestone roadmap` entity records the roadmap location
  (README.md) and per-version status.

## Sequential Thinking MCP

For complex, multi-step problems — architecture decisions, debugging intricate
bugs, designing systems — use the sequential thinking tool to break reasoning
into steps. It supports revision, branching, hypothesis generation, and
verification. Use when the problem doesn't have an obvious linear solution or
when you need to explore and refine your thinking iteratively.

## Skill Discipline

Before ANY action — exploring files, answering questions, writing code — check
which skill applies from the available skills list. Invoke it and follow it
exactly. Do not skip this step.

| Task type | Skill |
|---|---|
| Building features, creating something new | `brainstorming` |
| Fixing bugs, test failures, unexpected behavior | `systematic-debugging` |
| Implementing features or bugfixes | `test-driven-development` |
| Approved spec needs execution steps | `writing-plans` |
| Plan ready with independent tasks | `subagent-driven-development` |

## What this is

A static, personal schedule site for WCHS 2026 (Aug 22–29, 2026, Kentucky
State Fair). The site is three generated files — `index.html` (page shell),
`payload.json` (live data) and `check.json` (tiny poll probe: asof + data
hash) — served by GitHub Pages from the `main`
branch. The page shell polls the
published `check.json` every 30 s and only fetches the full
`payload.json` when the hash changed; it then re-renders in place (no manual
refresh); the embedded snapshot in `index.html` is the first-paint/offline
fallback. `refresh/` is the pipeline
that regenerates them from live show data. README.md has the user-facing
story.

## Commands

Run from the repo root:

```bash
refresh/fetch_entries.sh                    # resumable; uses refresh/jar.txt session cookie
python3 refresh/class_list.py refresh/entries/<page>.html   # refresh classes.json from the live master grid (rc 3 = changed)
python3 refresh/parse_entries.py
python3 refresh/build_page.py               # data -> index.html + payload.json + check.json (asof only changes if the data changed)
python3 refresh/build_page.py --ui-only     # UI/template change: reuses the payload (and asof) already in index.html
python3 refresh/fetch_live.py               # live scores fetch -> refresh/live.json
python3 refresh/parse_live.py               # fold live.json into refresh/live_cache.json
python3 refresh/fetch_scorecards.py         # judge scorecards index (Drive) -> refresh/scorecards.json
bash refresh/refresh_upcoming.sh               # one 4-hour scratch-refresh cycle, manually (cron: 0 */4 * * *)
npm --prefix tests install                  # once; jsdom dev-only dependency
npm --prefix tests test                     # page smoke suite (runs against the built index.html)
python3 tests/test_ui_only.py               # verifies --ui-only preserves the payload
python3 tests/test_asof.py                  # verifies the asof only changes when the data changes
python3 tests/test_frontier.py              # frontier/lookahead selection (cron refresh)
python3 tests/test_predict.py               # predicted-pace model (synthetic sessions)
python3 tests/test_payload.py               # verifies payload.json follows the asof policy
python3 tests/test_check.py                 # verifies check.json follows the asof policy
python3 tests/test_live.py                  # live protocol/parse/merge tests (fixtures)
python3 tests/test_class_list.py            # live class list: master-grid parse + update semantics
python3 tests/test_parse_entries.py         # entry-page parse (page label wins, section slot inheritance)
python3 tests/test_scorecards.py            # scorecards: Drive folder parse + payload card merge (fixtures)
bash refresh/refresh_cron.sh                # one full cron cycle, manually
git add index.html payload.json check.json && git commit -m "Refresh entries <date>" && git push
```

`build_page.py` resolves its inputs and output relative to its own file
location, so `cd refresh && python3 build_page.py` is equivalent.

## Auto-refresh (cron)

`refresh/refresh_cron.sh` runs on cron every 8 minutes
(`*/8 * * * * /path/to/repo/refresh/refresh_cron.sh`). Each run:

- refreshes the **live class list** (`class_list.py` on the newest fetched
  page): the master grid on any class page is the show's current class
  universe — split sections (89.1/89.2) are separate classes, each with
  its own ClassGUID, and classes can be added mid-show. It rewrites
  `classes.json` only when the list changed (rc 3), in which case the
  resumable fetcher downloads the new pages;
- decides what to fetch: if `refresh/entries/` is missing/empty it does the
  full resumable fetch; otherwise it re-fetches the **results frontier** —
  the first class in schedule order without placings, walking forward class
  by class until a class has no results yet — plus the next 8 schedule
  classes (lookahead) to keep upcoming entry lists fresh;
- also fetches the **live scores** grid (one callback per class row;
  placings land minutes after scoring) into `refresh/live.json` and folds
  it into the accumulating `refresh/live_cache.json`; a live failure is a
  warning only — the page degrades to official-only data;
- rebuilds `index.html` + `payload.json` + `check.json`, and commits + pushes **only
  when the data actually changed** (the asof policy makes an unchanged rebuild
  byte-identical, so `git diff` against HEAD is the no-change signal).

The frontier needs no state file: "done" is the page's own rule (a class has
a place on any entry), read from the payload already embedded in
`index.html`. A class whose session started 4h ago with no results is
presumed skipped (otherwise a void class would stall the frontier). One run
at a time (flock); a run that finds the previous one still going skips. All
output goes to `refresh/cron.log` (git-ignored; it contains `git push`
output — masked by git, but never copy log lines containing URLs). Safety:
the run aborts before publishing if the parsed entry count drops by more
than half, and the fetcher only replaces a page when the new one looks
valid (> 50 KB or a legit "No entries" page), so a dead session cookie
cannot clobber good data.

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
never run at once. Both crons fire in the same second at every 4-hour
boundary (4h marks are multiples of 8 min), so the upcoming job waits up
to 3 min (`flock -w 180`) for the running job to finish instead of
skipping — without that wait its scorecard pass was being skipped at
every boundary; the 8-minute job still skips fast. It also refreshes the
**judge scorecard index** (`fetch_scorecards.py`), so this run publishes
when a new scorecard PDF lands even if nothing else changed (no early
exit when all classes are settled).

## Architecture

- `index.html` is **generated, never hand-edited**. All page markup, CSS,
  and JS live in the raw-string template (`html = r"""..."""`) inside
  `refresh/build_page.py`. Change the template, rebuild, commit.
- The payload is embedded by replacing the `__PAYLOAD__` placeholder with
  compact JSON: `{"asof":"<local time>","h":"<sha1-12 of the classes
  JSON>","classes":[...]}`.
- `payload.json` (repo root) is the same compact payload as a committed
  file, served by Pages. The page polls the tiny `check.json` (repo root,
  ~50 B: `{"asof":...,"h":...}`) every 30 s (`?ts=` + `cache: "no-store"`
  — the buster defeats Pages' 600 s edge cache; ETag/304 revalidation is
  not an option because freshness must stay ~30 s) and fetches the full
  `payload.json` only when its `h` differs from the page's current one;
  the embedded snapshot carries the same `h`, so first paint needs no
  fetch. Re-renders preserve the user's view (selection, open cards, day
  collapse, scroll, focus — a re-render is deferred while a control has
  focus); a ring in the header counts down to the next check.
- Data flow: `classes.json` + `schedule.json` + `entries/*.html`
  → `parse_entries.py` → `data.json` → `build_page.py` →
  `index.html` + `payload.json` + `check.json`.
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
- **Scratch entries:** withdrawn entries sit on the same ClassResults.aspx
  pages the pipeline already fetches, marked on the `<tr>` with
  `background-color:LightPink;…text-decoration: line-through`.
  `parse_entries.py` flags them, `build_page.py` emits a per-class
  `"sc": [entry numbers]` (only when non-empty), and the page renders
  those rows with a pink background + strikethrough. No separate source
  or fetcher — the 4-hour upcoming refresh (above) is the only new
  moving part.
- **Judge scorecards:** the show posts one judge scorecard PDF per class
  in a public Google Drive folder, named `CLASS N.pdf` (split sections
  included, e.g. `10.1`). The judges' names drift from the live class
  list: `CLASS N-K.pdf` (hyphen) for plain classes, and a plain
  `CLASS N.pdf` for a class whose parent number a later split removed
  (e.g. `CLASS 104.pdf` for section `104.1`). The fetcher keeps such
  keys raw; `build_page.py` resolves them against the current classes
  before stamping — `N-K` → section `N.K` if it exists, else plain `N`;
  plain `N` → its surviving section (`.1` first, else the only one);
  exact numbers always win. `fetch_scorecards.py` lists the folder via the
  legacy **embeddedfolderview** endpoint (plain GET, no key or session;
  the main `/drive/folders/` page lazy-loads and only serves the first ~50
  rows in its initial HTML) — every entry is an
  `<a href="…/file/d/FILEID/view">` wrapping a `flip-entry-title` — into
  `refresh/scorecards.json`
  (`{"fetched":..., "cards": {"N": "FILEID"}}`); `build_page.py` stamps
  matching payload classes with `"card": "https://drive.google.com/file/d/<id>/view"`
  and the page renders a `scorecard ↗` chip in the class card header
  (a span with stopPropagation, since an `<a>` can't live inside the
  `<button>` head; it opens the Drive PDF viewer in a new tab). Refreshed
  by the 4-hour upcoming job; a fetch failure or a parse that finds zero
  cards never overwrites a good cache, so the page degrades to no chips.
- **Predicted pace:** `refresh/predict.py` is a pure per-session pace
  model (10.125 min/class — 13.5 cut 25% on 2026-08-26 after observed
  classes ran short — plus 45 min champion equitation, raised from 25 on
  2026-08-27 after the senior championship ran long; constants in that
  file). The session holding the newest live observation is the "hot"
  session, shifted so that class's predicted end matches it (positive
  shift capped at +180 min). The build stamps each payload class with
  `ps`/`pe` (UTC epoch seconds); the page evaluates "on now" / "up next" /
  "awaiting results" client-side on the user's clock and ticks every 60 s
  in place. **Official placings always beat the model.** The model never
  reads wall-clock time, so the asof policy is untouched.
- **Manual "here" pacing (client-only, no payload/build change):** every
  not-done class with a window renders a small `here` chip in its card
  header. Clicking it stores `{num, at}` in localStorage
  (`wchs2026.pin.v1`) and re-anchors that class's session: `pinShifts`
  computes a uniform ms shift of the pinned session's tail (the pin and
  every later class in the same day/per/time slot) so the pinned class
  starts at the click time `at` and the rest walks forward at the usual
  pace; the pinned class may even be one the model already passed
  ("awaiting results") — the whole tail goes back to it. The header
  "Reset pace" button clears the pin. The pin is **dropped automatically
  the moment any class at or after it (schedule order) has live or
  official placings** — `pinValidity` re-checks on every render/tick, so
  results always take over. All pin state is per-browser localStorage;
  it is never in the payload or URL, and none of it touches the asof
  policy. Pure helpers: `pinValidity`, `pinShifts`; the pace fns
  (`onNowCls`, `upNextCls`, `isPendingCls`, `classPill`) take an optional
  `shifts` map (null → the normal model).
- **asof policy: the "Updated" stamp changes only when the data
  actually changes** (in `index.html`, `payload.json` and `check.json`).
  The
  regular build compares the new `classes`
  against the payload already embedded in `index.html` and keeps the old
  `asof` when they're identical. `h` (and therefore `check.json`) is a
  pure function of the classes, so it follows the same policy. `--ui-only`
  re-embeds that same payload, so template/UI rebuilds never touch the
  stamp.
- `data.json`, `entries/`, `jar.txt`, `fetchlist.txt`, `refreshlist.txt`,
  `cron.log`, `cron.lock`, `live.json`, `live_cache.json`,
  `scorecards.json`, `tests/node_modules/` are git-ignored
  intermediates. Never commit them.
- **Class number is the join key** across all data sources. Sub-classes
  use `x.y` numbering (e.g. `45.1`) and inherit the parent's schedule
  slot. Some classes legitimately have zero entries — don't "fix" them.
- **Split sections are their own classes.** The show splits overloaded
  classes into `x.1`/`x.2` sections mid-show; each section is a real
  class with its own ClassGUID, entry page, card, and pace slot (the
  live scoreboard already used section numbers). The authoritative class
  list is the master grid (`grMaster`) on any class-results page, not a
  pre-show snapshot — `class_list.py` parses it and refreshes
  `classes.json` (exit 3 = changed). Each entry page carries its own
  `Class: N` label, which `parse_entries.py` trusts over the filename;
  section pages are plain `ClassResults.aspx?ClassGUID=<row key>` GETs.
  `predict.py` / `select_frontier.py` / the live merge already treat
  `x.y` as independent classes — no changes needed there.
- `schedule.json` only changes if the show re-times sessions.
  `classes.json` is now refreshed by the cron each run from the live
  master grid (rewritten only on change, committed with the rebuild);
  a mid-show class addition/split is picked up automatically.

## Secrets & credentials

- The `origin` remote URL embeds a GitHub PAT. **Never print
  `git remote -v`** and never copy the remote URL into files, logs, or
  chat output.
- `refresh/jar.txt` is a session cookie for the show website, created by
  the fetcher. It is git-ignored; if it ever shows in `git status`, do
  not stage it.
- This repo contains no other secrets. Don't add any.

## Publishing

- GitHub Pages deploys from `main` (root folder). A push to `main`
  publishes https://jcuzens.github.io/wchs2026/ within 1–2 minutes.
- `index.html` (~385 KB), `payload.json` (~370 KB) and `check.json`
  (50 B) are published together as one commit. The two big ones must go
  through `git push`. The GitHub MCP tools take file contents inline and
  truncate above ~40 KB — do not attempt to push either file through them.

## Verification

After any rebuild, sanity-check the embedded payload:

```bash
python3 - <<'EOF'
import re
s = open('index.html').read()
print("classes:", len(re.findall(r'"n":"', s)))      # 210 at first snapshot; grows during the show
print("entries:", len(re.findall(r'\["\d+","', s)))  # 3471 at first snapshot; grows during the show
print("asof:", re.search(r'"asof":"([^"]*)"', s).group(1))
import json
print("check:", open('check.json').read().strip())   # must match the asof above
EOF
```

The jsdom smoke suite (filters, context/done toggles, day collapse,
per-class show-all, entry numbers, persistence, mobile default,
live-update polling, manual "here" pacing) lives in `tests/test.js` and
runs against the freshly built `index.html`:

```bash
npm --prefix tests test
```

`tests/test_ui_only.py` verifies the `--ui-only` rebuild preserves the
embedded payload. The suite pins "now" to 2026-08-25 so day-collapse
defaults are deterministic. jsdom is a dev-only test dependency — the
page itself stays one dependency-free HTML file.

## Tips for AI Agents

**Generated file:** `index.html` is a build artifact — edit the template
in `refresh/build_page.py` instead, then rebuild.

**The raw string is load-bearing:** the template is `r"""..."""` on
purpose (it contains JS regex with backslashes). Don't remove the `r`
prefix or "clean up" escape sequences.

**The payload is one line:** the embedded data in `index.html` (and
`payload.json`) is a single long line by design. A huge `git diff` on
`index.html` usually means only the `asof` timestamp changed.

**Live protocol is reverse-engineered:** `refresh/fetch_live.py` drives a
DevExpress ASPxGridView callback protocol that is not documented anywhere;
the wire format (c0: prefix, KV/FR/CT/GB segments, envelope stateObject)
is in the spec above. If it breaks, nothing is lost — the fetch fails
softly and the page degrades to official-only. Don't "simplify" the
callback param; every segment is load-bearing.

**The pace anchor is the live cache's first-seen `at`**, not live.json's
"Updated Xm ago": the latter is a rounded relative string whose absolute
value jitters by a minute across fetches and would wobble the asof stamp on
every cron cycle. `fold_live_cache` keeps the first `at` per entry on
purpose — don't "fix" it to the latest.

**Don't print the remote:** `git remote -v` leaks the PAT embedded in
the origin URL.

**The master grid is the class universe:** every class page embeds the
show's full current class list (with ClassGUID row keys). If a class's
data looks wrong (e.g. "missing" entries), check whether it was split
into `x.1`/`x.2` sections — the old parent number no longer exists, and
the old parent page now serves section 1.

**Scratch marks are on the pages we already fetch:** the line-through
`<tr>` style on an entry page is the whole signal. Settled classes' pages
were re-fetched when their results posted, so they already contain all
their scratches; only unsettled classes need periodic re-fetching (the
4-hour upcoming refresh).

**Stay dependency-free:** the page must remain one HTML file with no
external requests, and the pipeline must remain Python stdlib + curl.

**The Drive folder is public but fragile:** `fetch_scorecards.py` parses
the human-rendered **embeddedfolderview** page (entry `<a href>` file id +
`flip-entry-title`), not an API — and only that endpoint lists ALL files
(the main folder page lazy-loads the first ~50). If Google changes the
markup, the parse finds zero cards and the fetcher keeps the old
`scorecards.json` (zero-card guard) — the page degrades to no chips; fix
the regexes, don't wipe the cache.
