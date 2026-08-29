#!/usr/bin/env python3
"""Fetch the judge scorecard index from the show's public Google Drive folder.

The main /drive/folders/<id> page lazy-loads and only serves the first ~50
file rows in its initial HTML, so we use the legacy embeddedfolderview
endpoint instead: a plain GET returns EVERY entry in one plain page, each
entry an <a href="https://drive.google.com/file/d/FILEID/view..."> wrapping
a flip-entry-title with the file name. Names matching CLASS N.pdf
(N = x or x.y, split sections included) map to class numbers; the judges
also post "CLASS N-K.pdf" (hyphen) for plain classes, which is kept as the
raw key "N-K" — build_page.py resolves such keys against the current class
list (N-K -> section N.K if it exists, else plain N; plain parent name of a
split class -> its surviving section). Writes refresh/scorecards.json:
{"fetched": "<local time>", "cards": {"12": "FILEID", "12.1": "FILEID"}}.

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
FOLDER_ID = "1N59TLwiKCRYBeTqwxT80WfPdguAiLhGy"
FOLDER_URL = "https://drive.google.com/embeddedfolderview?id=" + FOLDER_ID
SCORECARDS_JSON = os.path.join(HERE, "scorecards.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

ENTRY_RE = re.compile(
    r'<a href="https://drive\.google\.com/file/d/([A-Za-z0-9_-]{10,})/view[^"]*"'
    r'[^>]*>.*?flip-entry-title">([^<]*)</div>', re.S)
CARD_RE = re.compile(r'^CLASS\s+(\d+(?:[.-]\d+)?)\.pdf$', re.I)


def parse_folder_html(html):
    """Map class number -> Drive file id for every CLASS N.pdf in the page."""
    cards = {}
    for fid, name in ENTRY_RE.findall(html):
        n = CARD_RE.match(name.strip())
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
