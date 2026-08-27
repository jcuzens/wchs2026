#!/usr/bin/env python3
"""Frontier selection for the cron refresh: walk the schedule from the last
'done' class (any entry has a place - same rule as the page's isDone), stop
at the first class whose results are not posted yet. A class whose session
started FORCE_DONE_HOURS ago with no results is presumed skipped and passed
over, so a void class can't stall the frontier forever."""
import datetime, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import select_frontier as sf

def rec(num, places):
    return {"num": num, "name": "t", "type": None, "division": "T",
            "entries": [{"place": p, "entry": "e"} for p in places]}

# --- synthetic schedule: two sessions on August 22
#     A: 10:00 a.m.  classes 1, 2, 3
#     B: 6:00 p.m.   classes 4, 5, 6
#   5 is split into 5.1/5.2 (parent not fetchable); 6 has no page at all.
SCHED = [
    {"weekday": "Saturday", "period": "Morning", "date": "August 22", "time": "10:00 a.m.",
     "classes": [{"num": "1"}, {"num": "2"}, {"num": "3"}]},
    {"weekday": "Saturday", "period": "Night", "date": "August 22", "time": "6:00 p.m.",
     "classes": [{"num": "4"}, {"num": "5"}, {"num": "6"}]},
]
CLASSES = ["1", "2", "3", "4", "5.1", "5.2"]
NOW_A = datetime.datetime(2026, 8, 22, 12, 0)   # 2h into session A
NOW_LATE = datetime.datetime(2026, 8, 22, 15, 0)  # 5h after A, 3h before B
ALL_DONE = [rec("1", ["1"]), rec("2", ["1"]), rec("3", ["1"]), rec("4", ["1"]),
            rec("5.1", ["1"]), rec("5.2", ["1"])]

# 1. basic frontier: 1,2 done; 3 has entries but no place -> stop at 3
d = [rec("1", ["1", "2"]), rec("2", ["1"]), rec("3", [None] * 3)]
check("frontier stops at first class without results",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_A) == "3")

# 2. a class whose page has no entries is not the frontier
d = [rec("1", ["1"]), rec("2", ["1"]), rec("4", [None] * 2)]
check("frontier moves past a no-entries class",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_A) == "4")

# 3. sub-classes: 5 is settled only when both 5.1 and 5.2 are settled
d = [rec("1", ["1"]), rec("2", ["1"]), rec("3", ["1"]), rec("4", ["1"]),
     rec("5.1", ["1"]), rec("5.2", [None] * 2)]
check("subclass without results holds the frontier",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_A) == "5")
d = [rec("1", ["1"]), rec("2", ["1"]), rec("3", ["1"]), rec("4", ["1"]), rec("5.1", ["1"])]
check("subclass with no entries does not hold the frontier",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_A) is None)

# 4. force-done: session A is 5h old and 3 never got results -> skip to B
d = [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 2), rec("4", [None] * 2)]
check("stale class is presumed skipped, frontier advances to next session",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_LATE) == "4")
check("recent session's class is not force-skipped",
      sf.frontier_num(SCHED, set(CLASSES), d, NOW_A) == "3")

# 5. everything settled -> no frontier
check("no frontier when everything is done",
      sf.frontier_num(SCHED, set(CLASSES), ALL_DONE, NOW_A) is None)

# 6. lookahead: the next k schedule classes after the frontier, as fetchable nums
d = [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 3)]
check("lookahead lists next classes after the frontier",
      sf.lookahead_nums(SCHED, set(CLASSES), d, NOW_A, k=2) == ["4", "5.1", "5.2"])
check("lookahead is empty when there is no frontier",
      sf.lookahead_nums(SCHED, set(CLASSES), ALL_DONE, NOW_A, k=2) == [])

# 7. session time parsing (real formats from schedule.json)
check("parses a.m. time", sf.parse_session_time("August 22", "11:00 a.m.", 2026)
      == datetime.datetime(2026, 8, 22, 11, 0))
check("parses Noon time", sf.parse_session_time("August 23", "12:00 Noon", 2026)
      == datetime.datetime(2026, 8, 23, 12, 0))
check("parses p.m. time", sf.parse_session_time("August 22", "7:00 p.m.", 2026)
      == datetime.datetime(2026, 8, 22, 19, 0))
check("garbage time -> None", sf.parse_session_time("August 22", "whenever", 2026) is None)

# 8. CLI (what refresh_cron.sh invokes)
tmp = tempfile.mkdtemp(prefix="frontier_")
sched_p, cls_p, data_p = (os.path.join(tmp, n) for n in ("schedule.json", "classes.json", "data.json"))
json.dump(SCHED, open(sched_p, "w"))
json.dump([{"num": n} for n in CLASSES], open(cls_p, "w"))
d = [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 3)]
json.dump(d, open(data_p, "w"))
MOD = os.path.join(ROOT, "refresh", "select_frontier.py")
def cli(*args):
    r = subprocess.run([sys.executable, MOD, *args,
                        "--sched", sched_p, "--classes", cls_p, "--data", data_p,
                        "--now", "2026-08-22T12:00"],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()

rc, out = cli("frontier")
check("cli frontier prints the frontier class", out == "3", out)
rc, out = cli("frontier-nums")
check("cli frontier-nums prints fetchable nums", out == "3", out)
rc, out = cli("settled", "1")
check("cli settled exits 0 for a done class", rc == 0, str(rc))
rc, out = cli("settled", "3")
check("cli settled exits 1 for the frontier class", rc == 1, str(rc))
rc, out = cli("lookahead", "2")
check("cli lookahead prints next fetchable nums", out == "4\n5.1\n5.2", out)

# 8b. upcoming: every not-yet-settled, not-stale schedule class in order,
#     sections expanded (the 4-hour scratch refresh fetches exactly these)
D_UP = [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 3), rec("4", [None] * 2),
        rec("5.1", [None] * 2), rec("5.2", ["1"])]
check("upcoming lists unsettled non-stale classes in schedule order",
      sf.upcoming_nums(SCHED, set(CLASSES), D_UP, NOW_A) == ["3", "4", "5.1", "5.2"],
      str(sf.upcoming_nums(SCHED, set(CLASSES), D_UP, NOW_A)))
check("upcoming excludes stale (presumed skipped) classes",
      sf.upcoming_nums(SCHED, set(CLASSES),
                       [rec("1", ["1"]), rec("2", ["1"]), rec("3", [None] * 2), rec("4", [None] * 2)],
                       NOW_LATE) == ["4"])
check("upcoming is empty when everything is settled",
      sf.upcoming_nums(SCHED, set(CLASSES), ALL_DONE, NOW_A) == [])
json.dump(D_UP, open(data_p, "w"))
rc, out = cli("upcoming")
check("cli upcoming prints fetchable nums in order", out == "3\n4\n5.1\n5.2", out)

# 9. property check against the real committed payload (data evolves during the
#    show, so assert invariants, not exact numbers)
sched = json.load(open(os.path.join(ROOT, "refresh", "schedule.json")))
cj = {c["num"] for c in json.load(open(os.path.join(ROOT, "refresh", "classes.json")))}
payload = json.loads(re.search(
    r'^(?:const|let) DATA = (\{.*\});\s*$',
    open(os.path.join(ROOT, "index.html")).read(), re.M).group(1))
data = [{"num": c["n"], "entries": [{"place": e[6]} for e in c["e"]]}
        for c in payload["classes"]]
now = datetime.datetime(2026, 8, 25, 12, 0)
order = [c["num"] for s in sched for c in s["classes"]]
f = sf.frontier_num(sched, cj, data, now)
if f is None:
    check("real payload: frontier is None (all settled)", True)
else:
    i = order.index(f)
    check("real payload: frontier not settled", not sf.is_settled(f, cj, data), f)
    check("real payload: everything before the frontier is settled or stale",
          all(sf.is_settled(n, cj, data) or sf.is_stale(n, sched, now)
              for n in order[:i]))
    check("real payload: frontier fetchable nums are known classes",
          all(n in cj for n in sf.fetch_nums_for(f, cj)))

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
