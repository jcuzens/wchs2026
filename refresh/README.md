# Refreshing the show data

`../index.html` is a static snapshot (see "generated" date in the page footer).
Entries, start orders and placings change during the show, so re-run this before
the day your riders go.

```bash
bash fetch_entries.sh   # re-download all class pages (skips already-fetched; resumable)
python3 parse_entries.py
python3 build_page.py    # rebuilds ../index.html
```

- `fetch_entries.sh` needs `curl`; it refreshes the show session automatically.
  To force a full re-fetch, `rm -rf entries/` first.
- `classes.json` / `schedule.json` are the raw sources (class grid from
  horseshowsonline.com, schedule parsed from the 2026 Premium Book PDF).
  They only change if the show adds/removes classes or re-times the schedule.
- `data.json` is the intermediate parsed entries file.

Deploy: replace `index.html` at the repo root and push — GitHub Pages picks it up.
