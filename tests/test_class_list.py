#!/usr/bin/env python3
"""Live class list (refresh/class_list.py): the master grid on any class
page is the show's authoritative class list (split sections like 89.1/89.2
are separate classes, each with its own ClassGUID as the row key). The
parser reads rows + row keys and update_classes_json rewrites
classes.json only when the list changed."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import class_list as cl

def mkrow(idx, num, name, typ, div, entries, placed):
    return ('<tr id="ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster_DXDataRow%d" '
            'class="dxgvDataRow_Office2010Blue">'
            '<td class="dxgvDetailButton_Office2010Blue dxgv dxgvDBC" style="width:1px;border-right-width:0px;">'
            '<img class="dxGridView_gvDetailCollapsedButton_Office2010Blue" onclick="ASPx.GVShowDetailRow(&#39;ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster&#39;,%d,event);event.cancelBubble = true" src="/DXR.axd?r=1" alt="Expand" style="cursor:pointer;" /></td>'
            '<td class="dxgvCommandColumn_Office2010Blue dxgv" align="center">&nbsp;</td>'
            '<td class="dxgv" align="right">      %s</td><td class="dxgv">%s</td><td class="dxgv">%s</td>'
            '<td class="dxgv"><a class="dxeHyperlink_Office2010Blue" href="DivisionResults.aspx?DivisionGUID=x">%s</a></td>'
            '<td class="dxgv" align="right">%s</td><td class="dxgv" align="right" style="border-right-width:0px;">%s</td>'
            '</tr>') % (idx, idx, num, name, typ, div, entries, placed)

def mkpage(rows, keys, subgrid_rows=()):
    """rows: (num, name, type, division, entries, placed) tuples; keys: the
    grMaster stateObject key list (one per row, in row order)."""
    body = "\n".join(mkrow(i, *r) for i, r in enumerate(rows))
    body += "\n" + "\n".join(subgrid_rows)
    return (
        '<html><body><table><tr id="ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster_DXHeadersRow0"><th>h</th></tr>'
        + body +
        '</table><script>'
        "ASPx.createControl(ASPxClientGridView,'ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster',"
        "'',{'callBack':function(arg) { WebForm_DoCallback('ctl00$ctl00$MainContent$panContentRight$ContentShow$grMaster',arg,ASPx.Callback,'ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster',ASPx.CallbackError,true); },"
        "'uniqueID':'ctl00$ctl00$MainContent$panContentRight$ContentShow$grMaster',"
        "'stateObject':{'keys':[" + ",".join("'%s'" % k for k in keys) + "],'callbackState':'xyz','groupLevelState':{}}});"
        "</script></body></html>"
    )

SUBGRID_ROW = ('<tr id="ctl00_ctl00_MainContent_panContentRight_ContentShow_grMaster_dxdt5_grPlacing_DXDataRow0">'
               '<td>1</td><td>12</td></tr>')

KEYS = ["%08d-0000-4000-8000-%012d" % (i, i) for i in range(10)]
ROWS = [
    ("89.1", "Ladies Roadster to Bike Section 1", "UNDERSADDLE", "Roadster", "17", "8"),
    ("89.2", "Ladies Roadster to Bike Section 2", "UNDERSADDLE", "Roadster", "9", "&nbsp;"),
    ("33.1", 'Amateur Roadster Pony Over 50&quot; to 52&quot; Sec 1', "UNDERSADDLE", "Roadster Pony", "&nbsp;", "&nbsp;"),
]
PAGE = mkpage(ROWS, KEYS, (SUBGRID_ROW,))

# 1. row keys from the master grid's stateObject (row order = key order)
check("master_grid_keys returns the key list",
      cl.master_grid_keys(PAGE) == KEYS)

# 2. rows: cells -> fields, entities unescaped, &nbsp; counts -> None,
#    guid = key at the row index
got = cl.parse_master_grid(PAGE)
check("parse_master_grid row count (sub-grid row ignored)", len(got) == 3, str(len(got)))
check("parse_master_grid first row", got and got[0] == {
    "num": "89.1", "name": "Ladies Roadster to Bike Section 1",
    "type": "UNDERSADDLE", "division": "Roadster",
    "entries": "17", "placed": "8", "guid": KEYS[0]},
    str(got[0] if got else None))
check("parse_master_grid unescapes entities in the name",
      got and got[2]["name"] == 'Amateur Roadster Pony Over 50" to 52" Sec 1',
      got[2]["name"] if got else "")
check("parse_master_grid maps &nbsp; counts to None",
      got and got[2]["entries"] is None and got[2]["placed"] is None)
check("parse_master_grid guid follows the row index",
      got and got[1]["guid"] == KEYS[1])

# 3. no master grid (no-entries page) -> no keys, no rows
NOENTRY = "<html><body><div>No entries</div></body></html>"
check("master_grid_keys is None without a grid", cl.master_grid_keys(NOENTRY) is None)
check("parse_master_grid is empty without a grid", cl.parse_master_grid(NOENTRY) == [])

# 4. defensive: a row beyond the key list is skipped, the rest survive
SHORT = mkpage(ROWS, KEYS[:2])
got = cl.parse_master_grid(SHORT)
check("row without a key is skipped", [r["num"] for r in got] == ["89.1", "89.2"],
      str([r["num"] for r in got]))

def dump(rows, keys):
    """(num, name, type, division, entries, placed) tuples -> classes.json
    format (names unescaped, &nbsp; counts -> None, as the parser stores
    them)."""
    import html as H
    def cnt(x):
        x = H.unescape(x).strip()
        return x or None
    return [{"num": r[0], "name": H.unescape(r[1]), "guid": keys[i],
             "type": r[2], "division": r[3], "entries": cnt(r[4])}
            for i, r in enumerate(rows)]

tmp = tempfile.mkdtemp(prefix="class_list_")

# 5. update_classes_json: unchanged list -> no rewrite
p = os.path.join(tmp, "classes.json")
json.dump(dump(ROWS, KEYS), open(p, "w"), indent=1)
before = open(p).read()
check("identical list leaves classes.json untouched",
      cl.update_classes_json(p, cl.parse_master_grid(PAGE)) == "unchanged"
      and open(p).read() == before)

# 6. update_classes_json: changed list -> rewrite in the file schema
rows2 = ROWS + [("97.2", "Youth Roadster to Bike 15-21 Years Old Section 2",
                 "UNDERSADDLE", "Roadster", "6", "5")]
PAGE2 = mkpage(rows2, KEYS[:4])
check("changed list rewrites classes.json",
      cl.update_classes_json(p, cl.parse_master_grid(PAGE2)) == "changed")
new = json.load(open(p))
check("rewritten list has the new row",
      [c["num"] for c in new] == ["89.1", "89.2", "33.1", "97.2"]
      and new[3]["guid"] == KEYS[3] and new[3]["entries"] == "6", str(new[-1]))
check("rewrite uses the classes.json schema (indent 1)",
      open(p).read() == json.dumps(new, indent=1))

# 7. CLI: no grid -> rc 1, classes.json untouched; changed -> rc 3; same -> rc 0
pg = os.path.join(tmp, "page.html")
open(pg, "w").write(NOENTRY)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "class_list.py"),
                    pg, "--classes", p], capture_output=True, text=True)
check("cli rc 1 for a page without a grid", r.returncode == 1, str(r.returncode) + r.stderr)
check("cli leaves classes.json untouched on error", json.load(open(p)) == new)
open(pg, "w").write(PAGE2)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "class_list.py"),
                    pg, "--classes", p], capture_output=True, text=True)
check("cli rc 0 when the list is already current", r.returncode == 0,
      str(r.returncode) + r.stderr)
open(pg, "w").write(PAGE)
r = subprocess.run([sys.executable, os.path.join(ROOT, "refresh", "class_list.py"),
                    pg, "--classes", p], capture_output=True, text=True)
check("cli rc 3 when the list changed", r.returncode == 3, str(r.returncode) + r.stderr)
check("cli change reported on stdout", "97.2" in r.stdout, r.stdout)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
