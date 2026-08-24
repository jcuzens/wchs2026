#!/usr/bin/env python3
"""asof policy: the page's 'Updated' timestamp only changes when the data
actually changes - a plain rebuild around unchanged data must keep it."""
import datetime, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
PLJ = os.path.join(ROOT, "payload.json")
DATA = os.path.join(ROOT, "refresh", "data.json")
BUILDER = os.path.join(ROOT, "refresh", "build_page.py")

def asof_of(path):
    s = open(path).read()
    m = re.search(r'"asof":"([^"]*)"', s)
    assert m, "asof not found in " + path
    return m.group(1)

def build():
    subprocess.run([sys.executable, BUILDER], check=True)

def wait_next_minute():
    time.sleep(60 - datetime.datetime.now().second + 1)

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

a0 = asof_of(IDX)
idx_backup = IDX + ".bak"
shutil.copyfile(IDX, idx_backup)
plj_backup = PLJ + ".bak"
plj_existed = os.path.exists(PLJ)
if plj_existed:
    shutil.copyfile(PLJ, plj_backup)
try:
    # 1. plain rebuild, unchanged data -> asof unchanged
    build()
    check("rebuild with unchanged data keeps asof", asof_of(IDX) == a0, asof_of(IDX) + " vs " + a0)

    # 2. changed data -> asof bumped (data.json is a git-ignored intermediate;
    #    back it up and always restore it)
    if a0 == datetime.datetime.now().strftime('%Y-%m-%d %H:%M'):
        # same-minute aliasing: a fresh timestamp would be indistinguishable from a0
        wait_next_minute()
    backup = DATA + ".bak"
    shutil.copyfile(DATA, backup)
    try:
        d = json.load(open(DATA))
        d.append({"num": "999999", "name": "asof policy test class", "type": None, "division": "TEST",
                  "entries": [], "weekday": "Saturday", "period": "Morning", "date": "August 29", "time": "1:00 p.m."})
        json.dump(d, open(DATA, "w"), indent=1)
        build()
        a1 = asof_of(IDX)
        check("changed data bumps asof", a1 != a0, a1 + " vs " + a0)
    finally:
        shutil.move(backup, DATA)

    # 3. restore: rebuild from real data, fake class must be gone
    build()
    s = open(IDX).read()
    check("restored build drops test class", "999999" not in s)
    check("restored build has the full class list", s.count('"n":"') >= 210, str(s.count('"n":"')))
finally:
    # asof is monotonic, so the rebuild around restored data may not reproduce the
    # committed files byte-for-byte; put the originals back so the repo state is clean
    shutil.move(idx_backup, IDX)
    if plj_existed:
        shutil.move(plj_backup, PLJ)
    elif os.path.exists(PLJ):
        os.remove(PLJ)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
