#!/usr/bin/env python3
"""Judge scorecards: refresh/fetch_scorecards.py parses the show's public
Google Drive folder page (file rows carry data-id="FILEID" and the file
name in a title aria-label) into refresh/scorecards.json; build_page.py
stamps payload classes with a "card" URL. A parse that finds zero cards
must never wipe a good cache (login wall / page redesign)."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(ROOT, "refresh")
sys.path.insert(0, REF)

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

# ---- parse_folder_html (fixture shaped like the real folder page) ----
import fetch_scorecards as fs

def row(fid, name, kind="PDF"):
    return ('<tr data-selectable data-id="%s" data-selection-key="0" data-target="doc" '
            'class="qwPkcb eZp0ce" aria-selected="false" role="row" draggable="true">'
            '<div class="JxSEve" aria-label="%s %s Shared" data-handled-by-drag-and-drop="true">'
            '<i role="presentation"></i><i role="presentation"></i></div>'
            '<span aria-label="Shared"></span><span aria-label="Modified Aug 22"></span>'
            '</tr>') % (fid, name, kind)

FIX = ('<html><body><table><tbody>' +
       row("a" * 33, "CLASS 1.pdf") +
       row("b" * 33, "CLASS 10.1.pdf") +
       row("c" * 33, "Old Scores", "FOLDER") +
       row("d" * 33, "Show Program.pdf") +
       '</tbody></table></body></html>')

cards = fs.parse_folder_html(FIX)
check("parse: class numbers from CLASS N.pdf names",
      cards.get("1") == "a" * 33 and cards.get("10.1") == "b" * 33, json.dumps(cards))
check("parse: folder and non-class files ignored", set(cards) == {"1", "10.1"}, json.dumps(cards))
check("parse: empty page -> empty dict", fs.parse_folder_html("<html></html>") == {})
check("parse: name match is case-insensitive",
      fs.parse_folder_html(row("e" * 33, "class 2.pdf")).get("2") == "e" * 33)

# ---- main(): fetch failure / empty parse must not wipe a good cache ----
tmp = tempfile.mkdtemp(prefix="wchs-sc-")
out = os.path.join(tmp, "scorecards.json")
json.dump({"fetched": "x", "cards": {"1": "keepme"}}, open(out, "w"))
rc = fs.main(fetch=lambda url: "<html></html>", out=out)
check("main: empty parse keeps existing cache (rc 1)",
      rc == 1 and json.load(open(out))["cards"] == {"1": "keepme"})
rc = fs.main(fetch=lambda url: FIX, out=out)
check("main: good parse rewrites the file (rc 0)",
      rc == 0 and set(json.load(open(out))["cards"]) == {"1", "10.1"},
      "rc=%s" % rc)
out2 = os.path.join(tmp, "empty-first.json")
rc = fs.main(fetch=lambda url: "<html></html>", out=out2)
check("main: first run with empty folder writes an empty cache",
      rc == 0 and json.load(open(out2))["cards"] == {}, "rc=%s" % rc)
def boom(url):
    raise OSError("network down")
out3 = os.path.join(tmp, "netdown.json")
json.dump({"fetched": "x", "cards": {"1": "keepme"}}, open(out3, "w"))
rc = fs.main(fetch=boom, out=out3)
check("main: fetch failure keeps existing cache (rc 1)",
      rc == 1 and json.load(open(out3))["cards"] == {"1": "keepme"}, "rc=%s" % rc)

# ---- build_page.py merges scorecards.json into the payload (sandbox) ----
def sandbox(cards=None):
    t = tempfile.mkdtemp(prefix="wchs-sc-build-")
    sref = os.path.join(t, "refresh")
    os.makedirs(sref)
    for f in ("build_page.py", "predict.py", "live_scores.py", "select_frontier.py",
              "data.json", "classes.json", "schedule.json"):
        shutil.copyfile(os.path.join(REF, f), os.path.join(sref, f))
    if cards is not None:
        json.dump({"fetched": "2026-08-28 12:00", "cards": cards},
                  open(os.path.join(sref, "scorecards.json"), "w"))
    subprocess.run([sys.executable, os.path.join(sref, "build_page.py")],
                   check=True, cwd=sref, stdout=subprocess.DEVNULL)
    return t

data_nums = [c["num"] for c in json.load(open(os.path.join(REF, "data.json")))]
SEC = next((n for n in data_nums if "." in n), None)
assert SEC, "no section class (x.y) in data.json; test needs one"

tA = sandbox()
plA = json.load(open(os.path.join(tA, "payload.json")))
check("build: no scorecards.json -> no card keys",
      all("card" not in c for c in plA["classes"]))

tB = sandbox({"1": "ZID1", SEC: "ZID2"})
plB = json.load(open(os.path.join(tB, "payload.json")))
b1 = next(c for c in plB["classes"] if c["n"] == "1")
bsec = next(c for c in plB["classes"] if c["n"] == SEC)
check("build: card URL stamped on the class",
      b1.get("card") == "https://drive.google.com/file/d/ZID1/view",
      json.dumps(b1.get("card")))
check("build: section class gets its own card",
      bsec.get("card") == "https://drive.google.com/file/d/ZID2/view")
check("build: no card key on other classes",
      all("card" not in c for c in plB["classes"] if c["n"] not in ("1", SEC)))
tC = sandbox({"999.9": "ZIDX"})
check("build: card for an unknown class is a no-op",
      all("card" not in c for c in
          json.load(open(os.path.join(tC, "payload.json")))["classes"]))

plj = os.path.join(tB, "payload.json")
idx = os.path.join(tB, "index.html")
first_plj, first_idx = open(plj).read(), open(idx).read()
subprocess.run([sys.executable, os.path.join(tB, "refresh", "build_page.py")],
               check=True, cwd=os.path.join(tB, "refresh"), stdout=subprocess.DEVNULL)
check("build: unchanged rebuild is byte-identical (asof policy)",
      open(plj).read() == first_plj and open(idx).read() == first_idx)

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(tA, ignore_errors=True)
shutil.rmtree(tB, ignore_errors=True)
shutil.rmtree(tC, ignore_errors=True)

if fails:
    print("%d FAILURES: %s" % (len(fails), fails))
    sys.exit(1)
print("all scorecard tests passed")
