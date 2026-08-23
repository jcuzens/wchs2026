# AGENTS.md

Guidance for AI agents working in this repository.

## What this is

A static, personal schedule site for WCHS 2026 (Aug 22–29, 2026, Kentucky
State Fair). The entire site is a single generated file, `index.html`,
served by GitHub Pages from the `main` branch. `refresh/` is the pipeline
that regenerates it from live show data. README.md has the user-facing
story.

## Commands

Run from the repo root:

```bash
refresh/fetch_entries.sh       # resumable; uses refresh/jar.txt session cookie
python3 refresh/parse_entries.py
python3 refresh/build_page.py  # writes index.html at the repo root
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
- `data.json`, `entries/`, `jar.txt`, `fetchlist.txt` are git-ignored
  intermediates. Never commit them.
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

The page was also verified during development with a 20-assertion jsdom
smoke test (filters, lazy rendering, persistence, print view) that lived
in /tmp and was not committed.

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
