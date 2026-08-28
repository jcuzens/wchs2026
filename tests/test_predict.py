#!/usr/bin/env python3
"""Predicted class windows (refresh/predict.py): per-session pace model,
hot-session anchor from the live cache's first-seen timestamps, the 180-min
cap, degrade paths, determinism."""
import datetime, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "refresh"))

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

import predict as pr

TZ = pr.TZ
def ep(y, mo, d, h, mi):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp())

A_START = ep(2026, 8, 22, 10, 0)   # session A: Saturday Morning, 10:00 a.m.
B_START = ep(2026, 8, 22, 18, 0)   # session B: Saturday Night, 6:00 p.m.
PACE_S = pr.PACE_MIN * 60          # 607.5 s (13.5 reduced 25%)
CHAMP_S = pr.CHAMP_EQ_MIN * 60     # 2700 s

def at(start, secs):
    """A window boundary the way build_windows truncates it:
    int of start + the float cumulative seconds."""
    return int(start + secs)

def cls(n, name, day="August 22", per="Morning", time="10:00 a.m."):
    return {"n": n, "name": name, "day": day, "per": per, "time": time, "e": []}

B = "6:00 p.m."
A1 = cls("1", "Hunt Seat Equitation")
A2 = cls("2", "Champion Equitation")
B4 = cls("4", "Hunt Seat Equitation", per="Night", time=B)
B51 = cls("5.1", "Hunt Seat Equitation", per="Night", time=B)
B52 = cls("5.2", "Hunt Seat Equitation", per="Night", time=B)
B6 = cls("6", "Hunt Seat Equitation", per="Night", time=B)
ALL = [A1, A2, B4, B51, B52, B6]

base = pr.build_windows(ALL)

# 1. pure schedule: contiguous walk from the published start
check("first ps = published start", base["1"][0] == A_START, str(base["1"]))
check("session B starts at its published time", base["4"][0] == B_START, str(base["4"]))
check("contiguous within a session",
      base["1"][1] == base["2"][0]
      and base["4"][1] == base["5.1"][0]
      and base["5.1"][1] == base["5.2"][0]
      and base["5.2"][1] == base["6"][0], str(base))

# 2. durations: champion equitation 45 min, everything else 10.125 (13.5 cut 25%)
check("plain class pace reduced 25% from 13.5", pr.PACE_MIN == 13.5 * 0.75, str(pr.PACE_MIN))
check("champion equitation slot is 45 min", pr.CHAMP_EQ_MIN == 45.0, str(pr.CHAMP_EQ_MIN))
check("champion equitation gets a 45-min slot",
      base["2"] == (at(A_START, PACE_S), at(A_START, PACE_S + CHAMP_S)), str(base["2"]))
check("plain class gets 10.125 min", base["1"] == (A_START, at(A_START, PACE_S)), str(base["1"]))
check("is_champion_equitation needs both words",
      pr.is_champion_equitation("Champion Equitation")
      and pr.is_champion_equitation("EQ - Champion Equitation - Senior")
      and not pr.is_champion_equitation("Equitation - Open")
      and not pr.is_champion_equitation("Champion Hunter")
      and not pr.is_champion_equitation(None))

# 3. observed end = the LATEST first-seen at across a class's entries
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"},
                                  "2": {"p": 2, "at": "2026-08-22 18:41"}}})
check("observed end = latest first-seen at", w["4"][1] == B_START + 41 * 60, str(w["4"]))

# 4. hot-session anchor: observed class pe = observed end, the rest of the
#    hot session shifts by the same delta, other sessions untouched
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}})
check("anchor: observed class pe = observed end", w["4"][1] == B_START + 35 * 60, str(w["4"]))
SHIFT = 35 * 60 - PACE_S   # 1492.5 s: 18:35 - predicted end 18:10:07.5
check("anchor: hot session shifted by the same delta",
      w["4"][0] == at(B_START, SHIFT)
      and w["5.1"][0] == w["4"][1]
      and w["6"][1] == at(B_START, 4 * PACE_S + SHIFT), str(w))
check("anchor: other sessions unchanged",
      w["1"] == base["1"] and w["2"] == base["2"], str(w))

# 5. cap: a very late observation clamps the positive shift at 180 min;
#    a negative shift (early start) is not capped
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-23 10:00"}}})
check("cap: positive shift clamped at 180 min", w["4"][0] == B_START + 180 * 60, str(w["4"]))
w = pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 17:50"}}})
check("cap: negative shift not capped", w["4"][1] == B_START - 10 * 60, str(w["4"]))

# 6. degrade: no/empty/corrupt cache -> pure schedule; unknown numbers and
#    slot-less classes are ignored
check("degrade: no cache", pr.build_windows(ALL) == base)
check("degrade: empty cache", pr.build_windows(ALL, {}) == base)
check("degrade: corrupt at ignored",
      pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "whenever"}}}) == base)
check("degrade: cache class with no window ignored",
      pr.build_windows(ALL, {"99": {"1": {"p": 1, "at": "2026-08-22 18:35"}}}) == base)
noslot = cls("9", "no slot", day=None)
check("no-slot class gets no window, others fine",
      "9" not in pr.build_windows(ALL + [noslot])
      and pr.build_windows(ALL + [noslot])["1"] == base["1"])

# 7. tie: same observed end -> the later class number anchors
w = pr.build_windows(ALL, {"2": {"1": {"p": 1, "at": "2026-08-22 10:20"}},
                            "4": {"1": {"p": 1, "at": "2026-08-22 10:20"}}})
check("tie: later class number is the anchor",
      w["4"][1] == A_START + 20 * 60 and w["1"][0] == A_START, str(w["4"]))

# 8. determinism
check("deterministic: same inputs -> same output",
      pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}})
      == pr.build_windows(ALL, {"4": {"1": {"p": 1, "at": "2026-08-22 18:35"}}}))

# 9. session-start parsing (delegates to select_frontier)
check("parse a.m. start", pr.parse_session_start("August 22", "10:00 a.m.") == A_START)
check("parse Noon start",
      pr.parse_session_start("August 23", "12:00 Noon") == ep(2026, 8, 23, 12, 0))
check("parse p.m. start", pr.parse_session_start("August 22", "6:00 p.m.") == B_START)
check("parse garbage -> None", pr.parse_session_start("August 22", "whenever") is None)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
