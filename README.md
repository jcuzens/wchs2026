# WCHS 2026 — My Schedule

A personal schedule page for the **2026 World's Championship Horse Show**
(August 22–29, 2026 · Kentucky State Fair, Lexington, KY), so everyone at
the barn can see exactly which of *our* horses go when — and in what order.

**Live:** https://jcuzens.github.io/wchs2026/

## Using the page

Open the link on your phone:

- Pick your horses by **trainer, rider, horse, owner, or division** —
  combine as many as you like; every filter has its own search box.
- Your selection is saved **on that device** and restored the next time
  you open the page.
- **Copy link** shares that exact selection with someone else (it's
  encoded in the URL) — handy for the barn you're not at.
- **Print** produces a day-by-day schedule of only your classes, with a
  page break per day.
- The page checks for new results about every 30 seconds and updates in
  place — the small ring next to the "Updated" time fills as the next
  check approaches, and the timestamp moves when new data lands. No need
  to refresh.
- Under each class you'll see the **entry number and placings** (entries
  are listed in start order); a blank slot means that class hasn't been
  judged yet.
- The highlighted card shows where the show is: **"on now · est H:MM"** or
  **"up next · est H:MM"**. Those times are *predictions* from an average
  class pace (~13.5 min, anchored to the live scoreboard) — actual order
  may vary. Classes the model has passed but that still lack official
  results are marked **"awaiting results"**.

Entries and placings change during the show — the page picks them up on
its own (the "Updated" time in the header tells you how fresh the data
is).

## What's in the repo

Two generated files, no server, no dependencies. `index.html` is the page
shell with an embedded data snapshot (first paint + offline fallback);
`payload.json` is the live data the shell re-fetches about every 30 s
while the page is open.

| File | Role |
|---|---|
| `index.html` | The page. **Generated — don't edit by hand.** Served by GitHub Pages. |
| `payload.json` | Live data the page polls every ~30 s. **Generated — don't edit by hand.** |
| `refresh/build_page.py` | Generator: page template + data → `index.html` |
| `refresh/classes.json` | Class grid (scraped from horseshowsonline.com) |
| `refresh/schedule.json` | Session schedule (parsed from the 2026 Premium Book PDF) |
| `refresh/fetch_entries.sh` | Downloads all class entry pages (resumable) |
| `refresh/parse_entries.py` | Parses the entry pages → `refresh/data.json` |
| `tests/` | Smoke tests for the built page (dev-only jsdom dependency) |

`refresh/data.json`, `refresh/entries/`, `refresh/jar.txt` and
`refresh/fetchlist.txt` are local build intermediates and are git-ignored.
To rebuild the page UI without a data refresh:
`python3 refresh/build_page.py --ui-only`.

## Refreshing the data during the show

```bash
cd refresh
./fetch_entries.sh        # re-download class pages (resumable, skips fresh ones)
python3 parse_entries.py  # rebuild data.json
python3 build_page.py     # rebuild ../index.html
```

Then commit `index.html` and `payload.json` and push — GitHub Pages picks
them up within a couple of minutes (cron does this automatically every 8
min). Details in [refresh/README.md](refresh/README.md).

Requirements to rebuild: Python 3 (standard library only) and `curl`.
That's the whole dependency list.
