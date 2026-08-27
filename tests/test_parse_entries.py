#!/usr/bin/env python3
"""parse_entries: one record per class, and the class number comes from the
page's own 'Class: N' detail label (a split section page parsed as 89.2,
not as its file name). Sections inherit the parent's schedule slot. After a
split, the parent page (114.html) and the section page (114.1.html) can both
label themselves with the section number: exactly one record is kept."""
import json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import parse_entries as pe

# A split-section page: detail label says 89.2 (whatever the file name was),
# one placed entry, one non-placed.
SECTION_PAGE = """
<html><body>
<span class="dxeBase bold" id="ctl00_dxdt230_grPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1</td><td>1044</td><td>WA-SO FAR LUCKY</td><td>WALKER, DARIEN</td><td></td>
<td>WALKER, DARIEN</td><td>SIMPSON, AMANDA</td><td>$360.00</td><td>$0.00</td>
<td>6</td><td>0.000</td><td>0.000</td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
<span class="dxeBase bold" id="ctl00_dxdt230_grNonPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grNonPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1050</td><td>HORSE B</td><td>RIDER B</td><td></td><td>OWNER B</td>
<td>TRAINER B</td><td>$0.00</td><td>7</td><td></td><td></td><td>&nbsp;</td>
<td>&nbsp;</td></tr>
</table>
</body></html>
"""

CLASSES = {
    "89.2": {"num": "89.2", "name": "Ladies Roadster to Bike Section 2",
             "guid": "g", "type": "UNDERSADDLE", "division": "Roadster", "entries": "9"},
}
# only the PARENT has a schedule slot; sections inherit it
SCHED_LOOKUP = {
    "89": {"weekday": "Tuesday", "period": "Morning", "date": "August 25",
           "time": "9:00 a.m.", "sched_name": "Ladies Roadster to Bike"},
}

# 1. the page's own detail label is the class number
check("page_class_num reads the detail label", pe.page_class_num(SECTION_PAGE) == "89.2",
      str(pe.page_class_num(SECTION_PAGE)))
check("page_class_num is None without a label",
      pe.page_class_num("<html><body>no detail here</body></html>") is None)

# 2. a section page yields a record for 89.2, named from the class list,
#    with the parent's schedule slot
rec = pe.parse_page(SECTION_PAGE, "89", CLASSES, SCHED_LOOKUP)
check("record num comes from the page label, not the file name",
      rec and rec["num"] == "89.2", str(rec and rec["num"]))
check("record name/type/division come from the class list entry",
      rec and rec["name"] == "Ladies Roadster to Bike Section 2"
      and rec["type"] == "UNDERSADDLE" and rec["division"] == "Roadster",
      str(rec and (rec["name"], rec["type"], rec["division"])))
check("record entries: placed + non-placed",
      rec and len(rec["entries"]) == 2
      and rec["entries"][0]["place"] == "1" and rec["entries"][0]["entry"] == "1044"
      and rec["entries"][1]["place"] is None and rec["entries"][1]["entry"] == "1050",
      str(rec and rec["entries"]))
check("section inherits the parent's schedule slot",
      rec and rec.get("weekday") == "Tuesday" and rec.get("period") == "Morning"
      and rec.get("date") == "August 25" and rec.get("time") == "9:00 a.m."
      and rec.get("sched_name") == "Ladies Roadster to Bike",
      str(rec))

# 3. a page without a label falls back to the file name (existing behavior)
NO_LABEL = SECTION_PAGE.replace("Class:       89.2", "Classless")
rec = pe.parse_page(NO_LABEL, "99", {"99": {"num": "99", "name": "Plain Class",
                                            "guid": "g", "type": "UNDERSADDLE",
                                            "division": "ASB", "entries": "2"}}, {})
check("no label -> file name used", rec and rec["num"] == "99"
      and rec["name"] == "Plain Class", str(rec and rec["num"]))
check("no schedule slot -> no weekday keys", rec and "weekday" not in rec)

# 4. a page for a class no longer in the master grid is stale and yields no
#    record: the grid is the class universe. A pre-split parent page (114,
#    fetched before the show split it into 114.1/114.2) is exactly this case;
#    its entries now live in the section pages, and a record for 114 would
#    carry null name/division.
PARENT_PAGE = SECTION_PAGE.replace("89.2", "114")
SPLIT_CLASSES = {
    "114.1": {"num": "114.1", "name": "ASB Country Pleasure Driving Div I Sec 1",
              "guid": "g1", "type": "UNDERSADDLE", "division": "ASB", "entries": "9"},
    "114.2": {"num": "114.2", "name": "ASB Country Pleasure Driving Div I Sec 2",
              "guid": "g2", "type": "UNDERSADDLE", "division": "ASB", "entries": "6"},
}
rec = pe.parse_page(PARENT_PAGE, "114", SPLIT_CLASSES,
                    {"114": {"weekday": "Wednesday", "period": "Morning",
                             "date": "August 26", "time": "9:00 a.m.",
                             "sched_name": "ASB Country Pleasure Driving Div I"}})
check("class not in master grid -> no record (stale pre-split parent page)",
      rec is None, str(rec and rec["num"]))

# 5. a split class fetched as TWO pages that both label themselves with the
#    section number: the parent page (114.html, which the site now serves as
#    section 1) and the section page (114.1.html). One record per class, from
#    the canonical page (file name == class number), even when the parent
#    page was fetched more recently.
PLACED_1141 = SECTION_PAGE.replace("89.2", "114.1")
LISTONLY_1141 = re.sub(
    r'<table>\s*<tr id="ctl00_dxdt230_grPlacing_DXDataRow\d+".*?</tr>\s*</table>',
    '', PLACED_1141, flags=re.S)
SCHED_114 = [{"weekday": "Wednesday", "period": "Morning", "date": "August 26",
              "time": "9:00 a.m.",
              "classes": [{"num": "114",
                           "name": "ASB Country Pleasure Driving Div I"}]}]

def run_main(tmp, pages, classes, sched, mtimes=None):
    mtimes = mtimes or {}
    os.makedirs(os.path.join(tmp, "entries"), exist_ok=True)
    for name, content in pages.items():
        p = os.path.join(tmp, "entries", name)
        open(p, "w").write(content)
        if name in mtimes:
            os.utime(p, (mtimes[name], mtimes[name]))
    open(os.path.join(tmp, "classes.json"), "w").write(
        json.dumps(list(classes.values())))
    open(os.path.join(tmp, "schedule.json"), "w").write(json.dumps(sched))
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        pe.main()
        return json.load(open("data.json"))
    finally:
        os.chdir(cwd)

tmp = tempfile.mkdtemp(prefix="pe_dup_")
try:
    # parent page fetched AFTER the section page (mtime 200 > 100): the
    # canonical file name must still win, and it carries the placings
    data = run_main(
        tmp,
        {"114.html": LISTONLY_1141, "114.1.html": PLACED_1141,
         "114.2.html": SECTION_PAGE.replace("89.2", "114.2")},
        SPLIT_CLASSES, SCHED_114,
        mtimes={"114.html": 200, "114.1.html": 100, "114.2.html": 100})
    nums = sorted(c["num"] for c in data)
    check("parent + section page for the same class -> one record per class",
          nums == ["114.1", "114.2"], str(nums))
    r1141 = next((c for c in data if c["num"] == "114.1"), None)
    check("the kept 114.1 record is the canonical section page (has placings)",
          r1141 is not None
          and any(e["place"] == "1" and e["entry"] == "1044" for e in r1141["entries"])
          and len(r1141["entries"]) == 2, str(r1141 and r1141["entries"]))
finally:
    shutil.rmtree(tmp)

tmp = tempfile.mkdtemp(prefix="pe_dup_")
try:
    # neither file name is canonical -> the newest fetch wins
    data = run_main(
        tmp,
        {"114.html": PLACED_1141, "999.html": LISTONLY_1141},
        SPLIT_CLASSES, SCHED_114,
        mtimes={"114.html": 100, "999.html": 200})
    nums = sorted(c["num"] for c in data)
    check("two pages labeled the same class -> one record",
          nums == ["114.1"], str(nums))
    r1141 = next((c for c in data if c["num"] == "114.1"), None)
    check("neither file canonical -> newest fetch wins (no placings here)",
          r1141 is not None
          and not any(e["place"] for e in r1141["entries"])
          and len(r1141["entries"]) == 1, str(r1141 and r1141["entries"]))
finally:
    shutil.rmtree(tmp)

# 6. scratch rows: the show site marks withdrawn entries with a LightPink +
#    line-through <tr> style; exactly those entries are flagged (both grids)
SCRATCH_PAGE = """
<html><body>
<span class="dxeBase bold" id="ctl00_dxdt230_grPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1</td><td>1044</td><td>WA-SO FAR LUCKY</td><td>WALKER, DARIEN</td><td></td>
<td>WALKER, DARIEN</td><td>SIMPSON, AMANDA</td><td>$360.00</td><td>$0.00</td>
<td>6</td><td>0.000</td><td>0.000</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr id="ctl00_dxdt230_grPlacing_DXDataRow1" class="dxgvDataRow_Office2010Blue"
 style="background-color:LightPink;font-size:8pt;text-decoration: line-through;">
<td>5</td><td>1060</td><td>SCRATCHED PLACED</td><td>SP, RIDER</td><td></td>
<td>SP, OWNER</td><td>SP, TRAINER</td><td>$0.00</td><td>$0.00</td>
<td>4</td><td>0.000</td><td>0.000</td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
<span class="dxeBase bold" id="ctl00_dxdt230_grNonPlacing_Title_ASPxLabel3" style="font-size:12pt;">Class:       89.2</span>
<table>
<tr id="ctl00_dxdt230_grNonPlacing_DXDataRow0" class="dxgvDataRow_Office2010Blue">
<td>1050</td><td>HORSE B</td><td>RIDER B</td><td></td><td>OWNER B</td>
<td>TRAINER B</td><td>$0.00</td><td>7</td><td></td><td></td><td>&nbsp;</td>
<td>&nbsp;</td></tr>
<tr id="ctl00_dxdt230_grNonPlacing_DXDataRow1" class="dxgvDataRow_Office2010Blue"
 style="background-color:LightPink;font-size:8pt;text-decoration: line-through;">
<td>1055</td><td>SCRATCH HORSE</td><td>SCRATCH RIDER</td><td></td>
<td>OWNER S</td><td>TRAINER S</td><td>$0.00</td><td>9</td>
<td></td><td></td><td>&nbsp;</td><td>&nbsp;</td></tr>
</table>
</body></html>
"""
rec = pe.parse_page(SCRATCH_PAGE, "89", CLASSES, SCHED_LOOKUP)
scratched = sorted(e["entry"] for e in rec["entries"] if e.get("scratch") is True)
check("exactly the line-through rows carry scratch=True",
      rec is not None and scratched == ["1055", "1060"], str(scratched))
check("plain rows carry no scratch key",
      rec is not None and all("scratch" not in e for e in rec["entries"]
                              if e["entry"] not in ("1055", "1060")),
      str(rec and rec["entries"]))

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
