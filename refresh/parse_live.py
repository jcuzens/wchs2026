#!/usr/bin/env python3
"""Fold refresh/live.json into refresh/live_cache.json (git-ignored).

The cache grows only during the show so a class doesn't "un-place" when it
ages out of the live window before its official results page re-fetches.
The merge into the page happens in build_page.py.

Usage: parse_live.py [live.json [cache.json]]
  (defaults: refresh/live.json and refresh/live_cache.json)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_scores as ls


def main():
    live_p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "live.json")
    cache_p = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "live_cache.json")
    try:
        live = json.load(open(live_p))
    except (OSError, ValueError) as e:
        sys.exit("parse_live.py: cannot read %s: %s" % (live_p, e))
    try:
        cache = json.load(open(cache_p))
    except (OSError, ValueError):
        cache = {}
    ls.fold_live_cache(cache, live)
    with open(cache_p, "w") as f:
        json.dump(cache, f, separators=(',', ':'))
    print("live_cache.json: %d classes, %d placings"
          % (len(cache), sum(len(v) for v in cache.values())))


if __name__ == '__main__':
    main()
