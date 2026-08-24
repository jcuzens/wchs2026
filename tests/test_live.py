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

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
