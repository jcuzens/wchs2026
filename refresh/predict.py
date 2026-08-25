#!/usr/bin/env python3
"""Predicted class windows for the schedule page.

Pure module: same inputs -> same output (it never reads wall-clock "now"),
so the asof policy is untouched. build_page.py imports it to stamp each
payload class with ps/pe (UTC epoch seconds); the page evaluates "on now" /
"up next" / "awaiting" client-side on the user's own clock.

Model: one sequential timeline per session, walking from the published
session start at PACE_MIN per class (CHAMP_EQ_MIN for champion equitation).
The session holding the newest live observation (the "hot" session) is
shifted so that observed class's predicted end equals the observed end; a
positive shift is capped at MAX_SHIFT_MIN. Official placings always beat
the model (enforced by the page, not here).

Observation source: the first-seen "at" timestamps in live_cache.json
(immutable per entry once folded — fold_live_cache keeps the first stamp).
A class's observed end is the LATEST first-seen "at" across its entries
(when its last placing first appeared). The live.json "Updated Xm ago"
column is deliberately NOT used: it is a rounded relative string, so the
reconstructed absolute time jitters by a minute across fetches and would
wobble the asof stamp on every cron cycle.

See docs/superpowers/specs/2026-08-24--predicted-pace-design.md
"""
import datetime
from zoneinfo import ZoneInfo

import select_frontier as sf

PACE_MIN = 13.5        # wall-clock minutes per class slot (incl. turnover)
CHAMP_EQ_MIN = 25.0    # champion equitation pattern classes
MAX_SHIFT_MIN = 180.0  # cap on the positive hot-session anchor shift
TZ = ZoneInfo("America/New_York")

def is_champion_equitation(name):
    """Name matches both 'equit' and 'champion' (case-insensitive)."""
    if not name:
        return False
    n = name.lower()
    return "equit" in n and "champion" in n

def num_order(n):
    """45 < 45.1 < 45.2 < 46."""
    return tuple(int(p) for p in str(n).split("."))

def session_key(c):
    """Payload keys; a class missing any of the three has no window."""
    return (c.get("day"), c.get("per"), c.get("time"))

def parse_session_start(date_str, time_str):
    """'August 24' + '1:00 p.m.' -> UTC epoch seconds; None when
    unparseable. Delegates the formats to
    select_frontier.parse_session_time (naive show-local time), then
    attaches the show zone."""
    dt = sf.parse_session_time(date_str or "", time_str or "", sf.SHOW_YEAR)
    if dt is None:
        return None
    return int(dt.replace(tzinfo=TZ).timestamp())

def _at_epoch(s):
    """A cache 'at' stamp (show-local '%Y-%m-%d %H:%M') -> epoch seconds."""
    try:
        dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    return int(dt.replace(tzinfo=TZ).timestamp())

def build_windows(classes, cache=None):
    """{num: (ps, pe)} in UTC epoch seconds (ints) for every class with a
    session slot. cache: the live_cache.json dict; None/empty -> pure
    schedule. Deterministic: same inputs -> same output."""
    sessions = {}
    for c in classes:
        k = session_key(c)
        if any(v is None for v in k):
            continue
        sessions.setdefault(k, []).append(c)
    for k in sessions:
        sessions[k].sort(key=lambda c: num_order(c["n"]))

    wins = {}
    key_by_num = {}
    for k, cs in sessions.items():
        start = parse_session_start(k[0], k[2])
        if start is None:
            continue
        t = start
        for c in cs:
            dur = CHAMP_EQ_MIN if is_champion_equitation(c.get("name")) else PACE_MIN
            wins[c["n"]] = [t, t + dur * 60.0]
            key_by_num[c["n"]] = k
            t += dur * 60.0

    # Anchor: the newest observed end (the class whose last placing first
    # appeared most recently); ties -> later class number.
    anchor = None   # (end_obs, class_num)
    if cache:
        for num, entries in cache.items():
            if num not in wins:
                continue
            obs = None
            for e in entries.values():
                if isinstance(e, dict):
                    ep = _at_epoch(e.get("at"))
                    if ep is not None and (obs is None or ep > obs):
                        obs = ep
            if obs is None:
                continue
            if anchor is None or (obs, num_order(num)) > (anchor[0], num_order(anchor[1])):
                anchor = (obs, num)
    if anchor:
        end_obs, num = anchor
        shift = end_obs - wins[num][1]
        if shift > MAX_SHIFT_MIN * 60.0:
            shift = MAX_SHIFT_MIN * 60.0
        for c in sessions[key_by_num[num]]:
            wins[c["n"]][0] += shift
            wins[c["n"]][1] += shift

    return {n: (int(w[0]), int(w[1])) for n, w in wins.items()}
