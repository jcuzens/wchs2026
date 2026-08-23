#!/usr/bin/env python3
import json, datetime

data = json.load(open('data.json'))
asof = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

classes = []
for c in data:
    classes.append({
        "n": c["num"],
        "name": c["name"],
        "div": c["division"],
        "wk": c.get("weekday"),
        "day": c.get("date"),
        "per": c.get("period"),
        "time": c.get("time"),
        "e": [[e["entry"], e["horse"], e["rider"], e["trainer"], e["owner"], e.get("start"), e.get("place")]
              for e in c["entries"]],
    })

payload = json.dumps({"asof": asof, "classes": classes}, separators=(',', ':'))

html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WCHS 2026 — My Schedule</title>
<style>
:root {
  --ink: #1a1a2e; --muted: #6b7280; --line: #e5e7eb;
  --accent: #1e40af; --accent-soft: #eff6ff; --gold: #b45309;
  --bg: #f9fafb;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: var(--ink); background: var(--bg); font-size: 15px; line-height: 1.4; }
header { position: sticky; top: 0; z-index: 10; background: #fff; border-bottom: 1px solid var(--line); padding: 10px 14px; }
header h1 { font-size: 17px; margin: 0; }
header .sub { color: var(--muted); font-size: 12.5px; margin-top: 2px; }
.actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.actions button { font: inherit; font-size: 13px; padding: 6px 12px; border: 1px solid var(--line); background: #fff; border-radius: 8px; cursor: pointer; }
.actions button:active { background: var(--accent-soft); }
.actions .primary { background: var(--accent); color: #fff; border-color: var(--accent); }
#layout { display: block; }
aside { background: #fff; border-bottom: 1px solid var(--line); }
.fgroup { border-bottom: 1px solid var(--line); padding: 10px 14px; }
.fgroup h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; margin: 0 0 6px; color: var(--muted); display: flex; align-items: center; gap: 8px; cursor: pointer; }
.fgroup h2 .selcount { background: var(--accent); color: #fff; border-radius: 9px; font-size: 11px; padding: 1px 7px; min-width: 18px; text-align: center; display: none; }
.fgroup h2 .selcount.on { display: inline-block; }
.fgroup h2 .clearx { margin-left: auto; border: none; background: none; color: var(--muted); font-size: 15px; cursor: pointer; display: none; padding: 0 4px; }
.fgroup h2 .clearx.on { display: inline-block; }
.fsearch { width: 100%; font: inherit; font-size: 14px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; margin-bottom: 6px; }
.fopts { max-height: 210px; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.frow { display: flex; align-items: center; gap: 8px; padding: 4px 2px; font-size: 14px; }
.frow input { width: 17px; height: 17px; flex: none; accent-color: var(--accent); }
.frow label { flex: 1; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.frow .cnt { color: var(--muted); font-size: 12px; flex: none; }
.fnote { color: var(--muted); font-size: 12px; padding: 4px 2px; }
.chips { display: none; flex-wrap: wrap; gap: 5px; margin-bottom: 7px; }
.chips:not(:empty) { display: flex; }
.chip { background: var(--accent-soft); color: var(--accent); border: 1px solid #bfdbfe; border-radius: 14px; font-size: 12.5px; padding: 2px 6px 2px 10px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chipx { cursor: pointer; margin-left: 5px; font-weight: 700; }
main { padding: 12px 14px 60px; max-width: 900px; }
.day { margin-bottom: 8px; }
.day h2 { font-size: 16px; margin: 18px 0 4px; padding-bottom: 4px; border-bottom: 2px solid var(--ink); }
.day h2 .dsub { color: var(--muted); font-weight: normal; font-size: 13px; }
.session h3 { font-size: 13.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--gold); margin: 12px 0 6px; }
.cls { background: #fff; border: 1px solid var(--line); border-radius: 10px; margin-bottom: 8px; overflow: hidden; }
.cls-head { width: 100%; display: flex; align-items: baseline; gap: 8px; padding: 10px 12px; border: none; background: #fff; font: inherit; text-align: left; cursor: pointer; }
.cls-head:active { background: var(--accent-soft); }
.cnum { font-weight: 700; color: var(--accent); flex: none; font-size: 13.5px; min-width: 34px; }
.cname { flex: 1; font-weight: 600; }
.cdiv { color: var(--muted); font-size: 11.5px; border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; flex: none; }
.ccount { color: var(--muted); font-size: 12.5px; flex: none; }
.chev { flex: none; color: var(--muted); font-size: 11px; transition: transform .15s; }
.cls.open .chev { transform: rotate(90deg); }
.cls-entries { display: none; border-top: 1px solid var(--line); }
.cls.open .cls-entries { display: block; }
.erow { display: grid; grid-template-columns: 34px 1fr; gap: 2px 8px; padding: 7px 12px; border-bottom: 1px solid var(--line); font-size: 13.5px; }
.erow:last-child { border-bottom: none; }
.erow .estart { grid-row: span 2; align-self: start; color: var(--muted); font-size: 12px; padding-top: 1px; }
.erow .estart b { color: var(--ink); font-size: 14px; }
.ehorse { font-weight: 600; }
.eppl { grid-column: 2; color: var(--muted); font-size: 12.5px; }
.eppl .place { color: var(--gold); font-weight: 600; }
.footnote { color: var(--muted); font-size: 12px; text-align: center; margin-top: 30px; }
#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--ink); color: #fff; padding: 8px 16px; border-radius: 8px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity .25s; z-index: 50; }
#toast.show { opacity: 1; }
#printHead { display: none; }
@media (min-width: 900px) {
  #layout { display: flex; gap: 18px; align-items: flex-start; padding: 14px; }
  aside { width: 320px; flex: none; position: sticky; top: 92px; border: 1px solid var(--line); border-radius: 12px; max-height: calc(100vh - 110px); overflow-y: auto; }
  .fgroup { border-bottom: 1px solid var(--line); }
  main { flex: 1; padding: 4px 0 60px; }
}
@media print {
  header .actions, aside, #toast, .chev { display: none !important; }
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
  <div class="actions">
    <button class="primary" id="printBtn">Print</button>
    <button id="copyBtn">Copy link</button>
    <button id="clearBtn">Clear selection</button>
  </div>
</header>
<div id="layout">
  <aside id="filters"></aside>
  <main id="schedule"></main>
</div>
<div id="toast"></div>
<script>
"use strict";
const DATA = __PAYLOAD__;
const LS_KEY = "wchs2026.sel.v1";
const FIELDS = [
  {key:"trainer", label:"Trainers", col:3},
  {key:"rider",   label:"Riders",   col:2},
  {key:"horse",   label:"Horses",   col:1},
  {key:"owner",   label:"Owners",   col:4},
];
const state = {trainer:new Set(), rider:new Set(), horse:new Set(), owner:new Set(), division:new Set()};
const search = {trainer:"", rider:"", horse:"", owner:"", division:""};
const openCls = new Set();

function norm(s){ return (s||"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim(); }

// ---- build name indexes
const NAMES = {trainer:{}, rider:{}, horse:{}, owner:{}};
const DIVS = {};
for (const c of DATA.classes){
  DIVS[norm(c.div)] = c.div;
  for (const e of c.e){
    const t = norm(e[3]); if (t) (NAMES.trainer[t] ||= {d:e[3], n:0}).n++;
    const r = norm(e[2]); if (r) (NAMES.rider[r]   ||= {d:e[2], n:0}).n++;
    const h = norm(e[1]); if (h) (NAMES.horse[h]   ||= {d:e[1], n:0}).n++;
    const o = norm(e[4]); if (o) (NAMES.owner[o]   ||= {d:e[4], n:0}).n++;
  }
}
const DIV_LIST = Object.values(DIVS).sort();

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
      more.style.cssText="width:100%;margin-top:4px;padding:6px;border:1px solid var(--line);background:#fff;border-radius:8px;cursor:pointer;font-size:12.5px;color:var(--muted);";
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

function renderSchedule(){
  const main = $("#schedule");
  main.textContent = "";
  const days = buildSchedule();
  const on = active();
  let shown = 0;
  for (const d of days){
    const secs = [...d.sessions.entries()].sort((a,b)=>(PER_ORDER[a[0]]??9)-(PER_ORDER[b[0]]??9));
    const dEl = el("section","day");
    const h2 = el("h2");
    h2.appendChild(el("span",null, d.wk + ", " + d.day));
    dEl.appendChild(h2);
    let dShown = 0;
    for (const [per, cls] of secs){
      const vis = cls.filter(clsMatches);
      if (!vis.length) continue;
      dShown += vis.length;
      const sEl = el("div","session");
      sEl.appendChild(el("h3",null, per + (cls[0].time ? " · " + cls[0].time : "")));
      for (const c of vis.sort((a,b)=>parseFloat(a.n)-parseFloat(b.n))){
        shown++;
        sEl.appendChild(makeClass(c, on));
      }
      dEl.appendChild(sEl);
    }
    if (!dShown) continue;
    if (on) h2.appendChild(el("span","dsub", " — " + dShown + " of " + d.n + " classes"));
    main.appendChild(dEl);
  }
  if (!shown){
    main.appendChild(el("div","fnote","Nothing matches your selection. Try removing a filter."));
  }
  const sub = $("#phSub");
  if (sub){
    const parts = FIELDS.filter(f=>state[f.key].size).map(f=>f.label+": "+[...state[f.key]].map(k=>namesDisp(f.key,k)).join(", "));
    if (state.division.size) parts.push("Divisions: "+[...state.division].map(k=>DIVS[k]).join(", "));
    sub.textContent = (parts.join("  ·  ") || "Full schedule") + "  —  generated " + DATA.asof;
  }
}
function namesDisp(key,k){ const m = NAMES[key] && NAMES[key][k]; return m ? m.d : k; }

function makeClass(c, on){
  const visE = on ? c.e.filter(eMatches) : c.e;
  const sortE = a => [...a].sort((x,y)=>{
    const sa = x[5]==null ? 9999 : parseInt(x[5])||0, sb = y[5]==null ? 9999 : parseInt(y[5])||0;
    return sa - sb;
  });
  const buildRows = (box, entries) => {
    for (const e of sortE(entries)){
      const row = el("div","erow");
      const st = el("span","estart");
      st.innerHTML = e[5]!=null ? "st&nbsp;<b>"+e[5]+"</b>" : "—";
      row.appendChild(st);
      row.appendChild(el("span","ehorse", e[1]));
      const ppl = el("span","eppl");
      if (e[6]!=null) ppl.appendChild(el("span","place", e[6]+placeSuf(e[6]) + "  "));
      ppl.appendChild(document.createTextNode(e[2] + (e[3] && e[3]!==e[2] ? "  ·  " + e[3] : "")));
      row.appendChild(ppl);
      box.appendChild(row);
    }
  };
  const d = el("div","cls");
  const head = el("button","cls-head");
  head.appendChild(el("span","cnum", c.n));
  head.appendChild(el("span","cname", c.name));
  head.appendChild(el("span","cdiv", c.div));
  head.appendChild(el("span","ccount", on ? visE.length+" of "+c.e.length+" entries" : c.e.length+" entries"));
  head.appendChild(el("span","chev","▶"));
  d.appendChild(head);
  const box = el("div","cls-entries");
  d.appendChild(box);
  const shouldOpen = on || openCls.has(c.n);
  if (shouldOpen){ d.classList.add("open"); buildRows(box, visE); }
  head.addEventListener("click", ()=>{
    if (!d.classList.contains("open") && !box.firstChild){ buildRows(box, on ? c.e.filter(eMatches) : c.e); }
    d.classList.toggle("open");
    d.classList.contains("open") ? openCls.add(c.n) : openCls.delete(c.n);
  });
  return d;
}
function placeSuf(p){ p=String(p); return p.endsWith("1")&&!p.endsWith("11")?"st":p.endsWith("2")?"nd":p.endsWith("3")?"rd":"th"; }

function onStateChange(){
  save();
  for (const g of document.querySelectorAll("#filters .fgroup")) g._update && g._update();
  renderSchedule();
}

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

// ---- init
const src = load();
renderFilters();
renderSchedule();
if (src) toast("Restored your selection");
</script>
</body>
</html>
"""

html = html.replace("__PAYLOAD__", payload)
open('index.html', 'w').write(html)
import os
print(f"index.html: {os.path.getsize('index.html')/1024/1024:.2f} MB")
