#!/usr/bin/env python3
"""payload.json (the published data file the page polls) follows the same
asof policy as the embedded payload: written by a regular build,
byte-identical across rebuilds around unchanged data, asof bumped when the
data changes, untouched by --ui-only. Restores repo state at the end."""
import datetime, json, os, re, shutil, subprocess, sys, time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
PLJ = os.path.join(ROOT, "payload.json")
DATA = os.path.join(ROOT, "refresh", "data.json")
BUILDER = os.path.join(ROOT, "refresh", "build_page.py")

def embedded_payload(path):
    s = open(path).read()
    m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
    assert m, "payload not found in " + path
    return m.group(1)

def asof_of_payload(p):
    return json.loads(p)["asof"]

def build(*args):
    subprocess.run([sys.executable, BUILDER, *args], check=True)

def wait_next_minute():
    time.sleep(60 - datetime.datetime.now().second + 1)

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

# Hold the cron lock for the duration of this test so a concurrent cron
# cycle cannot change the inputs (or the built files) mid-test; the cron
# then skips that cycle ("previous run still going").
import fcntl
_lock = open(os.path.join(os.path.dirname(BUILDER), "cron.lock"), "a+")
fcntl.flock(_lock.fileno(), fcntl.LOCK_EX)

idx_backup = IDX + ".bak"
plj_backup = PLJ + ".bak"
plj_existed = os.path.exists(PLJ)
shutil.copyfile(IDX, idx_backup)
if plj_existed:
    shutil.copyfile(PLJ, plj_backup)
try:
    # 1. a regular build publishes payload.json equal to the embedded payload
    build()
    check("payload.json written by build", os.path.exists(PLJ))
    check("payload.json equals embedded payload",
          open(PLJ).read().rstrip("\n") == embedded_payload(IDX))
    a0 = asof_of_payload(open(PLJ).read())

    # 2. rebuild with unchanged data -> byte-identical (asof policy holds)
    p_before = open(PLJ).read()
    build()
    check("unchanged data keeps payload.json byte-identical",
          open(PLJ).read() == p_before, asof_of_payload(open(PLJ).read()) + " vs " + a0)

    # 3. changed data -> asof bumps (same pattern as test_asof.py)
    if a0 == datetime.datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M'):
        wait_next_minute()
    backup = DATA + ".bak"
    shutil.copyfile(DATA, backup)
    try:
        d = json.load(open(DATA))
        d.append({"num": "999998", "name": "payload policy test class", "type": None, "division": "TEST",
                  "entries": [], "weekday": "Saturday", "period": "Morning", "date": "August 29", "time": "1:00 p.m."})
        json.dump(d, open(DATA, "w"), indent=1)
        build()
        check("changed data bumps payload.json asof",
              asof_of_payload(open(PLJ).read()) != a0, asof_of_payload(open(PLJ).read()) + " vs " + a0)
        check("changed data also bumps embedded asof",
              asof_of_payload(embedded_payload(IDX)) != a0)
    finally:
        shutil.move(backup, DATA)

    # 4. --ui-only never touches payload.json
    p_before = open(PLJ).read()
    build("--ui-only")
    check("--ui-only leaves payload.json untouched", open(PLJ).read() == p_before)

    # 5. restore: rebuild from real data, fake class gone
    build()
    check("restored build drops test class",
          "999998" not in open(IDX).read() and "999998" not in open(PLJ).read())
finally:
    shutil.move(idx_backup, IDX)
    if plj_existed:
        shutil.move(plj_backup, PLJ)
    elif os.path.exists(PLJ):
        os.remove(PLJ)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
