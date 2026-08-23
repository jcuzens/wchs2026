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
- Under each class you'll see the **start order and placings**; a blank
  slot means that class hasn't been judged yet.

The data snapshot date is in the page footer. Entries and placings change
during the show — refresh it before the day your riders go (below).

## What's in the repo

One self-contained HTML file — no server, no dependencies, works offline.
All data (210 classes, 3,471 entries at first snapshot) is embedded in the
page itself.

| File | Role |
|---|---|
| `index.html` | The page. **Generated — don't edit by hand.** Served by GitHub Pages. |
| `refresh/build_page.py` | Generator: page template + data → `index.html` |
| `refresh/classes.json` | Class grid (scraped from horseshowsonline.com) |
| `refresh/schedule.json` | Session schedule (parsed from the 2026 Premium Book PDF) |
| `refresh/fetch_entries.sh` | Downloads all class entry pages (resumable) |
| `refresh/parse_entries.py` | Parses the entry pages → `refresh/data.json` |

`refresh/data.json`, `refresh/entries/`, `refresh/jar.txt` and
`refresh/fetchlist.txt` are local build intermediates and are git-ignored.

## Refreshing the data during the show

```bash
cd refresh
./fetch_entries.sh        # re-download class pages (resumable, skips fresh ones)
python3 parse_entries.py  # rebuild data.json
python3 build_page.py     # rebuild ../index.html
```

Then commit `index.html` and push — GitHub Pages picks it up within a
couple of minutes. Details in [refresh/README.md](refresh/README.md).

Requirements to rebuild: Python 3 (standard library only) and `curl`.
That's the whole dependency list.
