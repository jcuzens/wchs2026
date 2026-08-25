#!/usr/bin/env python3
"""Live Scores protocol + parsing (refresh/live_scores.py) against real
fixtures captured from LiveScoring.aspx on 2026-08-24. Also covers the
merge/cache rules, the parse_live.py CLI, and build_page.py wiring."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import live_scores as ls

PAGE = open(os.path.join(HERE, "fixtures", "live_page.html")).read()
RESP = open(os.path.join(HERE, "fixtures", "live_showall.txt")).read()

# --- GET page bootstrap
boot = ls.parse_get_page(PAGE)
check("get: grid found", boot is not None)
check("get: callback id",
      boot["callback_id"] == "ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain")
check("get: 7 form fields in DOM order",
      [f[0] for f in boot["fields"]] == [
          "__EVENTTARGET", "__EVENTARGUMENT", "__VIEWSTATE",
          "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
          "ctl00$ctl00$MainContent$panContentRight$ContentShow$LiveClassResultsControl$cbLiveResults$grMain$DXSE",
          "ctl00$ctl00$ASPxDateEditMaster"])
check("get: event validation present",
      len(dict(boot["fields"])["__EVENTVALIDATION"]) > 100)
check("get: 8 row keys", len(boot["keys"]) == 8)
check("get: callback state token", len(boot["callbackState"]) > 100)
check("get: dead session -> None", ls.parse_get_page("<html>login shell</html>") is None)

# --- callback response envelope
check("resp: fault -> None",
      ls.response_html("0|/*DX*/({'generalError':'boom'})") is None)
html = ls.response_html(RESP)
check("resp: html unescaped",
      html is not None and "dxgvDataRow_Office2010Blue" in html)
st = ls.parse_envelope_state(RESP)
check("env: 8 keys", st is not None and len(st["keys"]) == 8)
check("env: callback state", len(st["callbackState"]) > 100)
check("env: group level state", st["groupLevelState"] == "{}")

# --- top-level rows
rows = ls.top_rows(html)
check("rows: headers + adaptive + 8 data + 1 detail",
      sorted(rows.keys()) == sorted(
          ["DXHeadersRow0", "DXADRow"] + ["DXDataRow%d" % i for i in range(8)] + ["DXDRow0"]))

# --- parent rows (class 48 is the expanded row in this capture)
p48 = ls.parse_parent_row(rows["DXDataRow0"])
check("parent: class 48 identity",
      p48["num"] == "48"
      and p48["name"] == "48 - Equitation - Open Class Rider 11 Years Old"
      and p48["ring"] == "Ring 1" and p48["ord"] == 1)
check("parent: progress + counts",
      p48["shown"] == 11 and p48["total"] == 11
      and p48["placed"] == 7 and p48["not_placed"] == 4)
check("parent: updated + source",
      p48["updated"] == "2 hours, 2 min" and p48["source"] == "Show Secretary")
p54 = ls.parse_parent_row(rows["DXDataRow7"])
check("parent: last row (54)",
      p54["num"] == "54" and p54["placed"] == 8 and p54["updated"] == "43 min")
p531 = ls.parse_parent_row(rows["DXDataRow5"])
check("parent: subclass number kept", p531["num"] == "53.1")

# --- detail (class 48's placed entries)
ents = ls.parse_detail_entries(rows["DXDRow0"])
check("detail: 7 placed entries", len(ents) == 7)
check("detail: first entry",
      ents[0] == ["1158", "TWENTY FOUR KARAT MAGIC", "WITMER, HAYLEN", 6, 1])
check("detail: apostrophe horse name",
      ents[6][1] == "SH LYNN'S LICORICE" and ents[6][0] == "935")
check("detail: places are 1..7", sorted(e[4] for e in ents) == [1, 2, 3, 4, 5, 6, 7])

# --- updated-string -> minutes
for s, want in [("53 min", 53), ("1 hour, 51 min", 111), ("2 hours, 2 min", 122),
                ("43 min", 43), ("Just now", 0), ("1 hour", 60)]:
    check("minutes: %r" % s, ls.updated_to_minutes(s) == want, str(ls.updated_to_minutes(s)))
check("minutes: empty -> None",
      ls.updated_to_minutes(None) is None and ls.updated_to_minutes("") is None)

# --- protocol strings (what fetch_live.py sends)
state = {"keys": ["aaaa", "bbbb"], "callbackState": "xyz", "groupLevelState": "{}"}
p = ls.build_param(state, "bbbb")
check("param: c0 KV FR CT GB shape",
      p == "c0:KV|15;[\"aaaa\",\"bbbb\"];FR|1;0;CT|2;{};GB|22;13|SHOWDETAILROW4|bbbb;", p)
name, val = ls.grid_state_field("GRID", state)
check("state field: name is the grid uniqueID", name == "GRID")
check("state field: html-escaped compact json",
      val == ("{&quot;keys&quot;:[&quot;aaaa&quot;,&quot;bbbb&quot;],"
              "&quot;groupLevelState&quot;:{},&quot;callbackState&quot;:&quot;xyz&quot;,"
              "&quot;focusedRow&quot;:0,&quot;selection&quot;:&quot;&quot;,"
              "&quot;toolbar&quot;:&quot;{}&quot;}"), val)

# --- merge rule: official wins, live fills gaps
def mcls(n, entries):    # entries: [(entry, place_or_None)]
    return {"n": n, "name": "t", "e": [[e, "h", "r", "t", "o", None, p] for e, p in entries]}
def mcache(num, places): # places: {entry: place}
    return {num: {str(k): {"p": v, "at": "2026-08-24 09:20"} for k, v in places.items()}}

d = [mcls("48", [("1158", None), ("958", "1")]), mcls("49", [("1", None)])]
ls.merge_live_places(d, mcache("48", {"1158": 1, "958": 5}))
check("merge: live fills the gap", d[0]["e"][0][6] == "1")
check("merge: official place wins over live", d[0]["e"][1][6] == "1")
check("merge: class not in cache untouched", d[1]["e"][0][6] is None)
d2 = [mcls("48", [("1158", "2")])]
ls.merge_live_places(d2, mcache("48", {"1158": 7}))
check("merge: never overwrites an official place", d2[0]["e"][0][6] == "2")
d3 = [mcls("48", [("1158", None)])]
ls.merge_live_places(d3, {})
check("merge: empty cache is a no-op", d3[0]["e"][0][6] is None)

# --- cache: accumulate across runs, idempotent
c = {}
live1 = {"fetched": "2026-08-24 09:20",
         "classes": [{"num": "48", "entries": [["1158", "H", "R", 1]]}]}
live2 = {"fetched": "2026-08-24 09:28",
         "classes": [{"num": "48", "entries": [["958", "H", "R", 2]]},
                     {"num": "49", "entries": [["1", "H", "R", 3]]}]}
ls.fold_live_cache(c, live1)
ls.fold_live_cache(c, live2)
check("cache: accumulates across runs",
      c["48"]["1158"]["p"] == 1 and c["48"]["958"]["p"] == 2 and c["49"]["1"]["p"] == 3)
check("cache: run timestamp stamped", c["48"]["958"]["at"] == "2026-08-24 09:28")
snapshot = json.loads(json.dumps(c))
ls.fold_live_cache(c, live2)
check("cache: idempotent on re-run", c == snapshot)

# first-seen timestamp is stable across re-folds (the predicted-pace model
# anchors on it; a moving stamp would wobble the asof stamp)
live3 = {"fetched": "2026-08-24 09:36",
         "classes": [{"num": "48", "entries": [["1158", "H", "R", 3]]}]}
c_snap = json.loads(json.dumps(c))
ls.fold_live_cache(c, live3)
check("cache: re-score updates the place", c["48"]["1158"]["p"] == 3)
check("cache: first-seen at kept on re-fold", c["48"]["1158"]["at"] == "2026-08-24 09:20")
check("cache: other entries untouched",
      c["48"]["958"] == c_snap["48"]["958"] and c["49"] == c_snap["49"])

# --- parse_live.py CLI (temp files; the repo's live files are never touched)
import tempfile
tmp = tempfile.mkdtemp(prefix="livetest_")
lp, cp = os.path.join(tmp, "live.json"), os.path.join(tmp, "cache.json")
json.dump(live2, open(lp, "w"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"), lp, cp],
                   capture_output=True, text=True)
check("cli: exits 0", r.returncode == 0, r.stderr.strip())
c1 = json.load(open(cp))
check("cli: wrote the folded cache", c1["48"]["958"]["p"] == 2 and c1["49"]["1"]["p"] == 3)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"), lp, cp],
                   capture_output=True, text=True)
check("cli: re-run is idempotent", json.load(open(cp)) == c1)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "parse_live.py"),
                    os.path.join(tmp, "nope.json"), cp], capture_output=True, text=True)
check("cli: missing live.json -> non-zero, cache untouched",
      r.returncode != 0 and json.load(open(cp)) == c1, r.stderr.strip())

# --- build_page.py wiring (temp repo copy: merge + live flag)
import shutil
tmp = tempfile.mkdtemp(prefix="livebuild_")
os.makedirs(os.path.join(tmp, "refresh"))
for fn in ("build_page.py", "live_scores.py", "predict.py", "select_frontier.py"):
    shutil.copyfile(os.path.join(ROOT, "refresh", fn),
                    os.path.join(tmp, "refresh", fn))
mini = [{"num": "48", "name": "Equitation", "type": None, "division": "EQ",
         "weekday": "Saturday", "period": "Morning", "date": "August 22",
         "time": "10:00 a.m.",
         "entries": [
             {"entry": "1158", "horse": "H1", "rider": "R1", "trainer": "T1",
              "owner": "O1", "start": "6", "place": None},
             {"entry": "958", "horse": "H2", "rider": "R2", "trainer": "T2",
              "owner": "O2", "start": "7", "place": "1"}]}]
json.dump(mini, open(os.path.join(tmp, "refresh", "data.json"), "w"))
json.dump(mcache("48", {"1158": 1}), open(os.path.join(tmp, "refresh", "live_cache.json"), "w"))
json.dump({"fetched": "2026-08-24 09:20",
           "classes": [{"num": "48", "updated": "43 min", "updated_min": 43}]},
          open(os.path.join(tmp, "refresh", "live.json"), "w"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
check("build: exits 0", r.returncode == 0, r.stderr.strip())
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
c48 = b["classes"][0]
check("build: live gap filled from cache",
      c48["e"][0][6] == "1" and c48["e"][1][6] == "1")
check("build: live flag from fresh live.json", c48.get("live") == 43)

json.dump({"fetched": "2026-08-24 09:20",
           "classes": [{"num": "48", "updated": "2 hours, 2 min", "updated_min": 122}]},
          open(os.path.join(tmp, "refresh", "live.json"), "w"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
check("build: stale live class -> no flag", b["classes"][0].get("live") is None)

# missing live files -> exactly today's behavior (no live key at all)
os.remove(os.path.join(tmp, "refresh", "live_cache.json"))
os.remove(os.path.join(tmp, "refresh", "live.json"))
r = subprocess.run([sys.executable, os.path.join(tmp, "refresh", "build_page.py")],
                   capture_output=True, text=True)
b = json.loads(re.search(r"^(?:const|let) DATA = (\{.*\});\s*$",
                         open(os.path.join(tmp, "index.html")).read(), re.M).group(1))
check("build: no live files -> no merge, no flag",
      r.returncode == 0 and b["classes"][0]["e"][0][6] is None
      and "live" not in b["classes"][0])

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
