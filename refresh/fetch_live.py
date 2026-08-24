#!/usr/bin/env python3
"""Fetch the show's Live Scores grid (summary + per-class placed entries)
via the DevExpress ASPxGridView callback protocol.

The detail view is an accordion: the server keeps at most one detail row
expanded per response, so the fetcher sends one SHOWDETAILROW callback per
row key and parses that row's placed entries from the response. Each
response also re-renders every parent row (ring/ord/progress/placed/
updated/source), so parent info is collected from all responses. New
classes can join the window mid-run (the show is live), so the key set is
re-checked from each response's envelope and the loop repeats until stable.

Writes refresh/live.json. On any failure exits non-zero and leaves
live.json (and live_cache.json) untouched, so the page degrades to
official-only data. Uses refresh/jar.txt (same session as fetch_entries.sh).

Protocol details: docs/superpowers/specs/2026-08-24--live-scores-design.md
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_scores as ls

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SHOW_GUID = "46c298a5-6bac-44e0-a711-56695c992e12"
SHOW_URL = "https://horseshowsonline.com/ShowDetails?ShowGUID=" + SHOW_GUID
LIVE_URL = "https://horseshowsonline.com/LiveScoring.aspx?ShowGUID=" + SHOW_GUID
JAR = os.path.join(HERE, "jar.txt")
LIVE_JSON = os.path.join(HERE, "live.json")
PACING = 0.7      # seconds between callbacks
MAX_ROUNDS = 5    # bound on key-set re-check rounds


def enc(x):
    return urllib.parse.quote(str(x), safe='')


def num_key(n):
    return tuple(int(p) for p in n.split('.'))


def main():
    if not os.path.exists(JAR):
        sys.exit("fetch_live.py: no %s (run fetch_entries.sh first)" % JAR)
    cj = http.cookiejar.MozillaCookieJar(JAR)
    cj.load(ignore_discard=True, ignore_expires=True)
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UA)]

    def http_get(url):
        return op.open(url, timeout=90).read().decode('utf-8', 'replace')

    def http_post(url, body):
        req = urllib.request.Request(
            url, data=body,
            headers={'User-Agent': UA,
                     'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'})
        return op.open(req, timeout=120).read().decode('utf-8', 'replace')

    http_get(SHOW_URL)  # session warm-up (mirrors fetch_entries.sh)
    boot = ls.parse_get_page(http_get(LIVE_URL))
    if not boot:
        sys.exit("fetch_live.py: no grid in LiveScoring.aspx (dead session?)")
    fields = boot["fields"]
    ev = dict(fields).get("__EVENTVALIDATION", "")
    state = {"keys": boot["keys"], "callbackState": boot["callbackState"],
             "groupLevelState": boot["groupLevelState"]}

    classes = {}
    expanded = set()
    for _round in range(MAX_ROUNDS):
        pending = [k for k in state["keys"] if k not in expanded]
        if not pending:
            break
        for key in pending:
            name, val = ls.grid_state_field(boot["callback_id"], state)
            body = ("&".join("%s=%s" % (enc(k), enc(v))
                             for k, v in [(name, val)] + fields if k != "__EVENTVALIDATION")
                    + "&__CALLBACKID=" + enc(boot["callback_id"])
                    + "&__CALLBACKPARAM=" + enc(ls.build_param(state, key))
                    + "&__EVENTVALIDATION=" + enc(ev)).encode()
            resp = http_post(LIVE_URL, body)
            html = ls.response_html(resp)
            if html is None:
                m = (re.search(r"'generalError':'([^']*)'", resp)
                     or re.search(r"'message':'([^']*)'", resp))
                sys.exit("fetch_live.py: callback failed: %s"
                         % (m.group(1) if m else "unknown envelope"))
            ns = ls.parse_envelope_state(resp)
            if ns:
                state = ns
            rows = ls.top_rows(html)
            for rk, row in rows.items():
                if re.match(r'DXDataRow\d+$', rk):
                    info = ls.parse_parent_row(row)
                    if info:
                        prev = classes.get(info["num"])
                        # a later response re-renders this row without its
                        # detail; keep entries already collected for it
                        if prev and prev.get("entries") and not info.get("entries"):
                            info["entries"] = prev["entries"]
                        classes[info["num"]] = info
            detail = next((row for rk, row in rows.items()
                           if rk.startswith('DXDRow')), None)
            if detail:
                try:
                    kidx = state["keys"].index(key)
                    prow = rows.get("DXDataRow%d" % kidx)
                    info = ls.parse_parent_row(prow) if prow else None
                    if info:
                        info["entries"] = ls.parse_detail_entries(detail)
                        classes[info["num"]] = info
                except ValueError:
                    pass  # row left the window mid-flight; parent already captured
            expanded.add(key)
            time.sleep(PACING)
        if set(state["keys"]) <= expanded:
            break

    out_classes = []
    for num in sorted(classes, key=num_key):
        c = classes[num]
        out_classes.append({
            "num": c["num"], "name": c["name"], "ring": c["ring"], "ord": c["ord"],
            "shown": c["shown"], "total": c["total"],
            "placed": c["placed"], "not_placed": c["not_placed"],
            "updated": c["updated"],
            "updated_min": ls.updated_to_minutes(c["updated"]),
            "source": c["source"],
            # [entry, horse, rider, ord, place] -> [entry, horse, rider, place]
            # (the merge only needs the place)
            "entries": [[e[0], e[1], e[2], e[4]] for e in c.get("entries", [])],
        })
    if not out_classes:
        sys.exit("fetch_live.py: no classes parsed (page layout change?)")
    with open(LIVE_JSON, 'w') as f:
        json.dump({"fetched": datetime.now().strftime('%Y-%m-%d %H:%M'),
                   "classes": out_classes}, f, separators=(',', ':'))
    cj.save(ignore_discard=True, ignore_expires=True)
    print("live.json: %d classes, %d placings"
          % (len(out_classes), sum(len(c["entries"]) for c in out_classes)))


if __name__ == '__main__':
    main()
