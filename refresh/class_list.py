#!/usr/bin/env python3
"""The show's live class list (the master grid on any class page).

ClassResults.aspx renders a master grid (grMaster) listing every class the
show currently scores - including split sections (89.1/89.2) as separate
rows - so it is the authoritative, up-to-date class universe (a pre-show
classes.json snapshot goes stale when the secretary splits or adds classes).
Each row's key in the grid's stateObject is that class's ClassGUID, so
fetch_entries.sh can fetch a section's page with a plain
ClassResults.aspx?ClassGUID=<key> GET (the page arrives with that section's
detail expanded, exactly like a normal class page).

Usage: class_list.py <page.html> [--classes classes.json]
    Parses the grid from the page and rewrites classes.json when the list
    changed. Exit codes: 0 unchanged, 3 changed, 1 error (no grid on the
    page - dead session). The cron runs it on the newest fetched page at
    the start of each cycle.
"""
import argparse
import html as H
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = re.compile(r"ASPx\.createControl\(ASPxClientGridView,'([^']*_grMaster)'")
ROW = re.compile(r'<tr id="[^"]*grMaster_DXDataRow(\d+)"[^>]*>(.*?)</tr>', re.S)
TD = re.compile(r'<td[^>]*>(?:(?!</td>).)*</td>', re.S)
GUID = re.compile(r"'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'")
NUM = re.compile(r'\d+(?:\.\d+)?')

def cell_text(td):
    t = re.sub(r'<[^>]+>', '', td)
    return H.unescape(t).replace('\xa0', ' ').strip()

def master_grid_keys(page):
    """The master grid's stateObject keys, one per row in row order (each a
    ClassGUID). None when the page has no master grid (dead session /
    no-entries page)."""
    m = MASTER.search(page)
    if not m:
        return None
    seg = page[m.start():m.start() + 500000]
    k = re.search(r"'keys':\s*\[(.*?)\]", seg)
    if not k:
        return None
    return GUID.findall(k.group(1))

def parse_master_grid(page):
    """The master grid rows, in grid order:
    [{num, name, type, division, entries, placed, guid}, ...].
    Row cells 2-7 carry num/name/type/division/entries/placed; a row whose
    index has no key (or whose num cell is not a class number) is skipped.
    [] when the page has no grid."""
    keys = master_grid_keys(page)
    if not keys:
        return []
    out = []
    for m in ROW.finditer(page):
        idx = int(m.group(1))
        if idx >= len(keys):
            continue
        cells = [cell_text(td) for td in TD.findall(m.group(2))]
        if len(cells) < 8 or not NUM.fullmatch(cells[2]):
            continue
        out.append({
            "num": cells[2], "name": cells[3] or None, "type": cells[4] or None,
            "division": cells[5] or None, "entries": cells[6] or None,
            "placed": cells[7] or None, "guid": keys[idx],
        })
    return out

def update_classes_json(path, rows):
    """Rewrite classes.json (schema: num, name, guid, type, division,
    entries) from the parsed grid rows when the list changed.
    Returns 'changed' or 'unchanged'."""
    new = [{"num": r["num"], "name": r["name"], "guid": r["guid"],
            "type": r["type"], "division": r["division"], "entries": r["entries"]}
           for r in rows]
    try:
        old = json.load(open(path))
    except (OSError, ValueError):
        old = None
    if old == new:
        return "unchanged"
    with open(path, 'w') as f:
        json.dump(new, f, indent=1)
    return "changed"

def _num_order(n):
    return [int(p) for p in n.split('.')]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", help="a fetched class page (entries/<num>.html)")
    ap.add_argument("--classes", default=os.path.join(HERE, "classes.json"))
    a = ap.parse_args()
    try:
        page = open(a.page, encoding='utf-8', errors='replace').read()
    except OSError as e:
        print("class_list.py: cannot read %s: %s" % (a.page, e), file=sys.stderr)
        sys.exit(1)
    rows = parse_master_grid(page)
    if not rows:
        print("class_list.py: no master grid in %s (dead session?)" % a.page,
              file=sys.stderr)
        sys.exit(1)
    old_nums = set()
    try:
        old_nums = {c["num"] for c in json.load(open(a.classes))}
    except (OSError, ValueError):
        pass
    res = update_classes_json(a.classes, rows)
    if res == "unchanged":
        print("class list unchanged (%d classes)" % len(rows))
        sys.exit(0)
    new_nums = {r["num"] for r in rows}
    added = sorted(new_nums - old_nums, key=_num_order)
    removed = sorted(old_nums - new_nums, key=_num_order)
    print("class list changed: %d classes (+%d new, -%d gone)"
          % (len(rows), len(added), len(removed)))
    if added:
        print("  added: " + " ".join(added))
    if removed:
        print("  removed: " + " ".join(removed))
    sys.exit(3)

if __name__ == '__main__':
    main()
