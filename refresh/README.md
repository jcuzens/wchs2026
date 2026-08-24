# Refreshing the show data

`../index.html` is the page shell with an embedded data snapshot; the page polls
`../payload.json` (same directory, served by GitHub Pages) about every 30 s for
live data.
Entries, start orders and placings change during the show, so re-run this before
the day your riders go.

```bash
bash fetch_entries.sh   # re-download all class pages (skips already-fetched; resumable)
python3 parse_entries.py
python3 build_page.py    # rebuilds ../index.html
```

- `fetch_entries.sh` needs `curl`; it refreshes the show session automatically.
  To force a full re-fetch, `rm -rf entries/` first. It also accepts an
  optional list file of class numbers (one per line) to re-fetch just those
  pages. Pages are written to a temp file and moved into place only when the
  new page looks valid, so a failed fetch never clobbers a good page.
- `classes.json` / `schedule.json` are the raw sources (class grid from
  horseshowsonline.com, schedule parsed from the 2026 Premium Book PDF).
  They only change if the show adds/removes classes or re-times the schedule.
- `data.json` is the intermediate parsed entries file.
- `payload.json` (repo root) is the compact published payload the page polls.
  A regular `build_page.py` writes it; `--ui-only` never touches it; cron
  commits it with `index.html`.

### Changing the page without re-fetching data

The template (markup/CSS/JS) lives in `build_page.py`. To rebuild the page
around the data you already have — no fetch, no new "asof":

```bash
python3 build_page.py --ui-only   # re-embeds the payload from the current ../index.html
```

The "Updated" timestamp in the page header only changes when the data
actually changes: a regular build keeps the existing asof when the parsed
data is identical to what's already embedded, and `--ui-only` never touches
it. The same policy applies to `payload.json`.

Deploy: replace `index.html` at the repo root and push — GitHub Pages picks it up.

### Auto-refresh (cron)

`refresh_cron.sh` runs on cron every 8 minutes and automates the whole
cycle: it re-fetches the **results frontier** (the first scheduled class
without placings, plus the next 8 classes to keep upcoming entry lists
fresh), rebuilds `index.html` + `payload.json`, and commits/pushes only
when the data changed. The frontier is derived from the payload embedded in
`../index.html` (a class is done when any entry has a place), so there is
no state file.
All output goes to `cron.log`. See AGENTS.md for details.

After any rebuild, run the smoke tests: `npm --prefix ../tests test`
(plus `python3 ../tests/test_ui_only.py` for `--ui-only`).
