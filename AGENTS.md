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
State Fair). The entire site is a single generated file, `index.html`,
served by GitHub Pages from the `main` branch. `refresh/` is the pipeline
that regenerates it from live show data. README.md has the user-facing
story.

## Commands

Run from the repo root:

```bash
refresh/fetch_entries.sh                    # resumable; uses refresh/jar.txt session cookie
python3 refresh/parse_entries.py
python3 refresh/build_page.py               # data -> index.html (asof only changes if the data changed)
python3 refresh/build_page.py --ui-only     # UI/template change: reuses the payload (and asof) already in index.html
npm --prefix tests install                  # once; jsdom dev-only dependency
npm --prefix tests test                     # page smoke suite (runs against the built index.html)
python3 tests/test_ui_only.py               # verifies --ui-only preserves the payload
python3 tests/test_asof.py                  # verifies the asof only changes when the data changes
git add index.html && git commit -m "Refresh entries <date>" && git push
```

`build_page.py` resolves its inputs and output relative to its own file
location, so `cd refresh && python3 build_page.py` is equivalent.

## Architecture

- `index.html` is **generated, never hand-edited**. All page markup, CSS,
  and JS live in the raw-string template (`html = r"""..."""`) inside
  `refresh/build_page.py`. Change the template, rebuild, commit.
- The payload is embedded by replacing the `__PAYLOAD__` placeholder with
  compact JSON: `{"asof":"<local time>","classes":[...]}`.
- Data flow: `classes.json` + `schedule.json` + `entries/*.html`
  → `parse_entries.py` → `data.json` → `build_page.py` → `index.html`.
- **asof policy: the "Updated" stamp changes only when the data
  actually changes.** The regular build compares the new `classes`
  against the payload already embedded in `index.html` and keeps the old
  `asof` when they're identical. `--ui-only` re-embeds that same payload,
  so template/UI rebuilds never touch the stamp.
- `data.json`, `entries/`, `jar.txt`, `fetchlist.txt`, `tests/node_modules/`
  are git-ignored intermediates. Never commit them.
- **Class number is the join key** across all data sources. Sub-classes
  use `x.y` numbering (e.g. `45.1`) and inherit the parent's schedule
  slot. Some classes legitimately have zero entries — don't "fix" them.
- `classes.json` / `schedule.json` only change if the show itself changes
  (classes added/removed, sessions re-timed). They are not part of a
  routine entry refresh.

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
- `index.html` is ~380 KB and must go through `git push`. The GitHub MCP
  tools take file contents inline and truncate above ~40 KB — do not
  attempt to push `index.html` through them.

## Verification

After any rebuild, sanity-check the embedded payload:

```bash
python3 - <<'EOF'
import re
s = open('index.html').read()
print("classes:", len(re.findall(r'"n":"', s)))      # 210
print("entries:", len(re.findall(r'\["\d+","', s)))  # 3471 at first snapshot; grows during the show
print("asof:", re.search(r'"asof":"([^"]*)"', s).group(1))
EOF
```

The jsdom smoke suite (64 checks: filters, context/done toggles, day
collapse, per-class show-all, persistence, mobile default) lives in
`tests/test.js` and runs against the freshly built `index.html`:

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

**The payload is one line:** the embedded data in `index.html` is a
single long line by design. A huge `git diff` on `index.html` usually
means only the `asof` timestamp changed.

**Don't print the remote:** `git remote -v` leaks the PAT embedded in
the origin URL.

**Stay dependency-free:** the page must remain one HTML file with no
external requests, and the pipeline must remain Python stdlib + curl.
