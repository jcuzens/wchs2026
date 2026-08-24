#!/usr/bin/env python3
"""Frontier selection for the cron refresh (see tests/test_frontier.py).

The show advances through schedule order, and a class is "done" the same way
the page defines it: at least one of its entries has a place. The frontier is
the first class in schedule order whose results are not posted yet. A class
whose session started more than FORCE_DONE_HOURS ago with no results is
presumed skipped, so a void class cannot stall the frontier forever.
"""
import argparse, datetime, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SHOW_YEAR = 2026
FORCE_DONE_HOURS = 4

def parse_session_time(date_str, time_str, year=SHOW_YEAR):
    try:
        d = datetime.datetime.strptime(date_str, "%B %d")
        t = time_str.strip()
        if "noon" in t.lower():
            return d.replace(year=year, hour=12, minute=0)
        up = t.upper()
        if up.endswith("A.M.") or up.endswith("P.M."):
            mer = 12 if up.endswith("P.M.") else 0
            hh, mm = t[:-4].split(":")
            return d.replace(year=year, hour=int(hh) % 12 + mer, minute=int(mm))
        return None
    except (ValueError, AttributeError):
        return None

def fetch_nums_for(num, cj):
    out = [num] if num in cj else []
    out += sorted(n for n in cj if n.startswith(num + "."))
    return out

def _has_place(rec):
    return any(e.get("place") is not None for e in rec.get("entries", []))

def is_settled(num, cj, data):
    by = {c["num"]: c for c in data}
    nums = fetch_nums_for(num, cj)
    if not nums:
        return True
    return all(n not in by or _has_place(by[n]) for n in nums)

def _session_start(num, sched):
    for s in sched:
        for c in s["classes"]:
            if c["num"] == num:
                return parse_session_time(s["date"], s["time"])
    return None

def is_stale(num, sched, now):
    start = _session_start(num, sched)
    if start is None:
        return False
    return (now - start).total_seconds() > FORCE_DONE_HOURS * 3600

def _order(sched):
    return [c["num"] for s in sched for c in s["classes"]]

def frontier_num(sched, cj, data, now):
    for num in _order(sched):
        if is_settled(num, cj, data):
            continue
        if is_stale(num, sched, now):
            continue
        return num
    return None

def lookahead_nums(sched, cj, data, now, k=8):
    f = frontier_num(sched, cj, data, now)
    if f is None:
        return []
    order = _order(sched)
    i = order.index(f)
    out = []
    for num in order[i + 1: i + 1 + k]:
        out.extend(fetch_nums_for(num, cj))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["frontier", "frontier-nums", "settled", "lookahead"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--sched", default=os.path.join(HERE, "schedule.json"))
    ap.add_argument("--classes", default=os.path.join(HERE, "classes.json"))
    ap.add_argument("--data", default=os.path.join(HERE, "data.json"))
    ap.add_argument("--now", default=None,
                    help="override the clock, ISO format (for tests/debugging)")
    a = ap.parse_args()
    sched = json.load(open(a.sched))
    cj = {c["num"] for c in json.load(open(a.classes))}
    data = json.load(open(a.data))
    now = datetime.datetime.fromisoformat(a.now) if a.now else datetime.datetime.now()
    if a.cmd == "frontier":
        f = frontier_num(sched, cj, data, now)
        if f:
            print(f)
    elif a.cmd == "frontier-nums":
        f = frontier_num(sched, cj, data, now)
        if f:
            print("\n".join(fetch_nums_for(f, cj)))
    elif a.cmd == "settled":
        raise SystemExit(0 if is_settled(a.arg, cj, data) else 1)
    elif a.cmd == "lookahead":
        k = int(a.arg) if a.arg else 8
        print("\n".join(lookahead_nums(sched, cj, data, now, k)))

if __name__ == "__main__":
    main()
