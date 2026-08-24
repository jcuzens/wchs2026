#!/usr/bin/env python3
"""Pure protocol + parse helpers for the show's Live Scores grid
(DevExpress ASPxGridView WebForms callbacks). No network I/O and no file
I/O here: fetch_live.py drives the requests, build_page.py does the merge.
Protocol details: docs/superpowers/specs/2026-08-24--live-scores-design.md
(section "Callback protocol")."""
import html as H
import json
import re

GRID_TR = re.compile(r'<tr id="[^"]*_grMain_DX[A-Za-z]')

def unescape_js(s):
    """Unescape a JS string-literal body (the response's result.html)."""
    return (s.replace("\\'", "'").replace("\\\\", "\\")
              .replace("\\n", "\n").replace("\\r", "\r").replace("\\/", "/"))

def clean_cell(x):
    """Strip tags, unescape entities, squash whitespace."""
    x = re.sub(r'<[^>]+>', '', x)
    return H.unescape(x).replace('\r', ' ').replace('\n', ' ').strip()

def top_rows(grid_html):
    """Split a grid's HTML into its top-level rows.

    Every top-level row (headers, DXADRow, DXDataRowN, DXDRowN) carries an
    id ending in _grMain_DX*; nested rows (progress bars, the detail
    sub-grids) have no ids and stay inside their parent row. Returns
    {row_id_suffix: row_html}.
    """
    marks = [m.start() for m in GRID_TR.finditer(grid_html)]
    rows = {}
    for a, b in zip(marks, marks[1:] + [len(grid_html)]):
        m = re.search(r'<tr id="([^"]+)"', grid_html[a:b])
        rows[m.group(1).rsplit('_grMain_', 1)[1]] = grid_html[a:b]
    return rows

def parse_parent_row(row):
    """Parse a class-summary row (DXDataRowN). Returns a dict with
    num, name, ring, ord, shown, total, placed, not_placed, updated,
    source (None when a cell is absent), or None when the row has no
    class name at all."""
    name_m = re.search(r'dxeBase[^>]*>\s*([^<]+?)\s*<', row)
    if not name_m:
        return None
    name = H.unescape(name_m.group(1)).strip()
    tci = row.find('tccell')   # the name+progress cell; its tag starts with an id, so the plain-cell regex below skips it
    tail = [clean_cell(t) for t in re.findall(r'<td class="dxgv"[^>]*>([^<]*)</td>', row[tci:])]

    def toi(x):
        x = (x or '').strip()
        return int(x) if x.isdigit() else None

    prog = re.search(r'(\d+)\s*/\s*(\d+)', row)
    cells = re.findall(r'<td class="dxgv"[^>]*>([^<]*)</td>', row)
    return {
        "num": name.split(' - ')[0].strip(),
        "name": name,
        "ring": clean_cell(cells[0]) if cells else None,
        "ord": toi(cells[1]) if len(cells) > 1 else None,
        "shown": int(prog.group(1)) if prog else None,
        "total": int(prog.group(2)) if prog else None,
        "placed": toi(tail[0]) if len(tail) > 0 else None,
        "not_placed": toi(tail[1]) if len(tail) > 1 else None,
        "updated": tail[2] if len(tail) > 2 else None,
        "source": tail[3] if len(tail) > 3 else None,
    }

def parse_detail_entries(detail_row):
    """Parse the placed-entries sub-grid (grPlaced_*) of a detail row into
    [entry, horse, rider, ord, place] rows. The grNonPlaced sub-grid is
    ignored (no placings)."""
    entries = []
    pm = [m.start() for m in re.finditer(r'<tr id="[^"]*grPlaced_\d+_(DXDataRow\d+)"', detail_row)]
    for a, b in zip(pm, pm[1:] + [len(detail_row)]):
        row = detail_row[a:b]

        def sp(nm):
            m = re.search(r'id="[^"]*' + nm + r'_\d+"[^>]*>([^<]+)<', row)
            return H.unescape(m.group(1)).strip() if m else None

        rider = re.search(r'<td class="dxgv" style="font-weight:bold;">([^<]+)</td>', row)
        nums = re.findall(r'<td class="dxgv" align="right" style="font-weight:bold;">([^<]+)</td>', row)
        entries.append([
            sp("lbEntryNo"),
            sp("lbEntryName"),
            H.unescape(rider.group(1)).strip() if rider else None,
            int(nums[0]) if len(nums) > 0 else None,
            int(nums[1]) if len(nums) > 1 else None,
        ])
    return entries

def parse_envelope_state(response):
    """keys/callbackState/groupLevelState from a callback response's
    envelope stateObject — the source of truth for the next request. The
    response HTML must not be used: it re-initializes the main grid via
    PostponeInitialize (no createControl) and also embeds the detail
    sub-grids' own state objects."""
    m = re.search(r"'stateObject':", response)
    if not m:
        return None
    k = response.find('{', m.end())
    depth = 0
    for i in range(k, len(response)):
        c = response[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
    lit = response[k:i + 1]
    keys = re.findall(r"'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'", lit)
    cb_m = re.search(r"'callbackState':'([^']+)'", lit)
    gl_m = re.search(r"'groupLevelState':(\{[^}]*\})", lit)
    if not cb_m:
        return None
    return {"keys": keys, "callbackState": cb_m.group(1),
            "groupLevelState": gl_m.group(1) if gl_m else "{}"}

def response_html(response):
    """Unescaped result.html of a callback response; None when the
    envelope is a fault (generalError / error.message) or malformed."""
    if re.search(r"'generalError':", response) or re.search(r"'message':", response):
        return None
    m = re.search(r"'html':'((?:[^'\\]|\\.)*)'", response)
    return unescape_js(m.group(1)) if m else None

def parse_get_page(page):
    """Bootstrap state from a GET of LiveScoring.aspx: the grid's callback
    id, all form fields (DOM order), and the grid's stateObject. Returns
    None when the page has no grid block (dead session / login shell)."""
    m = re.search(r"ASPx\.createControl\(ASPxClientGridView,'([^']+)'", page)
    if not m:
        return None
    js_name = m.group(1)
    i2 = page.find("ASPx.createControl(ASPxClientGridView,'" + js_name + "'")
    cb_m = re.search(r"WebForm_DoCallback\('([^']+)'", page[i2:i2 + 800])
    if not cb_m:
        return None
    j2 = page.find('stateObject', i2)
    seg = page[j2:j2 + 400000]
    keys_m = re.search(r"'keys':\[(.*?)\]", seg)
    cb2 = re.search(r"'callbackState':'([^']+)'", seg)
    if not keys_m or not cb2:
        return None
    gl_m = re.search(r"'groupLevelState':(\{[^}]*\})", seg)
    fields = []
    fi = page.find('<form')
    fj = page.find('</form>', fi)
    for fm in re.finditer(r'<(?:input|select|textarea)[^>]*?(?:/>|>)', page[fi:fj], re.S):
        tag = fm.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        if not n:
            continue
        typ_m = re.search(r'type="([^"]+)"', tag)
        typ = typ_m.group(1) if typ_m else ''
        if typ in ('checkbox', 'radio') and 'checked' not in tag:
            continue
        if typ in ('submit', 'button', 'image', 'reset', 'file'):
            continue
        v = re.search(r'value="([^"]+)"', tag)
        fields.append((n.group(1), H.unescape(v.group(1)) if v else ''))
    return {
        "callback_id": cb_m.group(1),
        "fields": fields,
        "keys": re.findall(r"'([^']+)'", keys_m.group(1)),
        "callbackState": cb2.group(1),
        "groupLevelState": gl_m.group(1) if gl_m else "{}",
    }

def grid_state_field(callback_id, state):
    """(name, value) for the grid's hidden state input. The grid renders
    this hidden input (named with its uniqueID) at JS runtime; the server
    needs it on every callback. Value is HTML-escaped compact JSON."""
    gs = H.escape(json.dumps({"keys": state["keys"],
                              "groupLevelState": json.loads(state["groupLevelState"]),
                              "callbackState": state["callbackState"],
                              "focusedRow": 0, "selection": "", "toolbar": "{}"},
                             separators=(',', ':')), quote=True)
    return (callback_id, gs)

def build_param(state, key):
    """__CALLBACKPARAM for a SHOWDETAILROW callback on row key `key`.
    The c0: prefix and the FR/CT segments are required by the server."""
    kv = json.dumps(state["keys"], separators=(',', ':'))
    ser = "13|SHOWDETAILROW%d|%s" % (len(key), key)
    return ("c0:" + "KV|%d;%s;" % (len(kv), kv)
            + "FR|1;0;" + "CT|2;{};" + "GB|%d;%s;" % (len(ser), ser))

def merge_live_places(classes, cache):
    """In place: fill e[6] from the live cache where the official place is
    missing. Official places are never overwritten; class numbers absent
    from the cache (including live sub-classes the page doesn't know) are
    untouched."""
    for c in classes:
        cc = cache.get(c["n"])
        if not cc:
            continue
        for e in c["e"]:
            if e[6] is None and e[0] in cc:
                e[6] = str(cc[e[0]]["p"])
    return classes

def fold_live_cache(cache, live):
    """In place: fold a live.json payload into the accumulating cache.
    Grows only — no deletes during the show; re-folding is idempotent."""
    fetched = live.get("fetched", "")
    for c in live.get("classes", []):
        cls = cache.setdefault(c["num"], {})
        for entry, _horse, _rider, place in c.get("entries", []):
            cls[str(entry)] = {"p": place, "at": fetched}
    return cache

def updated_to_minutes(s):
    """'53 min' -> 53; '1 hour, 51 min' -> 111; '2 hours, 2 min' -> 122;
    'Just now' -> 0; None/''/unparseable -> None."""
    if not s:
        return None
    s = s.lower()
    if 'just now' in s:
        return 0
    h = re.search(r'(\d+)\s*hours?', s)
    m = re.search(r'(\d+)\s*min', s)
    if not h and not m:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
