#!/usr/bin/env python3
import hashlib, json, datetime, os, re, sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

if "--ui-only" in sys.argv[1:]:
    # Rebuild the page from the payload already embedded in index.html,
    # for template/UI changes that don't touch the data.
    idx = os.path.join(ROOT, "index.html")
    try:
        s = open(idx).read()
    except OSError:
        sys.exit("build_page.py: --ui-only needs an existing index.html at the repo root")
    m = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", s, re.M)
    if not m:
        sys.exit("build_page.py: no embedded payload found in index.html (is it a build of this template?)")
    payload = m.group(1)
else:
    data = json.load(open(os.path.join(HERE, 'data.json')))

    classes = []
    for c in data:
        cc = {
            "n": c["num"],
            "name": c["name"],
            "div": c["division"],
            "wk": c.get("weekday"),
            "day": c.get("date"),
            "per": c.get("period"),
            "time": c.get("time"),
            "e": [[e["entry"], e["horse"], e["rider"], e["trainer"], e["owner"], e.get("start"), e.get("place")]
                  for e in c["entries"]],
        }
        # scratched (withdrawn) entries, by entry number; key only when non-empty
        sc = [e["entry"] for e in c["entries"] if e.get("scratch")]
        if sc:
            cc["sc"] = sc
        classes.append(cc)

    # Live scores (git-ignored intermediates): official placings win, live
    # fills gaps; classes with fresh live activity (< 60 min) get "live".
    # Missing files -> exactly today's behavior.
    # See docs/superpowers/specs/2026-08-24--live-scores-design.md
    sys.path.insert(0, HERE)
    import live_scores as ls
    cache = {}
    try:
        cache = json.load(open(os.path.join(HERE, 'live_cache.json')))
    except (OSError, ValueError):
        pass
    live_fresh = {}
    try:
        for c in json.load(open(os.path.join(HERE, 'live.json'))).get("classes", []):
            u = c.get("updated_min")
            if u is not None and u < 60:
                live_fresh[c["num"]] = u
    except (OSError, ValueError):
        pass
    if cache or live_fresh:
        ls.merge_live_places(classes, cache)
        for c in classes:
            if c["n"] in live_fresh:
                c["live"] = live_fresh[c["n"]]

    # Judge scorecards (git-ignored intermediate): the show posts one PDF per
    # class in a public Google Drive folder, named CLASS N.pdf; classes with
    # a posted card get a "card" link the page renders in the card header.
    # The judges' names drift from the live class list ("CLASS 128-1.pdf"
    # for plain class 128; "CLASS 104.pdf" for section 104.1 after a split
    # removed the parent number), so keys are resolved against the current
    # classes before stamping — exact numbers always win. Missing/empty
    # file -> exactly today's page.
    try:
        cards = json.load(open(os.path.join(HERE, 'scorecards.json'))).get("cards", {})
    except (OSError, ValueError):
        cards = {}
    known = {c["n"] for c in classes}

    def card_key(k):
        if k in known:
            return k
        m = re.match(r'^(\d+)-(\d+)$', k)
        if m:
            if m.group(1) + "." + m.group(2) in known:
                return m.group(1) + "." + m.group(2)
            if m.group(1) in known:
                return m.group(1)
        if re.match(r'^\d+$', k):
            if k + ".1" in known:
                return k + ".1"
            secs = sorted(x for x in known if x.startswith(k + "."))
            if len(secs) == 1:
                return secs[0]
        return k

    lookup = {}
    for k in sorted(cards, key=lambda k: k not in known):
        lookup.setdefault(card_key(k), cards[k])
    for c in classes:
        if c["n"] in lookup:
            c["card"] = "https://drive.google.com/file/d/%s/view" % lookup[c["n"]]

    # Predicted windows: per-session pace model + hot-session anchor from
    # the live cache's first-seen timestamps. Pure function of
    # (classes, cache) — the asof policy is untouched (same inputs ->
    # same ps/pe).
    # See docs/superpowers/specs/2026-08-24--predicted-pace-design.md
    import predict as pr
    wins = pr.build_windows(classes, cache)
    for c in classes:
        w = wins.get(c["n"])
        if w:
            c["ps"], c["pe"] = w

    # The "Updated" timestamp only changes when the data actually changes:
    # if index.html already embeds this exact data, keep its asof.
    asof = None
    idx = os.path.join(ROOT, "index.html")
    try:
        prev = re.search(r"^(?:const|let) DATA = (\{.*\});\s*$", open(idx).read(), re.M)
        if prev:
            prev_obj = json.loads(prev.group(1))
            if json.dumps(prev_obj.get("classes"), separators=(',', ':')) == json.dumps(classes, separators=(',', ':')):
                asof = prev_obj.get("asof")
    except (OSError, ValueError):
        pass
    if not asof:
        # Show time (Kentucky is Eastern; DST handled by the zone).
        asof = datetime.datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M')

    # h: fingerprint of the data. The page polls a tiny check.json carrying
    # this and only fetches the full payload.json when it changes. Pure
    # function of the data -> the asof policy is untouched.
    h = hashlib.sha1(json.dumps(classes, separators=(',', ':')).encode()).hexdigest()[:12]
    payload = json.dumps({"asof": asof, "h": h, "classes": classes}, separators=(',', ':'))
    with open(os.path.join(ROOT, "payload.json"), "w") as f:
        f.write(payload + "\n")
    with open(os.path.join(ROOT, "check.json"), "w") as f:
        f.write(json.dumps({"asof": asof, "h": h}, separators=(',', ':')) + "\n")
    print(f"payload.json: {os.path.getsize(os.path.join(ROOT, 'payload.json'))/1024:.0f} KB")

html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WCHS 2026 — My Schedule</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E%F0%9F%90%8E%3C%2Ftext%3E%3C%2Fsvg%3E">
<style>
:root {
  --ink: #1a1a2e; --muted: #6b7280; --line: #e5e7eb;
  --accent: #1e40af; --accent-soft: #eff6ff; --gold: #b45309;
  --bg: #f9fafb; --surface: #fff;
  --chip-border: #bfdbfe; --chip-press: #dbeafe;
  --done-bg: #d1fae5; --done-border: #6ee7b7; --done-ink: #15803d; --done-tint: #f0fdf4; --done-tint-border: #bbf7d0;
  --now-bg: #fffbeb; --now-line: #f59e0b;
  --scratch-bg: #fbd0dc; --scratch-ink: #b91c1c;
  --toast-bg: #1a1a2e; --toast-ink: #fff;
}
html.dark {
  --ink: #e5e7eb; --muted: #98a2b3; --line: #2e3644;
  --accent: #60a5fa; --accent-soft: #1d2c49; --gold: #fbbf24;
  --bg: #0f1115; --surface: #171d26;
  --chip-border: #2d4a78; --chip-press: #24365a;
  --done-bg: #12301f; --done-border: #21694a; --done-ink: #7ddba8; --done-tint: #14332a; --done-tint-border: #245c46;
  --now-bg: #33260a; --now-line: #f59e0b;
  --scratch-bg: #3b1522; --scratch-ink: #fca5a5;
  --toast-bg: #e5e7eb; --toast-ink: #111827;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: var(--ink); background: var(--bg); font-size: 15px; line-height: 1.4; }
header { position: sticky; top: 0; z-index: 10; background: var(--surface); border-bottom: 1px solid var(--line); padding: 10px 14px; }
header h1 { font-size: 17px; margin: 0; }
header .sub { color: var(--muted); font-size: 12.5px; margin-top: 2px; }
header .updated { color: var(--muted); font-size: 12px; margin-top: 2px; display: flex; align-items: center; gap: 6px; }
.ring { flex: none; transform: rotate(-90deg); }
.ring circle { fill: none; stroke-width: 2.5; }
.ring-track { stroke: var(--line); }
.ring-fg { stroke: var(--accent); stroke-linecap: round; }
.actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.actions button { font: inherit; font-size: 13px; padding: 6px 12px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 8px; cursor: pointer; }
.actions button:active { background: var(--accent-soft); }
.actions button.on { background: var(--accent); color: #fff; border-color: var(--accent); }
.actions button:disabled { opacity: .45; cursor: default; }
.actions .primary { background: var(--accent); color: #fff; border-color: var(--accent); }
#layout { display: block; }
aside { background: var(--surface); border-bottom: 1px solid var(--line); }
body.nofilters aside { display: none; }
.fgroup { border-bottom: 1px solid var(--line); padding: 10px 14px; }
.fgroup h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; margin: 0 0 6px; color: var(--muted); display: flex; align-items: center; gap: 8px; cursor: pointer; }
.fgroup h2 .selcount { background: var(--accent); color: #fff; border-radius: 9px; font-size: 11px; padding: 1px 7px; min-width: 18px; text-align: center; display: none; }
.fgroup h2 .selcount.on { display: inline-block; }
.fgroup h2 .clearx { margin-left: auto; border: none; background: none; color: var(--muted); font-size: 15px; cursor: pointer; display: none; padding: 0 4px; }
.fgroup h2 .clearx.on { display: inline-block; }
.fsearch { width: 100%; font: inherit; font-size: 14px; padding: 7px 10px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); border-radius: 8px; margin-bottom: 6px; }
.fopts { max-height: 210px; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.frow { display: flex; align-items: center; gap: 8px; padding: 4px 2px; font-size: 14px; }
.frow input { width: 17px; height: 17px; flex: none; accent-color: var(--accent); }
.frow label { flex: 1; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.frow .cnt { color: var(--muted); font-size: 12px; flex: none; }
.fnote { color: var(--muted); font-size: 12px; padding: 4px 2px; }
.chips { display: none; flex-wrap: wrap; gap: 5px; margin-bottom: 7px; }
.chips:not(:empty) { display: flex; }
.chip { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--chip-border); border-radius: 14px; font-size: 12.5px; padding: 2px 6px 2px 10px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chipx { cursor: pointer; margin-left: 5px; font-weight: 700; }
main { padding: 12px 14px 60px; max-width: 900px; }
.day { margin-bottom: 8px; }
.day h2 { font-size: 16px; margin: 18px 0 4px; padding-bottom: 4px; border-bottom: 2px solid var(--ink); cursor: pointer; }
.day h2 .dsub { color: var(--muted); font-weight: normal; font-size: 13px; }
.dchev { display: inline-block; color: var(--muted); font-size: 11px; margin-right: 5px; transition: transform .15s; transform: rotate(90deg); }
.day.collapsed .dchev { transform: rotate(0deg); }
.day.collapsed .day-body { display: none; }
.session h3 { font-size: 13.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--gold); margin: 12px 0 6px; }
.cls { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; margin-bottom: 8px; overflow: hidden; }
.cls.muted { opacity: .55; border-style: dashed; }
.cls.done { background: var(--done-bg); border-color: var(--done-border); }
.cls.done .cls-head { background: transparent; }
.cls.now { background: var(--now-bg); border: 2px solid var(--now-line); }
.cls.now .cls-head { background: transparent; }
.cnow { background: #f59e0b; color: #fff; border-radius: 6px; font-size: 11px; padding: 1px 6px; flex: none; }
.cpend { background: var(--now-bg); border: 1px dashed var(--now-line); color: var(--gold); border-radius: 6px; font-size: 11px; padding: 1px 6px; flex: none; }
.clive { display: inline-flex; align-items: center; gap: 4px; background: var(--now-bg); color: var(--gold); border: 1px solid var(--now-line); border-radius: 6px; font-size: 11px; font-weight: 600; padding: 1px 6px; flex: none; }
.clivedot { width: 6px; height: 6px; border-radius: 50%; background: var(--gold); animation: clivepulse 2s ease-in-out infinite; }
@keyframes clivepulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .clivedot { animation: none; } }
.cls-head { width: 100%; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; padding: 10px 12px; border: none; background: var(--surface); font: inherit; color: var(--ink); text-align: left; cursor: pointer; }
.cls-head:active { background: var(--accent-soft); }
.cnum { font-weight: 700; color: var(--accent); flex: none; font-size: 13.5px; min-width: 34px; }
.cname { flex: 1; font-weight: 600; }
.cdone { color: var(--done-ink); background: var(--done-tint); border: 1px solid var(--done-tint-border); border-radius: 6px; font-size: 11px; padding: 1px 6px; flex: none; }
.cscard { color: var(--accent); background: var(--accent-soft); border: 1px solid var(--chip-border); border-radius: 6px; font-size: 11px; font-weight: 600; padding: 1px 6px; flex: none; cursor: pointer; }
.cscard:active { background: var(--chip-press); }
.cdiv { color: var(--muted); font-size: 11.5px; border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; flex: none; }
.ccount { color: var(--muted); font-size: 12.5px; flex: none; }
.call { font-size: 12px; padding: 2px 8px; border: 1px solid var(--chip-border); background: var(--accent-soft); color: var(--accent); border-radius: 8px; cursor: pointer; flex: none; }
.call:active { background: var(--chip-press); }
.chere { color: var(--muted); border: 1px solid var(--line); background: var(--surface); border-radius: 6px; font-size: 11px; padding: 1px 6px; flex: none; cursor: pointer; }
.chere:active { background: var(--accent-soft); }
.chere.on { background: #f59e0b; border-color: #f59e0b; color: #fff; font-weight: 600; }
.chev { flex: none; color: var(--muted); font-size: 11px; transition: transform .15s; }
.cls.open .chev { transform: rotate(90deg); }
.cls-entries { display: none; border-top: 1px solid var(--line); }
.cls.open .cls-entries { display: block; }
.erow { display: grid; grid-template-columns: 40px 1fr; gap: 2px 8px; padding: 7px 12px; border-bottom: 1px solid var(--line); font-size: 13.5px; }
.erow:last-child { border-bottom: none; }
.erow .eentry { grid-row: span 2; align-self: start; color: var(--muted); font-size: 12px; padding-top: 1px; }
.erow .eentry b { color: var(--ink); font-size: 14px; font-variant-numeric: tabular-nums; }
.ehorse { font-weight: 600; }
.eppl { grid-column: 2; color: var(--muted); font-size: 12.5px; }
.eppl .place { color: var(--gold); font-weight: 600; }
.erow.other .eentry, .erow.other .eentry b, .erow.other .ehorse, .erow.other .eppl { color: var(--muted); }
.erow.other .ehorse { font-weight: 400; }
.erow.other .eppl .place { color: var(--gold); font-weight: 600; }
.erow.scratch { background: var(--scratch-bg); }
.erow.scratch .eentry b, .erow.scratch .ehorse, .erow.scratch .eppl { color: var(--scratch-ink); text-decoration: line-through; }
.eother { display: inline-block; margin-left: 6px; padding: 0 6px; border: 1px solid var(--line); background: var(--surface); border-radius: 9px; font-size: 10.5px; line-height: 1.5; color: var(--muted); vertical-align: 1px; }
.footnote { color: var(--muted); font-size: 12px; text-align: center; margin-top: 30px; }
#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--toast-bg); color: var(--toast-ink); padding: 8px 16px; border-radius: 8px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity .25s; z-index: 50; }
#toast.show { opacity: 1; }
#printHead { display: none; }
@media (min-width: 900px) {
  #layout { display: flex; gap: 18px; align-items: flex-start; padding: 14px; }
  aside { width: 320px; flex: none; position: sticky; top: 92px; border: 1px solid var(--line); border-radius: 12px; max-height: calc(100vh - 110px); overflow-y: auto; }
  .fgroup { border-bottom: 1px solid var(--line); }
  main { flex: 1; padding: 4px 0 60px; }
}
@media print {
  :root, html.dark { --ink: #1a1a2e; --muted: #6b7280; --line: #e5e7eb; --accent: #1e40af; --accent-soft: #eff6ff; --gold: #b45309; --bg: #fff; --surface: #fff; --chip-border: #bfdbfe; --chip-press: #dbeafe; --done-bg: #d1fae5; --done-border: #6ee7b7; --done-ink: #15803d; --done-tint: #f0fdf4; --done-tint-border: #bbf7d0; --now-bg: #fffbeb; --now-line: #f59e0b; --toast-bg: #1a1a2e; --toast-ink: #fff; }
  header .actions, aside, #toast, .chev, .dchev, .call, .chere, .ring { display: none !important; }
  .day .day-body { display: block !important; }
  #printHead { display: block; margin-bottom: 14px; }
  #printHead h1 { font-size: 16pt; margin: 0 0 2px; }
  #printHead .phsub { font-size: 10pt; color: #333; }
  body { background: #fff; font-size: 11pt; }
  main { padding: 0; max-width: none; }
  .day { break-before: page; }
  .day:first-child { break-before: auto; }
  .day h2 { break-after: avoid; border-bottom-width: 1.5pt; }
  .session h3 { break-after: avoid; }
  .cls { border: 1px solid #999; border-radius: 4px; break-inside: avoid; }
  .cls-head { padding: 6px 8px; }
  .cls-entries { display: block !important; border-top: 1px solid #999; }
  .erow { padding: 4px 8px; border-bottom: 1px solid #ddd; }
  .cdiv, .ccount { display: none; }
}
</style>
</head>
<body>
<div id="printHead"><h1>World's Championship Horse Show 2026 — My Schedule</h1><div class="phsub" id="phSub"></div></div>
<header>
  <h1>WCHS 2026 — My Schedule</h1>
  <div class="sub">World's Championship Horse Show · Aug 22–29 · Kentucky State Fair, Louisville</div>
  <div class="updated" id="updatedLine"><svg class="ring" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle class="ring-track" cx="7" cy="7" r="6"></circle><circle class="ring-fg" cx="7" cy="7" r="6"></circle></svg><span id="updatedText"></span></div>
  <div class="actions">
    <button id="filtersBtn">Filters</button>
    <button id="scopeBtn" disabled>My classes</button>
    <button id="doneBtn">Hide done</button>
    <button id="themeBtn">Dark</button>
    <button class="primary" id="printBtn">Print</button>
    <button id="copyBtn">Copy link</button>
    <button id="clearBtn">Clear</button>
    <button id="paceBtn" disabled>Reset pace</button>
  </div>
</header>
<div id="layout">
  <aside id="filters"></aside>
  <main id="schedule"></main>
</div>
<div id="toast"></div>
<script>
"use strict";
let DATA = __PAYLOAD__;
const LS_KEY = "wchs2026.sel.v1";
const VIEW_KEY = "wchs2026.view.v1";
const FIELDS = [
  {key:"trainer", label:"Trainers", col:3},
  {key:"rider",   label:"Riders",   col:2},
  {key:"horse",   label:"Horses",   col:1},
  {key:"owner",   label:"Owners",   col:4},
];
const state = {trainer:new Set(), rider:new Set(), horse:new Set(), owner:new Set(), division:new Set()};
const search = {trainer:"", rider:"", horse:"", owner:"", division:""};
const openCls = new Set();
const dayState = {};
const view = { filtersOpen: null, scope: false, doneHidden: false, theme: null };
(function loadView(){
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || "null");
    if (v){
      if (typeof v.filtersOpen === "boolean") view.filtersOpen = v.filtersOpen;
      view.scope = v.scope != null ? !!v.scope : !!v.context;   // v.context: legacy key
      view.doneHidden = !!v.doneHidden;
      view.theme = (v.theme === "dark" || v.theme === "light") ? v.theme : null;
    }
  } catch(e){}
})();
function saveView(){ try { localStorage.setItem(VIEW_KEY, JSON.stringify(view)); } catch(e){} }

// ---- manual "here" pacing: the user pins the live class. The pinned
// class's session is re-anchored so the pinned class starts at the pin time
// and the rest of the session walks forward at the usual pace. Results at or
// after the pin (live or official) drop the pin; a header button resets it.
const PIN_KEY = "wchs2026.pin.v1";
let pin = null;
(function loadPin(){
  try {
    const v = JSON.parse(localStorage.getItem(PIN_KEY) || "null");
    if (v && typeof v.num === "string" && typeof v.at === "number") pin = v;
  } catch(e){}
})();
function savePin(p){
  pin = p;
  try { p ? localStorage.setItem(PIN_KEY, JSON.stringify(p)) : localStorage.removeItem(PIN_KEY); } catch(e){}
}

function norm(s){ return (s||"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim(); }

// ---- pure helpers (unit-tested)
function defaultFiltersOpen(w){ return w >= 900; }
const MONTHS = {January:0, February:1, March:2, April:3, May:4, June:5, July:6, August:7, September:8, October:9, November:10, December:11};
function isPastDay(dayStr, now){
  now = now || new Date();
  const m = String(dayStr).match(/^(\w+) (\d{1,2})$/);
  if (!m || MONTHS[m[1]] == null) return false;
  const d = new Date(2026, MONTHS[m[1]], +m[2]);
  const t = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return d < t;
}
function isDone(c){ return c.e.some(e => e[6] != null); }
function fmtAsof(s){
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (!m) return s;
  const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const h = +m[4];
  return MON[+m[2]-1] + " " + (+m[3]) + ", " + m[1] + " · " + (h % 12 || 12) + ":" + m[5] + " " + (h < 12 ? "AM" : "PM");
}

// ---- build name indexes
const NAMES = {trainer:{}, rider:{}, horse:{}, owner:{}};
const DIVS = {};
let DIV_LIST = [];
function buildIndexes(){
  NAMES.trainer = {}; NAMES.rider = {}; NAMES.horse = {}; NAMES.owner = {};
  for (const k in DIVS) delete DIVS[k];
  for (const c of DATA.classes){
    DIVS[norm(c.div)] = c.div;
    for (const e of c.e){
      const t = norm(e[3]); if (t) (NAMES.trainer[t] ||= {d:e[3], n:0}).n++;
      const r = norm(e[2]); if (r) (NAMES.rider[r]   ||= {d:e[2], n:0}).n++;
      const h = norm(e[1]); if (h) (NAMES.horse[h]   ||= {d:e[1], n:0}).n++;
      const o = norm(e[4]); if (o) (NAMES.owner[o]   ||= {d:e[4], n:0}).n++;
    }
  }
  DIV_LIST = Object.values(DIVS).sort();
}
buildIndexes();

// ---- persistence
function active(){ return FIELDS.some(f=>state[f.key].size) || state.division.size; }
function serialize(){
  const p = {};
  for (const f of FIELDS) if (state[f.key].size) p[f.key[0]] = [...state[f.key]];
  if (state.division.size) p.dv = [...state.division];
  return p;
}
function hashEncode(arr){ return arr.map(encodeURIComponent).join("~"); }
function hashDecode(s){ return s.split("~").map(decodeURIComponent).filter(Boolean); }
function save(){
  try { localStorage.setItem(LS_KEY, JSON.stringify(serialize())); } catch(e){}
  const p = serialize();
  const h = Object.keys(p).map(k=>k+"="+hashEncode(p[k])).join("&");
  history.replaceState(null, "", h ? "#"+h : location.pathname+location.search);
}
function load(){
  let p = null;
  const HMAP = {t:"trainer", r:"rider", h:"horse", o:"owner", dv:"division"};
  const h = location.hash.slice(1);
  if (h){ for (const kv of h.split("&")){ const i = kv.indexOf("="); if (i<0) continue;
    const k = HMAP[kv.slice(0,i)], v = hashDecode(kv.slice(i+1));
    if (k && state[k]) state[k] = new Set(v);
  } p = "hash"; }
  else {
    try { const s = JSON.parse(localStorage.getItem(LS_KEY)); if (s){
      for (const f of FIELDS) if (s[f.key[0]]) state[f.key] = new Set(s[f.key[0]]);
      if (s.dv) state.division = new Set(s.dv);
      p = "ls";
    }} catch(e){}
  }
  return p;
}

// ---- matching
function clsMatches(c){
  if (!active()) return true;
  if (state.division.size && !state.division.has(norm(c.div))) return false;
  if (!FIELDS.some(f=>state[f.key].size)) return true;
  return c.e.some(e => FIELDS.some(f => state[f.key].has(norm(e[f.col]))));
}
function eMatches(e){
  if (!active() || !FIELDS.some(f=>state[f.key].size)) return true;
  return FIELDS.some(f => state[f.key].has(norm(e[f.col])));
}

// ---- schedule grouping
const PER_ORDER = {Morning:0, Afternoon:1, Night:2, Evening:2};
function buildSchedule(){
  const byDay = new Map();
  for (const c of DATA.classes){
    if (!byDay.has(c.day)) byDay.set(c.day, {day:c.day, wk:c.wk, sessions:new Map(), n:0});
    const d = byDay.get(c.day);
    d.n++;
    if (!d.sessions.has(c.per)) d.sessions.set(c.per, []);
    d.sessions.get(c.per).push(c);
  }
  return [...byDay.values()].sort((a,b)=>parseInt(a.day.slice(-2))-parseInt(b.day.slice(-2)));
}
// ---- predicted-pace status (unit-tested)
// ps/pe are UTC epoch seconds predicted at build time (refresh/predict.py);
// official placings always beat the model. A "here" pin re-anchors the
// pinned class's session tail (pinShifts) so the pinned class starts at the
// pin time and the walk continues at the usual pace; results at/after the
// pin drop it.
function displayOrderOf(cls){
  const byDay = new Map();
  for (const c of cls){
    if (!byDay.has(c.day)) byDay.set(c.day, {day:c.day, sessions:new Map()});
    const d = byDay.get(c.day);
    if (!d.sessions.has(c.per)) d.sessions.set(c.per, []);
    d.sessions.get(c.per).push(c);
  }
  const days = [...byDay.values()].sort((a,b)=>parseInt(a.day.slice(-2))-parseInt(b.day.slice(-2)));
  const out = [];
  for (const d of days){
    const secs = [...d.sessions.entries()].sort((a,b)=>(PER_ORDER[a[0]]??9)-(PER_ORDER[b[0]]??9));
    for (const [, cs] of secs) out.push(...cs.slice().sort((a,b)=>parseFloat(a.n)-parseFloat(b.n)));
  }
  return out;
}
function pinValidity(classes, p){
  if (!p || !p.num) return false;
  const order = displayOrderOf(classes);
  let i = -1;
  for (let j = 0; j < order.length; j++) if (order[j].n === p.num){ i = j; break; }
  if (i < 0) return false;
  for (let j = i; j < order.length; j++) if (isDone(order[j])) return false;
  return true;
}
// Uniform shift (ms) of the pinned session's tail — the pin and every later
// class in the same session; null when the pin is stale or has no window.
function pinShifts(classes, p){
  if (!pinValidity(classes, p)) return null;
  const pc = classes.find(c => c.n === p.num);
  if (!pc || pc.ps == null || pc.pe == null) return null;
  const shift = p.at - pc.ps * 1000;
  const out = {};
  let started = false;
  for (const c of displayOrderOf(classes)){
    if (c.n === p.num) started = true;
    if (started && c.day === pc.day && c.per === pc.per && c.time === pc.time && c.ps != null)
      out[c.n] = shift;
  }
  return out;
}
function onNowCls(classes, nowMs, shifts){
  let best = null, bestPs = null;
  for (const c of classes){
    if (isDone(c) || c.ps == null || c.pe == null) continue;
    const ps = c.ps * 1000 + (shifts && shifts[c.n] || 0);
    if (ps <= nowMs && nowMs < c.pe * 1000 + (shifts && shifts[c.n] || 0)
        && (best == null || ps > bestPs)){ best = c; bestPs = ps; }
  }
  return best;
}
function upNextCls(classes, nowMs, shifts){
  const on = onNowCls(classes, nowMs, shifts);
  if (on) return on;
  for (const c of displayOrderOf(classes))
    if (!isDone(c) && c.ps != null && c.ps * 1000 + (shifts && shifts[c.n] || 0) > nowMs) return c;
  return null;
}
function isPendingCls(c, nowMs, shifts){
  return !isDone(c) && c.pe != null && nowMs >= c.pe * 1000 + (shifts && shifts[c.n] || 0);
}
const SHOW_TZ = "America/New_York";
function fmtShowTime(epochSec){
  try {
    return new Intl.DateTimeFormat("en-US", {timeZone: SHOW_TZ, hour: "numeric", minute: "2-digit"}).format(new Date(epochSec * 1000));
  } catch(e){ return ""; }
}
// {tag, text, title, clsNow} for a card's predicted-status pill; null when
// the card has none (done classes, or a future class outside its window).
function classPill(c, nowMs, hotNum, shifts){
  if (isDone(c)) return null;
  const sh = (shifts && shifts[c.n] || 0) / 1000;
  const ps = c.ps == null ? null : c.ps + sh;
  const pe = c.pe == null ? null : c.pe + sh;
  if (c.n === hotNum){
    if (ps != null && ps * 1000 <= nowMs && nowMs < pe * 1000)
      return {tag:"cnow", text:"on now \u00b7 est " + fmtShowTime(pe), title:"", clsNow:true};
    return {tag:"cnow", text:"up next \u00b7 est " + fmtShowTime(ps), title:"", clsNow:true};
  }
  if (isPendingCls(c, nowMs, shifts))
    return {tag:"cpend", text:"awaiting results", title:"est done " + fmtShowTime(pe) + " (predicted)", clsNow:false};
  return null;
}

// ---- rendering
const $ = s => document.querySelector(s);
function el(tag, cls, txt){ const n = document.createElement(tag); if (cls) n.className = cls; if (txt!=null) n.textContent = txt; return n; }

function renderFilters(){
  const aside = $("#filters");
  aside.textContent = "";
  for (const f of FIELDS) aside.appendChild(makeGroup(f.key, f.label, NAMES[f.key]));
  aside.appendChild(makeGroup("division", "Divisions", null, DIV_LIST));
}
function makeGroup(key, label, names, plainList){
  const g = el("div", "fgroup");
  const h2 = el("h2");
  h2.appendChild(el("span", null, label));
  const cnt = el("span", "selcount"); h2.appendChild(cnt);
  const cx = el("button", "clearx", "×"); h2.appendChild(cx);
  g.appendChild(h2);
  const si = el("input", "fsearch"); si.placeholder = "Search " + label.toLowerCase() + "…"; si.type = "search";
  g.appendChild(si);
  const box = el("div", "fopts"); g.appendChild(box);

  const CAP = 250;
  let showAll = false;
  const chips = el("div","chips"); g.insertBefore(chips, box);
  function updChips(){
    chips.textContent = "";
    const sel = [...state[key]];
    if (!sel.length) return;
    for (const k of sel){
      const disp = plainList ? (DIVS[k]||k) : (names[k] ? names[k].d : k);
      const ch = el("span","chip", disp);
      ch.title = disp;
      const x = el("span","chipx","×");
      x.addEventListener("click", ev => { ev.stopPropagation(); state[key].delete(k); onStateChange(); });
      ch.appendChild(x);
      chips.appendChild(ch);
    }
  }
  function opts(){
    box.textContent = "";
    const raw = (search[key]||"").trim().toLowerCase();
    const qWords = raw ? raw.split(/\s+/) : [];
    const items = plainList
      ? plainList.map(d => ({k:norm(d), nk:norm(d), d, n:DATA.classes.filter(c=>norm(c.div)===norm(d)).reduce((a,c)=>a+c.e.length,0)}))
      : Object.entries(names).map(([k,v])=>({k, nk:norm(v.d), d:v.d, n:v.n}));
    items.sort((a,b)=> a.d.localeCompare(b.d));
    const vis = qWords.length ? items.filter(it => qWords.every(w => it.nk.includes(w))) : items;
    if (!vis.length){ box.appendChild(el("div","fnote","No matches")); return; }
    const shown = showAll || !qWords.length ? vis : vis.slice(0, CAP);
    for (const it of shown){
      const row = el("div","frow");
      const cb = document.createElement("input"); cb.type = "checkbox";
      cb.checked = state[key].has(it.k);
      cb.addEventListener("change", ()=>{ cb.checked ? state[key].add(it.k) : state[key].delete(it.k); onStateChange(); });
      const lb = el("label", null, it.d); lb.title = it.d;
      lb.addEventListener("click", ()=>{ cb.checked = !cb.checked; cb.dispatchEvent(new Event("change")); });
      row.appendChild(cb); row.appendChild(lb); row.appendChild(el("span","cnt", String(it.n)));
      box.appendChild(row);
    }
    if (vis.length > shown.length){
      const more = el("button","fnote morebtn", "Show more ("+(vis.length-shown.length)+" more)");
      more.style.cssText="width:100%;margin-top:4px;padding:6px;border:1px solid var(--line);background:var(--surface);color:var(--muted);border-radius:8px;cursor:pointer;font-size:12.5px;";
      more.addEventListener("click", ()=>{ showAll = true; opts(); });
      box.appendChild(more);
    }
  }
  opts();
  updChips();
  si.addEventListener("input", ()=>{ search[key] = si.value; opts(); });
  const updateBadges = () => {
    const n = state[key].size;
    cnt.textContent = n; cnt.classList.toggle("on", n>0); cx.classList.toggle("on", n>0);
  };
  cx.addEventListener("click", e => { e.stopPropagation(); state[key].clear(); onStateChange(); });
  h2.addEventListener("click", e => { if (e.target===cx) return; si.focus(); });
  g._update = () => { updateBadges(); updChips(); };
  updateBadges();
  return g;
}

let lastPinNum = null;
function notePin(num){
  if (lastPinNum && !num) toast("Results are ahead of class " + lastPinNum + " \u2014 back to predicted pace");
  lastPinNum = num;
}
function applyPaceBtn(active){
  const b = $("#paceBtn");
  if (b) b.disabled = !active;
}
function setPin(num){
  if (!num) lastPinNum = null;   // a manual reset is not the results override
  savePin(num ? {num: num, at: Date.now()} : null);
  renderSchedule();
  if (num) toast("Paced from class " + num + " \u2014 reset any time");
}
function renderSchedule(){
  const main = $("#schedule");
  main.textContent = "";
  const days = buildSchedule();
  const on = active();
  const nowMs = Date.now();
  const shifts = pin ? pinShifts(DATA.classes, pin) : null;
  notePin(shifts ? pin.num : null);
  applyPaceBtn(!!shifts);
  const hot = upNextCls(DATA.classes, nowMs, shifts);
  const hotNum = hot ? hot.n : null;
  const pinNum = shifts ? pin.num : null;
  let rendered = 0;
  for (const d of days){
    const secs = [...d.sessions.entries()].sort((a,b)=>(PER_ORDER[a[0]]??9)-(PER_ORDER[b[0]]??9));
    const dEl = el("section","day");
    dEl.dataset.day = d.day;
    const collapsed = dayState[d.day] != null ? dayState[d.day] : isPastDay(d.day);
    if (collapsed) dEl.classList.add("collapsed");
    const h2 = el("h2");
    h2.appendChild(el("span","dchev","▶"));
    h2.appendChild(el("span",null, d.wk + ", " + d.day));
    h2.addEventListener("click", () => {
      dayState[d.day] = !dEl.classList.contains("collapsed");
      dEl.classList.toggle("collapsed");
    });
    dEl.appendChild(h2);
    const body = el("div","day-body");
    let dShown = 0, dRendered = 0;
    for (const [per, cls] of secs){
      const list = cls.filter(c => !view.doneHidden || !isDone(c));
      const matched = on ? list.filter(clsMatches) : list;
      let vis = (on && view.scope) ? list : matched;
      if (on && !view.scope && hotNum && list.some(c => c.n === hotNum) && !vis.some(c => c.n === hotNum)){
        vis = [...vis, list.find(c => c.n === hotNum)];
      }
      if (!vis.length) continue;
      dShown += matched.length;
      dRendered += vis.length;
      const sEl = el("div","session");
      sEl.appendChild(el("h3",null, per + (cls[0].time ? " · " + cls[0].time : "")));
      for (const c of vis.slice().sort((a,b)=>parseFloat(a.n)-parseFloat(b.n))){
        const m = matched.includes(c);
        rendered++;
        sEl.appendChild(makeClass(c, m, hotNum, pinNum, shifts));
      }
      body.appendChild(sEl);
    }
    dEl.appendChild(body);
    if (!dRendered) continue;
    if (on) h2.appendChild(el("span","dsub", " — " + dShown + " of " + d.n + " classes"));
    main.appendChild(dEl);
  }
  if (!rendered){
    main.appendChild(el("div","fnote","Nothing matches your selection. Try removing a filter."));
  }
  main.appendChild(el("div","footnote",'"est" times are predictions from an average class pace (~10 min); actual order may vary. Tap "here" on a class to pace the schedule from where you are.'));
  const sub = $("#phSub");
  if (sub){
    const parts = FIELDS.filter(f=>state[f.key].size).map(f=>f.label+": "+[...state[f.key]].map(k=>namesDisp(f.key,k)).join(", "));
    if (state.division.size) parts.push("Divisions: "+[...state.division].map(k=>DIVS[k]).join(", "));
    sub.textContent = (parts.join("  ·  ") || "Full schedule") + "  —  generated " + DATA.asof;
  }
}
function namesDisp(key,k){ const m = NAMES[key] && NAMES[key][k]; return m ? m.d : k; }

function makeClass(c, isMatch, hotNum, pinNum, shifts){
  const isHot = c.n === hotNum;
  const on = active();
  const scr = new Set(c.sc || []);
  const visE = on ? c.e.filter(eMatches) : c.e;
  const showFiltered = on && isMatch;
  const canToggle = showFiltered && visE.length < c.e.length;
  let showingAll = !showFiltered;
  const sortE = a => [...a].sort((x,y)=>{
    const sa = x[5]==null ? 9999 : parseInt(x[5])||0, sb = y[5]==null ? 9999 : parseInt(y[5])||0;
    return sa - sb;
  });
  const buildRows = (box, entries) => {
    for (const e of sortE(entries)){
      const other = on && !eMatches(e);
      const row = el("div","erow" + (other ? " other" : "") + (scr.has(e[0]) ? " scratch" : ""));
      const en = el("span","eentry");
      en.innerHTML = e[0] ? "<b>"+e[0]+"</b>" : "—";
      row.appendChild(en);
      const horse = el("span","ehorse", e[1]);
      if (other) horse.appendChild(el("span","eother","other"));
      row.appendChild(horse);
      const ppl = el("span","eppl");
      if (e[6]!=null) ppl.appendChild(el("span","place", e[6]+placeSuf(e[6]) + "  "));
      ppl.appendChild(document.createTextNode(e[2] + (e[3] && e[3]!==e[2] ? "  ·  " + e[3] : "")));
      row.appendChild(ppl);
      box.appendChild(row);
    }
  };
  const d = el("div","cls" + (on && !isMatch && !isHot ? " muted" : "") + (isDone(c) ? " done" : "") + (isHot ? " now" : ""));
  d.dataset.num = c.n;
  const head = el("button","cls-head");
  head.appendChild(el("span","cnum", c.n));
  head.appendChild(el("span","cname", c.name));
  if (isDone(c)) head.appendChild(el("span","cdone","done ✓"));
  if (c.card){
    const sc = el("span","cscard","scorecard \u2197");
    head.appendChild(sc);
    sc.addEventListener("click", ev => {
      ev.stopPropagation();
      window.open(c.card, "_blank", "noopener");
    });
  }
  const pill = classPill(c, Date.now(), hotNum, shifts);
  if (pill){
    const p = el("span", pill.tag, pill.text);
    if (pill.title) p.title = pill.title;
    head.appendChild(p);
  }
  if (c.live != null){
    const lv = el("span","clive");
    lv.appendChild(el("span","clivedot"));
    lv.appendChild(document.createTextNode("live"));
    head.appendChild(lv);
  }
  if (!isDone(c) && c.ps != null){
    const hh = el("span","chere" + (c.n === pinNum ? " on" : ""), "here");
    hh.title = c.n === pinNum ? "The clock runs from this class \u2014 use Reset pace to clear" : "Pace the schedule from this class";
    hh.addEventListener("click", ev => { ev.stopPropagation(); setPin(c.n); });
    head.appendChild(hh);
  }
  head.appendChild(el("span","cdiv", c.div));
  const call = canToggle ? el("span","call") : null;
  if (call) head.appendChild(call);
  const count = el("span","ccount");
  head.appendChild(count);
  head.appendChild(el("span","chev","▶"));
  d.appendChild(head);
  const box = el("div","cls-entries");
  d.appendChild(box);
  const refreshHead = () => {
    if (canToggle){
      count.style.display = "none";
      call.textContent = showingAll ? "Show mine " + visE.length : "Show all " + c.e.length;
    } else {
      count.textContent = c.e.length + " entries";
    }
  };
  const build = () => { box.textContent = ""; buildRows(box, (showFiltered && !showingAll) ? visE : c.e); };
  const shouldOpen = (on && isMatch) || openCls.has(c.n);
  if (shouldOpen){ d.classList.add("open"); build(); }
  head.addEventListener("click", () => {
    if (!d.classList.contains("open") && !box.firstChild) build();
    d.classList.toggle("open");
    d.classList.contains("open") ? openCls.add(c.n) : openCls.delete(c.n);
  });
  if (call) call.addEventListener("click", ev => {
    ev.stopPropagation();
    showingAll = !showingAll;
    if (box.firstChild) build();
    refreshHead();
  });
  refreshHead();
  return d;
}
function placeSuf(p){ p=String(p); return p.endsWith("1")&&!p.endsWith("11")?"st":p.endsWith("2")?"nd":p.endsWith("3")?"rd":"th"; }

function onStateChange(){
  save();
  for (const g of document.querySelectorAll("#filters .fgroup")) g._update && g._update();
  applyScopeBtn();
  renderSchedule();
}

// ---- view options (filters panel / scope / done / theme)
function applyFiltersOpen(){
  const open = view.filtersOpen == null ? defaultFiltersOpen(window.innerWidth) : view.filtersOpen;
  document.body.classList.toggle("nofilters", !open);
  $("#filtersBtn").classList.toggle("on", open);
}
function applyDoneBtn(){
  const b = $("#doneBtn");
  b.textContent = view.doneHidden ? "Show done" : "Hide done";
  b.classList.toggle("on", view.doneHidden);
}
function applyScopeBtn(){
  const b = $("#scopeBtn");
  b.textContent = view.scope ? "All classes" : "My classes";
  b.classList.toggle("on", view.scope);
  b.disabled = !active();
}
function applyTheme(){
  let dark;
  if (view.theme) dark = view.theme === "dark";
  else if (window.matchMedia) dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  else dark = false;   // no system signal available (e.g. jsdom)
  document.documentElement.classList.toggle("dark", dark);
  const b = $("#themeBtn");
  b.textContent = dark ? "Light" : "Dark";
  b.classList.toggle("on", dark);
}
$("#themeBtn").addEventListener("click", () => {
  view.theme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  saveView(); applyTheme();
});
$("#filtersBtn").addEventListener("click", () => {
  view.filtersOpen = !(view.filtersOpen == null ? defaultFiltersOpen(window.innerWidth) : view.filtersOpen);
  saveView(); applyFiltersOpen();
});
$("#doneBtn").addEventListener("click", () => { view.doneHidden = !view.doneHidden; saveView(); applyDoneBtn(); renderSchedule(); });
$("#scopeBtn").addEventListener("click", () => { view.scope = !view.scope; saveView(); applyScopeBtn(); renderSchedule(); });
$("#paceBtn").addEventListener("click", () => setPin(null));

// ---- buttons
$("#printBtn").addEventListener("click", ()=>window.print());
$("#clearBtn").addEventListener("click", ()=>{
  for (const k of Object.keys(state)) state[k].clear();
  for (const k in search) search[k]="";
  document.querySelectorAll("#filters .fsearch").forEach(i=>i.value="");
  renderFilters();
  onStateChange();
  toast("Selection cleared");
});
$("#copyBtn").addEventListener("click", async ()=>{
  save();
  try { await navigator.clipboard.writeText(location.href); toast("Link copied — send it to your barn buddy"); }
  catch(e){ toast("Copy the URL from the address bar"); }
});
let toastT;
function toast(msg){ const t=$("#toast"); t.textContent=msg; t.classList.add("show"); clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove("show"),2200); }

// ---- live update (polls check.json — asof + data hash — every cycle;
// fetches the full payload.json only when the hash changed; the embedded
// DATA is first paint and carries the same h)
const POLL_MS = (typeof window.__POLL_MS === "number") ? window.__POLL_MS : 30000;
const pollingActive = typeof fetch === "function" && location.protocol.indexOf("http") === 0;
let liveRaw = JSON.stringify(DATA);
let pollsFailed = 0, pollInFlight = false, pollTimer = null;
const RING_C = 2 * Math.PI * 6;
const ringFg = document.querySelector(".ring-fg");
if (ringFg){
  ringFg.style.strokeDasharray = RING_C;
  ringFg.style.strokeDashoffset = RING_C;
}
function ringReset(){
  if (!ringFg) return;
  ringFg.style.transition = "none";
  ringFg.style.strokeDashoffset = RING_C;
  void ringFg.getBoundingClientRect();
  ringFg.style.transition = "stroke-dashoffset " + POLL_MS + "ms linear";
  ringFg.style.strokeDashoffset = 0;
}
// asof is passed explicitly: while a re-render is focus-deferred, DATA is
// still the old payload but the header must show the newest asof
function setUpdatedLine(asof, stale){
  $("#updatedText").textContent = "Updated " + fmtAsof(asof) + (stale ? " · not updating" : "");
  if (ringFg) ringFg.style.display = stale ? "none" : "";
}
function restoreSearch(){
  const keys = ["trainer", "rider", "horse", "owner", "division"];
  document.querySelectorAll("#filters .fsearch").forEach((inp, i) => { inp.value = search[keys[i]] || ""; });
}
function applyDataUpdate(p){
  liveRaw = JSON.stringify(p);
  const x = window.scrollX || 0, y = window.scrollY || 0;
  const aside = $("#filters");
  const asy = aside ? (aside.scrollTop || 0) : 0;
  for (const dEl of document.querySelectorAll("#schedule .day")){
    const key = dEl.dataset.day;
    if (key != null && dayState[key] == null) dayState[key] = dEl.classList.contains("collapsed");
  }
  DATA = p;
  buildIndexes();
  renderFilters();
  restoreSearch();
  renderSchedule();
  setUpdatedLine(p.asof, false);
  if (aside) aside.scrollTop = asy;
  if (x || y) window.scrollTo(x, y);
}
let pendingPayload = null;
function focusInBody(){
  const a = document.activeElement;
  return !!a && a !== document.body &&
    ($("#filters").contains(a) || $("#schedule").contains(a));
}
function flushPending(){
  if (pendingPayload && !focusInBody()){
    const p = pendingPayload;
    pendingPayload = null;
    applyDataUpdate(p);
  }
}
document.addEventListener("focusout", flushPending);
document.addEventListener("visibilitychange", () => {
  clearTimeout(tickTimer);
  if (document.hidden) { clearTimeout(pollTimer); }
  else { clearTimeout(pollTimer); poll(); scheduleTick(); }
});
async function poll(){
  flushPending();
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    const r = await fetch("check.json?ts=" + Date.now(), {cache: "no-store"});
    if (!r.ok) throw new Error("http " + r.status);
    const chk = await r.json();
    if (!chk || typeof chk.h !== "string" || !chk.asof) throw new Error("bad check");
    if (chk.h !== DATA.h){
      // data changed (or the embedded payload predates check.json): fetch it
      const pr = await fetch("payload.json?ts=" + Date.now(), {cache: "no-store"});
      if (!pr.ok) throw new Error("http " + pr.status);
      const p = await pr.json();
      if (!p || !Array.isArray(p.classes) || !p.classes.every(c => Array.isArray(c.e))) throw new Error("bad payload");
      pollsFailed = 0;
      const raw = JSON.stringify(p);
      if (raw !== liveRaw){
        if (focusInBody()){
          pendingPayload = p;
          setUpdatedLine(p.asof, false);
        } else {
          applyDataUpdate(p);
        }
      } else {
        setUpdatedLine(DATA.asof, false);
      }
    } else {
      pollsFailed = 0;
      setUpdatedLine(DATA.asof, false);
    }
  } catch (e) {
    pollsFailed++;
    if (pollsFailed >= 3) setUpdatedLine(DATA.asof, true);
  } finally {
    pollInFlight = false;
    ringReset();
    clearTimeout(pollTimer);
    if (!document.hidden) pollTimer = setTimeout(poll, POLL_MS);
  }
}

// ---- status tick (predicted pills advance in place; never re-renders)
const TICK_MS = (typeof window.__TICK_MS === "number") ? window.__TICK_MS : 60000;
let tickTimer = null;
function refreshStatus(){
  if (focusInBody()) return;   // deferred; the next tick picks it up
  const nowMs = Date.now();
  const shifts = pin ? pinShifts(DATA.classes, pin) : null;
  const hot = upNextCls(DATA.classes, nowMs, shifts);
  const hotNum = hot ? hot.n : null;
  const byNum = new Map(DATA.classes.map(c => [c.n, c]));
  for (const card of document.querySelectorAll("#schedule .cls")){
    const c = byNum.get(card.dataset.num);
    if (!c) continue;
    const want = classPill(c, nowMs, hotNum, shifts);
    const wantNow = !!(want && want.clsNow);
    if (card.classList.contains("now") !== wantNow) card.classList.toggle("now", wantNow);
    const cur = card.querySelector(".cnow, .cpend");
    if (!want){ if (cur) cur.remove(); continue; }
    if (cur && cur.classList.contains(want.tag)
        && cur.textContent === want.text && (cur.title || "") === want.title) continue;
    if (cur) cur.remove();
    const p = el("span", want.tag, want.text);
    if (want.title) p.title = want.title;
    const head = card.querySelector(".cls-head");
    head.insertBefore(p, head.querySelector(".clive") || head.querySelector(".chere") || head.querySelector(".cdiv"));
  }
}
function scheduleTick(){
  clearTimeout(tickTimer);
  tickTimer = setTimeout(() => {
    if (!document.hidden){ refreshStatus(); scheduleTick(); }
  }, TICK_MS);
}

// ---- init
const src = load();
renderFilters();
applyFiltersOpen();
applyDoneBtn();
applyScopeBtn();
applyTheme();
setUpdatedLine(DATA.asof, false);
renderSchedule();
scheduleTick();
if (src) toast("Restored your selection");
if (pollingActive) {
  ringReset();
  pollTimer = setTimeout(poll, POLL_MS);
} else {
  const ring = document.querySelector(".ring");
  if (ring) ring.remove();
}
</script>
</body>
</html>
"""

html = html.replace("__PAYLOAD__", payload)
out = os.path.join(os.path.dirname(HERE), 'index.html')
open(out, 'w').write(html)
print(f"index.html: {os.path.getsize(out)/1024/1024:.2f} MB")
