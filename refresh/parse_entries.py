import re, json, glob, html as h, os

def cell_text(td):
    t = re.sub(r'<[^>]+>', '', td)
    return h.unescape(t).replace('\xa0', ' ').strip()

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

def page_class_num(page):
    """The class number from the page's own detail title ('Class: 89.2').
    A split section's page labels itself with the section number; the file
    name may be the parent's. None when the page has no expanded detail
    (no-entries / failed page)."""
    m = re.search(r'Class:\s*(\d+(?:\.\d+)?)', page)
    return m.group(1) if m else None

def parse_page(page, fallback_num, classes, sched_lookup):
    """One fetched class page -> a data.json record. The page's own
    'Class: N' label wins over fallback_num (the file name). Class metadata
    comes from the class list entry for N; the schedule slot falls back to
    the parent's when N is a section (x.y). None when N is not in the class
    list (a stale page for a class no longer in the master grid)."""
    placed = parse_rows(page, 'grPlacing')
    nonpl = parse_rows(page, 'grNonPlacing')
    entries = []
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
    num = page_class_num(page) or fallback_num
    if num not in classes:
        # The master grid is the class universe: a page for a class that is
        # no longer in it is stale (e.g. a pre-split parent page, 114, fetched
        # before the show split it into 114.1/114.2). Its entries now live in
        # the section pages; a record here would be a ghost with null
        # name/division.
        return None
    wc = classes.get(num)
    parent = num.split('.')[0]
    sc = sched_lookup.get(num) or sched_lookup.get(parent)
    # class metadata comes from the show site's HTML and is entity-escaped
    # there, like the entry cells above
    rec = {
        "num": num,
        "name": h.unescape(wc["name"]) if wc and wc["name"] else None,
        "type": h.unescape(wc["type"]) if wc and wc["type"] else None,
        "division": h.unescape(wc["division"]) if wc and wc["division"] else None,
        "entries": entries,
    }
    if sc:
        rec.update({k: sc[k] for k in ("weekday", "period", "date", "time")})
        rec["sched_name"] = sc["sched_name"]
    return rec

def dedupe(pairs):
    """One record per class number. After a split, two fetched pages can
    label themselves with the same section number: the parent page (133.html,
    which the site now serves as section 1) and the section page (133.1.html).
    The page whose file name matches the class number is canonical; any other
    tie goes to the newest fetch. pairs: (file_name, path, record)."""
    best = {}
    for fname, path, rec in pairs:
        cand = (fname == rec["num"], os.path.getmtime(path))
        cur = best.get(rec["num"])
        if cur is None or cand > cur[0]:
            best[rec["num"]] = (cand, rec)
    return [rec for _, rec in best.values()]

def main():
    classes = {c['num']: c for c in json.load(open('classes.json'))}
    sched = json.load(open('schedule.json'))

    # build schedule lookup: num -> session info
    sched_lookup = {}
    for s in sched:
        sess = {"weekday": s["weekday"], "period": s["period"], "date": s["date"], "time": s["time"]}
        for c in s["classes"]:
            sched_lookup[c["num"]] = {**sess, "sched_name": c["name"]}

    all_entries = []
    problems = []
    stale = []
    for f in sorted(glob.glob('entries/*.html')):
        fname = f.split('/')[-1][:-5]
        page = open(f, encoding='utf-8', errors='replace').read()
        if 'grPlacing_DXDataRow' not in page and 'grNonPlacing_DXDataRow' not in page:
            if 'No entries' in page or 'no data' in page.lower():
                continue
            problems.append(fname)
            continue
        rec = parse_page(page, fname, classes, sched_lookup)
        if rec is None:
            stale.append(fname)
            continue
        all_entries.append((fname, f, rec))

    records = dedupe(all_entries)
    if len(records) < len(all_entries):
        print(f"deduped {len(all_entries) - len(records)} duplicate section record(s)")
    all_entries = records

    json.dump(all_entries, open('data.json', 'w'), indent=1)
    print(f"classes with data: {len(all_entries)}")
    print(f"total entries: {sum(len(c['entries']) for c in all_entries)}")
    print(f"no schedule slot: {[c['num'] for c in all_entries if 'weekday' not in c]}")
    print(f"stale (not in class list): {stale}")
    print(f"problems: {problems}")
    n = len(all_entries)
    print(f"avg entries/class: {sum(len(c['entries']) for c in all_entries)/max(n,1):.1f}")
    # data size
    print(f"data.json size: {os.path.getsize('data.json')/1024:.0f} KB")

if __name__ == '__main__':
    main()
