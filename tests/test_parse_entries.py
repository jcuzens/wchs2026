#!/usr/bin/env python3
"""parse_entries: one record per class, and the class number comes from the
page's own 'Class: N' detail label (a split section page parsed as 89.2,
not as its file name). Sections inherit the parent's schedule slot."""
import os, sys

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

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
