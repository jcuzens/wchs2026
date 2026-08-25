#!/usr/bin/env python3
"""Names shown on the page must be plain text: the show site's HTML escapes
entities in class names (&amp; &#39; &quot;) and the entry grids, and the page
renders everything via textContent, so any entity that reaches the payload
shows up literally. parse_entries.py must unescape class metadata (from
classes.json) exactly like it already unescapes entry cells."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARSE = os.path.join(ROOT, "refresh", "parse_entries.py")

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

ENTITY = re.compile(r"&[a-zA-Z][a-zA-Z0-9]*;|&#\d+;")

# --- fixture: a show page with escaped names, as fetched from the site ---
SCHED = [{"weekday": "Sunday", "period": "Morning", "date": "August 23",
          "time": "11:00 a.m.",
          "classes": [{"num": "1", "name": "Roadster Pony 50\" & Under"}]}]
CLASSES = [{"num": "1", "guid": "g-1",
            "name": "Roadster Pony 50&quot; &amp; Under Stake",
            "type": "UNDERSADDLE", "division": "Open &#39;Pony &#38; Pony&#39;"}]

def td(x):
    return "<td>%s</td>" % x

PLACED = ("<tr id=\"ctl_grPlacing_DXDataRow0\">"
          + td("1") + td("E-1") + td("Mac &amp; Doodle&#39;s Pony")
          + td("Tom &amp; Jerry") + td("USA") + td("Owner &amp; Co")
          + td("Trainer&#39;s Stables") + td("100") + td("")
          + td("1") + td("72.5") + td("98")
          + "</tr>")
NONPLACED = ("<tr id=\"ctl_grNonPlacing_DXDataRow0\">"
             + td("E-2") + td("Bella &#38; Biscuit") + td("Rider Two")
             + td("") + td("Owner Two") + td("") + td("")
             + td("2") + td("") + td("")
             + "</tr>")
PAGE = "<html><body>%s%s</body></html>" % (PLACED, NONPLACED)

tmp = tempfile.mkdtemp(prefix="names_")
os.makedirs(os.path.join(tmp, "entries"))
json.dump(SCHED, open(os.path.join(tmp, "schedule.json"), "w"))
json.dump(CLASSES, open(os.path.join(tmp, "classes.json"), "w"))
open(os.path.join(tmp, "entries", "1.html"), "w").write(PAGE)

r = subprocess.run([sys.executable, PARSE], cwd=tmp, capture_output=True, text=True)
check("parse_entries runs on fixture", r.returncode == 0, r.stderr.strip())
data = json.load(open(os.path.join(tmp, "data.json")))

c = data[0]
check("class name unescaped", c["name"] == 'Roadster Pony 50" & Under Stake', c["name"])
check("division unescaped", c["division"] == "Open 'Pony & Pony'", c["division"])
check("type untouched", c["type"] == "UNDERSADDLE", c["type"])
check("sched name passes through", c.get("sched_name") == 'Roadster Pony 50" & Under', c.get("sched_name"))

e0, e1 = c["entries"]
check("horse cell unescaped", e0["horse"] == "Mac & Doodle's Pony", e0["horse"])
check("rider cell unescaped", e0["rider"] == "Tom & Jerry", e0["rider"])
check("owner cell unescaped", e0["owner"] == "Owner & Co", e0["owner"])
check("trainer cell unescaped", e0["trainer"] == "Trainer's Stables", e0["trainer"])
check("non-placed horse cell unescaped", e1["horse"] == "Bella & Biscuit", e1["horse"])
check("no entities anywhere in data.json",
      not ENTITY.search(open(os.path.join(tmp, "data.json")).read()))

# --- the committed payload: same invariant, end to end ---
s = open(os.path.join(ROOT, "index.html")).read()
m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
check("payload embedded in index.html", m is not None)
if m:
    payload = m.group(1)
    bad = sorted({mm.group(0) for mm in ENTITY.finditer(payload)})
    check("no HTML entities in the embedded payload", not bad, ", ".join(bad))

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
