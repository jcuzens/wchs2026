#!/usr/bin/env python3
"""asof policy: the page's 'Updated' timestamp only changes when the data
actually changes - a plain rebuild around unchanged data must keep it.

The baseline is the first build of this run (not the committed one): the
local inputs (data.json, live-scores files) may legitimately differ from
whatever produced the last commit, in which case the first build bumps the
asof exactly once - which is the policy working, not a bug."""
import datetime, json, os, re, shutil, subprocess, sys, time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
PLJ = os.path.join(ROOT, "payload.json")
CHK = os.path.join(ROOT, "check.json")
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

# Hold the cron lock for the duration of this test so a concurrent cron
# cycle cannot change the inputs (or the built files) mid-test; the cron
# then skips that cycle ("previous run still going").
import fcntl
_lock = open(os.path.join(os.path.dirname(BUILDER), "cron.lock"), "a+")
fcntl.flock(_lock.fileno(), fcntl.LOCK_EX)

idx_backup = IDX + ".bak"
shutil.copyfile(IDX, idx_backup)
plj_backup = PLJ + ".bak"
plj_existed = os.path.exists(PLJ)
if plj_existed:
    shutil.copyfile(PLJ, plj_backup)
chk_backup = CHK + ".bak"
chk_existed = os.path.exists(CHK)
if chk_existed:
    shutil.copyfile(CHK, chk_backup)
try:
    # 1. baseline build, then an unchanged rebuild: asof must not move
    #    (the baseline build itself may bump the asof once if the local
    #    inputs differ from the committed payload - that is the policy)
    build()
    a1 = asof_of(IDX)
    wait_next_minute()   # a broken "always now" implementation would differ here
    build()
    check("rebuild with unchanged data keeps asof", asof_of(IDX) == a1, asof_of(IDX) + " vs " + a1)

    # 2. changed data -> asof bumped (data.json is a git-ignored intermediate;
    #    back it up and always restore it)
    if a1 == datetime.datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M'):
        # same-minute aliasing: a fresh timestamp would be indistinguishable from a1
        wait_next_minute()
    backup = DATA + ".bak"
    shutil.copyfile(DATA, backup)
    try:
        d = json.load(open(DATA))
        d.append({"num": "999999", "name": "asof policy test class", "type": None, "division": "TEST",
                  "entries": [], "weekday": "Saturday", "period": "Morning", "date": "August 29", "time": "1:00 p.m."})
        json.dump(d, open(DATA, "w"), indent=1)
        build()
        a2 = asof_of(IDX)
        check("changed data bumps asof", a2 != a1, a2 + " vs " + a1)
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
    if chk_existed:
        shutil.move(chk_backup, CHK)
    elif os.path.exists(CHK):
        os.remove(CHK)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
