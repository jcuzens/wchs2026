#!/usr/bin/env python3
"""Fetch the judge scorecard index from the show's public Google Drive folder.

The folder page is public: a plain GET returns the file rows, each
<tr data-id="FILEID"> carrying the file name in its title aria-label
("CLASS 12.pdf PDF Shared"). Names matching CLASS N.pdf (N = x or x.y,
split sections included) map to class numbers. Writes
refresh/scorecards.json: {"fetched": "<local time>",
"cards": {"12": "FILEID", "12.1": "FILEID"}}.

On any failure exits non-zero and leaves scorecards.json untouched, so the
page degrades to no scorecard links. A parse that finds zero cards never
overwrites a good cache (a login wall or page redesign must not wipe it).
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER_URL = "https://drive.google.com/drive/folders/1N59TLwiKCRYBeTqwxT80WfPdguAiLhGy"
SCORECARDS_JSON = os.path.join(HERE, "scorecards.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

ROW_RE = re.compile(r'<tr [^>]*?data-id="([A-Za-z0-9_-]{10,})"[^>]*>(.*?)</tr>', re.S)
NAME_RE = re.compile(r'aria-label="([^"]+) [A-Z]+ Shared"')
CARD_RE = re.compile(r'^CLASS\s+(\d+(?:\.\d+)?)\.pdf$', re.I)


def parse_folder_html(html):
    """Map class number -> Drive file id for every CLASS N.pdf in the page."""
    cards = {}
    for fid, row in ROW_RE.findall(html):
        m = NAME_RE.search(row)
        if not m:
            continue
        n = CARD_RE.match(m.group(1).strip())
        if n:
            cards[n.group(1)] = fid
    return cards


def default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')


def main(fetch=None, out=SCORECARDS_JSON):
    fetch = fetch or default_fetch
    try:
        html = fetch(FOLDER_URL)
    except Exception as e:
        print("fetch_scorecards.py: fetch failed: %s" % e)
        return 1
    cards = parse_folder_html(html)
    if not cards:
        try:
            if json.load(open(out)).get("cards"):
                print("fetch_scorecards.py: parsed 0 cards; keeping existing %s" % out)
                return 1
        except (OSError, ValueError):
            pass
    with open(out, 'w') as f:
        json.dump({"fetched": datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M'),
                   "cards": cards}, f, separators=(',', ':'))
    print("scorecards.json: %d cards" % len(cards))
    return 0


if __name__ == '__main__':
    sys.exit(main())
