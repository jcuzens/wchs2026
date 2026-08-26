#!/usr/bin/env python3
"""check.json (the tiny file the page polls instead of the full payload)
follows the same asof policy as payload.json: written by a regular build,
byte-identical across rebuilds around unchanged data, h (a hash of the
classes) and asof both change when the data changes, untouched by
--ui-only, and the embedded payload carries the same h so the page can
bootstrap. Restores repo state at the end."""
import datetime, hashlib, json, os, re, shutil, subprocess, sys, time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
PLJ = os.path.join(ROOT, "payload.json")
CHK = os.path.join(ROOT, "check.json")
DATA = os.path.join(ROOT, "refresh", "data.json")
BUILDER = os.path.join(ROOT, "refresh", "build_page.py")

def embedded_payload(path):
    s = open(path).read()
    m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
    assert m, "payload not found in " + path
    return m.group(1)

def h_of_classes(classes):
    return hashlib.sha1(json.dumps(classes, separators=(',', ':')).encode()).hexdigest()[:12]

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
chk_backup = CHK + ".bak"
plj_existed = os.path.exists(PLJ)
chk_existed = os.path.exists(CHK)
shutil.copyfile(IDX, idx_backup)
if plj_existed:
    shutil.copyfile(PLJ, plj_backup)
if chk_existed:
    shutil.copyfile(CHK, chk_backup)
try:
    # 1. a regular build publishes check.json: same asof as payload.json,
    #    h = sha1-12 of the canonical classes JSON, and the embedded
    #    payload carries the same h (bootstrap for the page)
    build()
    check("check.json written by build", os.path.exists(CHK))
    if os.path.exists(CHK):
        chk = json.loads(open(CHK).read())
        plj = json.loads(open(PLJ).read())
        emb = json.loads(embedded_payload(IDX))
        check("check.json asof equals payload asof", chk.get("asof") == plj["asof"],
              str(chk.get("asof")) + " vs " + str(plj["asof"]))
        check("check.json h hashes the canonical classes",
              chk.get("h") == h_of_classes(plj["classes"]), str(chk.get("h")))
        check("embedded payload carries the same h", emb.get("h") == chk.get("h"),
              str(emb.get("h")) + " vs " + str(chk.get("h")))
        check("check.json is tiny", os.path.getsize(CHK) < 100, str(os.path.getsize(CHK)) + " B")
    a0 = json.loads(open(PLJ).read())["asof"]

    # 2. rebuild with unchanged data -> byte-identical (asof policy holds)
    c_before = open(CHK).read()
    build()
    check("unchanged data keeps check.json byte-identical", open(CHK).read() == c_before)

    # 3. changed data -> h and asof both bump
    if a0 == datetime.datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M'):
        wait_next_minute()
    backup = DATA + ".bak"
    shutil.copyfile(DATA, backup)
    try:
        d = json.load(open(DATA))
        d.append({"num": "999997", "name": "check policy test class", "type": None, "division": "TEST",
                  "entries": [], "weekday": "Saturday", "period": "Morning", "date": "August 29", "time": "1:00 p.m."})
        json.dump(d, open(DATA, "w"), indent=1)
        build()
        chk = json.loads(open(CHK).read())
        plj = json.loads(open(PLJ).read())
        check("changed data bumps check.json h", chk["h"] == h_of_classes(plj["classes"]) and chk["h"] != json.loads(c_before)["h"],
              chk["h"])
        check("changed data bumps check.json asof", chk["asof"] != a0, chk["asof"] + " vs " + a0)
        check("changed data: embedded h matches check.json",
              json.loads(embedded_payload(IDX)).get("h") == chk["h"])
    finally:
        shutil.move(backup, DATA)

    # 4. --ui-only never touches check.json
    c_before = open(CHK).read()
    build("--ui-only")
    check("--ui-only leaves check.json untouched", open(CHK).read() == c_before)

    # 5. restore: rebuild from real data, fake class gone
    build()
    chk = json.loads(open(CHK).read())
    check("restored build drops test class",
          "999997" not in open(IDX).read() and "999997" not in open(PLJ).read()
          and chk["h"] == h_of_classes(json.loads(open(PLJ).read())["classes"]))
finally:
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
