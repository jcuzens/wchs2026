"use strict";
// Smoke tests for the generated WCHS 2026 schedule page.
// Reads ../index.html (build it first: python3 refresh/build_page.py).
//
// "now" is pinned to 2026-08-25 10:00 (show day 4) so day-collapse defaults
// are deterministic no matter when the suite runs.
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const HTML = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const PL = HTML.match(/^const DATA = (.*);$/m);
if (!PL) { console.error("FAIL  payload line not found in index.html"); process.exit(1); }
const DATA = JSON.parse(PL[1]);

const PIN_MS = Date.parse("2026-08-25T10:00:00");
function pinDate(w){
  const shift = PIN_MS - Date.now();
  const Real = w.Date;
  class D extends Real {
    constructor(...a){ a.length ? super(...a) : super(Real.now() + shift); }
    static now(){ return Real.now() + shift; }
  }
  w.Date = D;
}
function makeDom(opts){
  return new JSDOM(HTML, Object.assign({
    runScripts: "dangerously",
    url: "https://example.com/index.html",
    pretendToBeVisual: true,
  }, opts || {}));
}

let failures = 0, checks = 0;
function check(name, cond, extra){
  checks++;
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  [" + extra + "]" : ""));
  if (!cond) failures++;
}
const norm = s => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const isDone = c => c.e.some(e => e[6] != null);
const DONE_COUNT = DATA.classes.filter(isDone).length;
const TOTAL = DATA.classes.length;   // grows during the show (late entries join)

const TRAINER = "STACHOWSKI, JAMES";
const tNorm = norm(TRAINER);
const matchTrainer = c => c.e.some(e => norm(e[3]) === tNorm);
const MATCHED_COUNT = DATA.classes.filter(matchTrainer).length;
const SC = DATA.classes.find(c => c.n === "1");            // show-all target
const SC_MINE = SC.e.filter(e => norm(e[3]) === tNorm).length;

// mirror of the page's display order: day -> session -> class number
const PER_ORDER = {Morning:0, Afternoon:1, Night:2, Evening:2};
function orderedClasses(){
  const byDay = new Map();
  for (const c of DATA.classes){
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
const FRONTIER = orderedClasses().find(c => !isDone(c));
const FRONTIER_NUM = FRONTIER ? FRONTIER.n : null;
const FRONTIER_MATCHED = FRONTIER ? matchTrainer(FRONTIER) : false;
const FRONTIER_EXTRA = FRONTIER_NUM && !FRONTIER_MATCHED ? 1 : 0;   // card injected beyond matches
const FILTERED_SHOWN = MATCHED_COUNT + FRONTIER_EXTRA;
const MUTED_SHOWN = TOTAL - MATCHED_COUNT - FRONTIER_EXTRA;         // frontier never muted

const dom = makeDom({ beforeParse: pinDate });
const w = dom.window, doc = w.document;
w.addEventListener("error", e => { console.log("WINDOW ERROR:", e.message); failures++; });

setTimeout(() => {
  // ---------- initial render (desktop width 1024, now = Aug 25) ----------
  check("payload: at least the initial 210 classes", DATA.classes.length >= 210, String(DATA.classes.length));
  check("8 day sections render", doc.querySelectorAll("main .day").length === 8, "got " + doc.querySelectorAll("main .day").length);
  check("15 sessions render", doc.querySelectorAll("main .session").length === 15, "got " + doc.querySelectorAll("main .session").length);
  check("all classes render", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);
  check("entries lazy-built (0 rows initially)", doc.querySelectorAll("main .erow").length === 0, "got " + doc.querySelectorAll("main .erow").length);
  check("5 filter groups", doc.querySelectorAll("#filters .fgroup").length === 5, "got " + doc.querySelectorAll("#filters .fgroup").length);

  // (2) last updated at top
  const upd = doc.getElementById("updatedLine");
  check("updated line present", !!upd);
  check("updated line formatted", !!upd && /^Updated (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4} · \d{1,2}:\d{2} (AM|PM)$/.test(upd.textContent), upd ? upd.textContent : "missing");

  // (1) filters panel toggle
  const fbtn = doc.getElementById("filtersBtn");
  check("filters button present", !!fbtn);
  check("filters expanded on desktop default", !!fbtn && fbtn.classList.contains("on") && !doc.body.classList.contains("nofilters"));
  const dfo = x => typeof w.defaultFiltersOpen === "function" && w.defaultFiltersOpen(x);
  check("defaultFiltersOpen unit", dfo(375) === false && dfo(900) === true && dfo(1024) === true);

  // (6) completed-class treatment
  check("done pills rendered for placed classes", doc.querySelectorAll(".cdone").length === DONE_COUNT, doc.querySelectorAll(".cdone").length + " vs " + DONE_COUNT);
  check("done cards tinted", doc.querySelectorAll("main .cls.done").length === DONE_COUNT, "got " + doc.querySelectorAll("main .cls.done").length);
  check("current card count matches expected", doc.querySelectorAll("main .cls.now").length === (FRONTIER_NUM ? 1 : 0), "got " + doc.querySelectorAll("main .cls.now").length);
  if (FRONTIER_NUM){
    const nowCard = doc.querySelector("main .cls.now");
    check("current card is expected frontier", !!nowCard && nowCard.querySelector(".cnum").textContent === FRONTIER_NUM, (nowCard && nowCard.querySelector(".cnum").textContent) + " vs " + FRONTIER_NUM);
    check("current card has up-next pill", !!nowCard && !!nowCard.querySelector(".cnow"));
    const cards = [...doc.querySelectorAll("main .cls")];
    const nowIdx = cards.findIndex(x => x.classList.contains("now"));
    check("all classes before current are done", nowIdx >= 0 && cards.slice(0, nowIdx).every(x => x.classList.contains("done")), "idx " + nowIdx);
    check("current card never muted", !doc.querySelector("main .cls.now.muted"));
  }

  // (8) past days auto-collapsed (pinned Aug 25)
  const dayOf = d => [...doc.querySelectorAll("main .day")].find(el => el.querySelector("h2").textContent.includes(d));
  const ipd = d => typeof w.isPastDay === "function" && w.isPastDay(d, new w.Date(2026, 7, 25));
  check("isPastDay unit: past", ipd("August 22") === true);
  check("isPastDay unit: same day", ipd("August 25") === false);
  check("isPastDay unit: future", ipd("August 26") === false);
  check("past day (Aug 22) starts collapsed", !!dayOf("August 22") && dayOf("August 22").classList.contains("collapsed"));
  check("today (Aug 25) starts expanded", !!dayOf("August 25") && !dayOf("August 25").classList.contains("collapsed"));
  check("future day (Aug 29) starts expanded", !!dayOf("August 29") && !dayOf("August 29").classList.contains("collapsed"));
  // (7) day header toggles
  const d25 = dayOf("August 25");
  d25.querySelector("h2").click();
  check("day header click collapses", d25.classList.contains("collapsed"));
  d25.querySelector("h2").click();
  check("day header click re-expands", !d25.classList.contains("collapsed"));

  // ---------- filters toggle (1) ----------
  if (fbtn) fbtn.click();
  check("filters button hides aside", doc.body.classList.contains("nofilters"));
  check("view state persisted (filters closed)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").filtersOpen === false);
  if (fbtn) fbtn.click();
  check("filters button re-shows aside", !doc.body.classList.contains("nofilters"));

  // ---------- done toggle (4) ----------
  const dbtn = doc.getElementById("doneBtn");
  check("done button present", !!dbtn);
  check("done button default label", !!dbtn && dbtn.textContent === "Hide done");
  check("done classes shown by default", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);
  if (dbtn) dbtn.click();
  check("hide done removes placed classes", doc.querySelectorAll("main .cls").length === TOTAL - DONE_COUNT, "got " + doc.querySelectorAll("main .cls").length);
  check("no done pills when hidden", doc.querySelectorAll(".cdone").length === 0);
  if (FRONTIER_NUM){
    check("current card visible with done hidden", !!doc.querySelector("main .cls.now"));
    check("current card first when done hidden", doc.querySelector("main .cls") === doc.querySelector("main .cls.now"));
  }
  check("done button label flips", !!dbtn && dbtn.textContent === "Show done" && dbtn.classList.contains("on"));
  check("view state persisted (done hidden)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").doneHidden === true);
  if (dbtn) dbtn.click();
  check("show done restores classes", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);

  // ---------- select a trainer ----------
  const groups = doc.querySelectorAll("#filters .fgroup");
  const gT = groups[0];
  const si = gT.querySelector(".fsearch");
  si.value = "stachowski";
  si.dispatchEvent(new w.Event("input", { bubbles: true }));
  const tboxes = [...gT.querySelectorAll(".frow input")];
  check("trainer search finds results", tboxes.length > 0, "got " + tboxes.length);
  const target = tboxes.find(cb => cb.closest(".frow").querySelector("label").textContent === TRAINER);
  check("found target trainer checkbox", !!target);
  if (target) target.click();
  check("schedule filtered to matching classes", doc.querySelectorAll("main .cls").length === FILTERED_SHOWN, "got " + doc.querySelectorAll("main .cls").length + " vs " + FILTERED_SHOWN);
  if (FRONTIER_NUM){
    check("current card shown when filtered", !!doc.querySelector("main .cls.now"), "got " + doc.querySelectorAll("main .cls.now").length);
    check("current card not muted when filtered", !doc.querySelector("main .cls.now.muted"));
  }
  check("filtered classes auto-open", doc.querySelectorAll("main .cls.open").length === MATCHED_COUNT, doc.querySelectorAll("main .cls.open").length + "/" + MATCHED_COUNT);
  const badRows = [...doc.querySelectorAll("main .erow")].filter(r => !r.textContent.includes(TRAINER));
  check("all visible entries match trainer", badRows.length === 0, "bad: " + badRows.length);
  check("badge shows 1 selected", gT.querySelector(".selcount").textContent === "1", "got " + gT.querySelector(".selcount").textContent);
  check("chip shows selected name", gT.querySelector(".chip") && gT.querySelector(".chip").textContent.includes(TRAINER));
  check("localStorage saved", (JSON.parse(w.localStorage.getItem("wchs2026.sel.v1") || "{}").t || []).length === 1, w.localStorage.getItem("wchs2026.sel.v1"));
  check("hash persisted", w.location.hash.includes("t="), w.location.hash);
  const cbSel = doc.getElementById("contextBtn");
  check("context enabled with selection", cbSel && cbSel.disabled === false);

  // ---------- (9) per-class show all entries ----------
  const c1 = [...doc.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === "1");
  check("class 1 visible after filter", !!c1);
  const call = c1 && c1.querySelector(".call");
  check("show-all button present", !!call, call ? call.textContent : "missing");
  check("filtered rows initially", c1.querySelectorAll(".erow").length === SC_MINE, "got " + c1.querySelectorAll(".erow").length);
  if (call) call.click();
  check("show all expands to full entries", c1.querySelectorAll(".erow").length === SC.e.length, "got " + c1.querySelectorAll(".erow").length);
  // the left column surfaces the entry number — the identity of each entry
  const shownNums = [...c1.querySelectorAll(".erow .eentry")].map(n => n.textContent.trim()).sort();
  const allNums = SC.e.map(e => e[0]).sort();
  check("entry number shown on every row", shownNums.length === allNums.length && shownNums.every((x, i) => x === allNums[i]), shownNums.length + " vs " + allNums.length + (shownNums.length ? "" : "  (no .eentry elements found)"));
  const call2 = c1.querySelector(".call");
  check("call button flips to show mine", !!call2 && call2.textContent === "Show mine " + SC_MINE, call2 ? call2.textContent : "missing");
  if (call2) call2.click();
  check("show mine restores filtered rows", c1.querySelectorAll(".erow").length === SC_MINE, "got " + c1.querySelectorAll(".erow").length);

  // ---------- (3)+(5) context: show non-matching, muted ----------
  const xbtn = doc.getElementById("contextBtn");
  check("context button present", !!xbtn);
  if (xbtn) xbtn.click();
  check("context shows all classes", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);
  check("non-matching classes muted", doc.querySelectorAll("main .cls.muted").length === MUTED_SHOWN, "got " + doc.querySelectorAll("main .cls.muted").length + " vs " + MUTED_SHOWN);
  if (FRONTIER_NUM) check("current card shown in context", !!doc.querySelector("main .cls.now"));
  check("muted classes not auto-open", doc.querySelectorAll("main .cls.muted.open").length === 0);
  check("view state persisted (context on)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").context === true);
  const muted = doc.querySelector("main .cls.muted");
  const mdata = muted && DATA.classes.find(c => c.n === muted.querySelector(".cnum").textContent);
  if (muted) muted.querySelector(".cls-head").click();
  check("muted class opens with all its entries", !!muted && !!mdata && muted.querySelectorAll(".erow").length === mdata.e.length, muted ? muted.querySelectorAll(".erow").length + " vs " + (mdata ? mdata.e.length : "?") : "no muted class");
  check("muted class has no show-all button", !!muted && !muted.querySelector(".call"));
  if (xbtn) xbtn.click();
  check("context off restores filtered view", doc.querySelectorAll("main .cls").length === FILTERED_SHOWN, "got " + doc.querySelectorAll("main .cls").length + " vs " + FILTERED_SHOWN);

  const hash = w.location.hash;

  // ---------- reload with hash (selection restore) ----------
  const dom2 = makeDom({ beforeParse: pinDate, url: "https://example.com/index.html" + hash });
  setTimeout(() => {
    const d2 = dom2.window.document;
    check("hash restore: filtered schedule", d2.querySelectorAll("main .cls").length === FILTERED_SHOWN, "got " + d2.querySelectorAll("main .cls").length + " vs " + FILTERED_SHOWN);
    const gT2 = d2.querySelectorAll("#filters .fgroup")[0];
    check("hash restore: chip restored", gT2.querySelector(".chip") && gT2.querySelector(".chip").textContent.includes(TRAINER));

    // clear selection
    d2.querySelector("#clearBtn").click();
    check("clear restores full schedule", d2.querySelectorAll("main .cls").length === TOTAL, "got " + d2.querySelectorAll("main .cls").length);
    check("clear empties selection storage", Object.keys(JSON.parse(dom2.window.localStorage.getItem("wchs2026.sel.v1") || "{}")).length === 0, dom2.window.localStorage.getItem("wchs2026.sel.v1"));
    const cbClr = d2.getElementById("contextBtn");
    check("context disabled after clear", cbClr && cbClr.disabled === true);

    // division filter
    const gDiv = d2.querySelectorAll("#filters .fgroup")[4];
    gDiv.querySelector(".fsearch").value = "roadster pony";
    gDiv.querySelector(".fsearch").dispatchEvent(new dom2.window.Event("input", { bubbles: true }));
    const dvbox = [...gDiv.querySelectorAll(".frow input")].find(cb => cb.closest(".frow").querySelector("label").textContent === "Roadster Pony");
    if (dvbox) dvbox.click();
    const classes5 = d2.querySelectorAll("main .cls").length;
    const divsShown = new Set([...d2.querySelectorAll("main .cls .cdiv")].map(n => n.textContent));
    // expectations include the injected "current" card when it is not a Roadster Pony class
    const rp = norm("Roadster Pony");
    const fInRp = FRONTIER_NUM && DATA.classes.some(c => c.n === FRONTIER_NUM && norm(c.div) === rp);
    const expectedDivs = new Set(DATA.classes.filter(c => norm(c.div) === rp).map(c => c.div));
    if (FRONTIER_NUM && !fInRp) expectedDivs.add(FRONTIER.div);
    const expectedN = DATA.classes.filter(c => norm(c.div) === rp).length + (FRONTIER_NUM && !fInRp ? 1 : 0);
    check("division filter works", classes5 === expectedN && divsShown.size === expectedDivs.size && [...expectedDivs].every(x => divsShown.has(x)), [...divsShown].join() + " / " + classes5);

    // ---------- (1) mobile default: filters collapsed ----------
    const dom3 = makeDom({
      beforeParse: wd => {
        pinDate(wd);
        Object.defineProperty(wd, "innerWidth", { value: 375, configurable: true });
      },
    });
    setTimeout(() => {
      const d3 = dom3.window.document;
      const fbtn3 = d3.getElementById("filtersBtn");
      check("filters collapsed on mobile default", d3.body.classList.contains("nofilters"));
      check("filters button off on mobile default", !!fbtn3 && !fbtn3.classList.contains("on"));
      check("schedule still renders on mobile default", d3.querySelectorAll("main .cls").length === TOTAL, "got " + d3.querySelectorAll("main .cls").length);

      console.log("\n" + (checks - failures) + "/" + checks + " checks passed" + (failures ? "  —  " + failures + " FAILURES" : "  —  ALL TESTS PASSED"));
      process.exit(failures ? 1 : 0);
    }, 300);
  }, 300);
}, 300);
