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
const PL = HTML.match(/^(?:const|let) DATA = (.*);$/m);
if (!PL) { console.error("FAIL  payload line not found in index.html"); process.exit(1); }
const DATA = JSON.parse(PL[1]);
const DATA_JSON = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "refresh", "data.json"), "utf8"));
// classes whose source data has scratched entries -> expected "sc" payload lists
const SCRATCH_SRC = DATA_JSON
  .map(c => ({ n: c.num, sc: c.entries.filter(e => e.scratch).map(e => e.entry).sort() }))
  .filter(x => x.sc.length);

const PIN_MS = Date.parse("2026-08-25T10:00:00");
function pinDate(w){
  const shift = PIN_MS - Date.now();
  const Real = w.Date;
  let adv = 0;
  class D extends Real {
    constructor(...a){ a.length ? super(...a) : super(Real.now() + shift + adv); }
    static now(){ return Real.now() + shift + adv; }
  }
  w.Date = D;
  w.__advance = ms => { adv += ms; };   // tick test: move the pinned clock
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
function orderedClassesOf(cls){
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
const orderedClasses = () => orderedClassesOf(DATA.classes);
// mirror of the page's up-next logic; the DOM identity checks cross-check
// it against the page's own upNextCls, while the mirror keeps count
// expectations computable before the dom exists
function onNowOf(cls, nowMs){
  let best = null;
  for (const c of cls){
    if (isDone(c) || c.ps == null || c.pe == null) continue;
    if (c.ps * 1000 <= nowMs && nowMs < c.pe * 1000 && (!best || c.ps > best.ps)) best = c;
  }
  return best;
}
function upNextOf(cls, nowMs){
  const on = onNowOf(cls, nowMs);
  if (on) return on;
  for (const c of orderedClassesOf(cls))
    if (!isDone(c) && c.ps != null && c.ps * 1000 > nowMs) return c;
  return null;
}
const HOT = upNextOf(DATA.classes, PIN_MS);
const HOT_NUM = HOT ? HOT.n : null;
const HOT_MATCHED = HOT ? matchTrainer(HOT) : false;
const HOT_EXTRA = HOT_NUM && !HOT_MATCHED ? 1 : 0;   // card injected beyond matches
const FILTERED_SHOWN = MATCHED_COUNT + HOT_EXTRA;
const MUTED_SHOWN = TOTAL - MATCHED_COUNT - HOT_EXTRA;         // hot card never muted

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
  check("no ring when polling is inactive", !doc.querySelector(".ring"), "ring present in plain dom");

  // (1) filters panel toggle
  const fbtn = doc.getElementById("filtersBtn");
  check("filters button present", !!fbtn);
  check("filters expanded on desktop default", !!fbtn && fbtn.classList.contains("on") && !doc.body.classList.contains("nofilters"));
  const dfo = x => typeof w.defaultFiltersOpen === "function" && w.defaultFiltersOpen(x);
  check("defaultFiltersOpen unit", dfo(375) === false && dfo(900) === true && dfo(1024) === true);

  // (6) completed-class treatment + predicted-pace status
  check("done pills rendered for placed classes", doc.querySelectorAll(".cdone").length === DONE_COUNT, doc.querySelectorAll(".cdone").length + " vs " + DONE_COUNT);
  check("done cards tinted", doc.querySelectorAll("main .cls.done").length === DONE_COUNT, "got " + doc.querySelectorAll("main .cls.done").length);
  const pageHot = w.upNextCls(DATA.classes, PIN_MS);
  check("mirror matches the page's upNextCls",
        (pageHot ? pageHot.n : null) === HOT_NUM, (pageHot && pageHot.n) + " vs " + HOT_NUM);
  check("current card count matches expected",
        doc.querySelectorAll("main .cls.now").length === (HOT_NUM ? 1 : 0), "got " + doc.querySelectorAll("main .cls.now").length);
  if (HOT_NUM){
    const nowCard = doc.querySelector("main .cls.now");
    check("current card is expected up-next",
          !!nowCard && nowCard.querySelector(".cnum").textContent === (pageHot ? pageHot.n : HOT_NUM),
          (nowCard && nowCard.querySelector(".cnum").textContent) + " vs " + HOT_NUM);
    const pillTxt = nowCard ? (nowCard.querySelector(".cnow").textContent || "") : "";
    const pillRe = (pageHot && pageHot.ps * 1000 <= PIN_MS && PIN_MS < pageHot.pe * 1000)
      ? /on now · est \d{1,2}:\d{2} (AM|PM)/ : /up next · est \d{1,2}:\d{2} (AM|PM)/;
    check("current card pill shows a predicted time", !!nowCard && pillRe.test(pillTxt), pillTxt);
    const cards = [...doc.querySelectorAll("main .cls")];
    const nowIdx = cards.findIndex(x => x.classList.contains("now"));
    check("cards before current are done, awaiting, or in-window",
          nowIdx >= 0 && cards.slice(0, nowIdx).every(x => {
            const c = DATA.classes.find(cc => cc.n === x.querySelector(".cnum").textContent);
            return x.classList.contains("done") || x.querySelector(".cpend") ||
              (c && c.pe != null && c.ps * 1000 <= PIN_MS && PIN_MS < c.pe * 1000);
          }), "idx " + nowIdx);
    check("current card never muted", !doc.querySelector("main .cls.now.muted"));
  }
  const PENDING_EXPECT = DATA.classes.filter(c => !isDone(c) && c.pe != null && c.pe * 1000 <= PIN_MS).length;
  check("awaiting-results pills match expectation",
        doc.querySelectorAll("main .cpend").length === PENDING_EXPECT,
        doc.querySelectorAll("main .cpend").length + " vs " + PENDING_EXPECT);
  const fnote = doc.querySelector("main .footnote");
  check("pace footnote present", !!fnote && fnote.textContent.includes("predictions"), fnote ? fnote.textContent : "missing");

  // (11) predicted-pace helpers (synthetic classes; the page's own fns)
  const C = (n, ps, pe, done, day, per) => ({
    n, day: day || "August 25", per: per || "Morning", ps, pe,
    e: done ? [["1","H","R","T","O","1","1"]] : [["1","H","R","T","O","1",null]],
  });
  const T0 = 1000000;
  const mOn = x => w.onNowCls(x, T0);
  check("onNow: inside window", mOn([C("1", T0/1000-10, T0/1000+10)]).n === "1");
  check("onNow: at ps boundary is on", mOn([C("1", T0/1000, T0/1000+10)]).n === "1");
  check("onNow: at pe boundary is off", mOn([C("1", T0/1000-10, T0/1000)]) === null);
  check("onNow: overlap -> latest ps wins",
        mOn([C("1", T0/1000-100, T0/1000+50), C("2", T0/1000-10, T0/1000+60)]).n === "2");
  check("onNow: done class never on", mOn([C("1", T0/1000-10, T0/1000+10, true)]) === null);
  check("onNow: missing ps -> null",
        mOn([{n:"1", day:"August 25", per:"Morning", pe:T0/1000+10, e:[["1","H","R","T","O","1",null]]}]) === null);
  const mUp = x => w.upNextCls(x, T0);
  check("upNext: on-now class wins",
        mUp([C("1", T0/1000-10, T0/1000+10), C("2", T0/1000+20, T0/1000+30)]).n === "1");
  check("upNext: first future in display order",
        mUp([C("10", T0/1000+200, T0/1000+210, false, "August 26"),
             C("3", T0/1000+20, T0/1000+30, false, "August 25", "Night"),
             C("2", T0/1000+10, T0/1000+12)]).n === "2");
  check("upNext: done classes skipped",
        mUp([C("1", T0/1000+20, T0/1000+30, true), C("2", T0/1000+40, T0/1000+50)]).n === "2");
  check("upNext: all past or done -> null",
        mUp([C("1", T0/1000-100, T0/1000-90), C("2", T0/1000-50, T0/1000-40, true)]) === null);
  const mPend = x => w.isPendingCls(x, T0);
  check("pending: at pe is pending", mPend(C("1", T0/1000-10, T0/1000)) === true);
  check("pending: before pe is not", mPend(C("1", T0/1000-10, T0/1000+1)) === false);
  check("pending: done never pending", mPend(C("1", T0/1000-10, T0/1000-5, true)) === false);
  check("pending: missing pe is not",
        mPend({n:"1", day:"August 25", per:"Morning", ps:T0/1000-10, e:[["1","H","R","T","O","1",null]]}) === false);
  const f0 = Date.UTC(2026, 7, 25, 23, 15) / 1000;   // 7:15 PM on show day (EDT)
  check("fmtShowTime: show-zone wall clock", w.fmtShowTime(f0) === "7:15 PM", w.fmtShowTime(f0));

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
  if (HOT_NUM){
    check("current card visible with done hidden", !!doc.querySelector("main .cls.now"));
  }
  check("done button label flips", !!dbtn && dbtn.textContent === "Show done" && dbtn.classList.contains("on"));
  check("view state persisted (done hidden)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").doneHidden === true);
  if (dbtn) dbtn.click();
  check("show done restores classes", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);

  // ---------- CSS audit: buttons must declare a text color ----------
  // In real browsers <button> does NOT inherit color (UA default is black),
  // so a header button without color: renders near-black text in dark mode.
  // (jsdom models inheritance for buttons, so this is a rule audit, not a
  // computed-style check.)
  const css = [...doc.querySelectorAll("style")].map(s => s.textContent).join("\n");
  const headRule = (css.match(/(^|\n)\.cls-head\s*\{([^}]*)\}/) || [])[2];
  check("cls-head declares explicit color (button UA default is black)", headRule != null && /(^|;|\s)color\s*:/.test(headRule), headRule != null ? headRule.slice(0, 100) : "rule missing");
  // placements must stay highlighted (gold) on other/muted rows so you can
  // see who placed where; the rest of the row stays muted
  const placeRules = [...css.matchAll(/((?:^|\n)[^{}\n]*erow\.other[^{}\n]*\.place[^{}\n]*)\{([^}]*)\}/g)];
  check("other-row .place stays gold (not muted)", placeRules.length >= 1 && placeRules.every(r => /color\s*:\s*var\(--gold\)/.test(r[2]) && !r[2].includes("var(--muted)")), placeRules.map(r => r[1].trim() + " { " + r[2].trim() + " }").join(" | ").slice(0, 160));

  // ---------- scratch entries (withdrawn before their class) ----------
  const scrPayload = DATA.classes.map(c => ({ n: c.n, sc: c.sc || [] }));
  check("payload carries sc for every class with scratched entries",
        SCRATCH_SRC.length === 0 ||
        SCRATCH_SRC.every(s => {
          const p = scrPayload.find(x => x.n === s.n);
          return p && p.sc.length === s.sc.length && s.sc.every(n => p.sc.includes(n));
        }),
        "src " + SCRATCH_SRC.length + " vs payload classes with sc: " + scrPayload.filter(x => x.sc.length).length);
  const SCR = DATA.classes.find(c => c.sc && c.sc.length);
  if (SCR){
    const scrCard = [...doc.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCR.n);
    scrCard.querySelector(".cls-head").click();
    const rows = [...scrCard.querySelectorAll(".erow")];
    const scrRows = rows.filter(r => r.classList.contains("scratch"));
    check("scratch entries render with the scratch class",
          scrRows.length === SCR.sc.length, scrRows.length + " vs " + SCR.sc.length);
    check("scratch rows are exactly the scratched entry numbers",
          scrRows.every(r => SCR.sc.includes(r.querySelector(".eentry").textContent.trim())) &&
          rows.filter(r => !r.classList.contains("scratch")).length === SCR.e.length - SCR.sc.length);
    check("scratch styling declares background + strikethrough",
          /\.erow\.scratch\s*\{[^}]*background[^}]*\}/.test(css) &&
          /\.erow\.scratch [^{]*\{[^}]*text-decoration\s*:\s*line-through[^}]*\}/.test(css));
  } else {
    check("scratch DOM checks skipped (no scratches in payload)", true, "no class has sc; nothing to render");
  }

  // ---------- scorecard links (judge scorecards posted to Google Drive) ----------
  const CARD_CLS = DATA.classes.filter(c => c.card);
  check("payload classes with scorecards render a chip",
        CARD_CLS.length === 0 ||
        doc.querySelectorAll("main .cscard").length === CARD_CLS.length,
        "payload " + CARD_CLS.length + " vs dom " + doc.querySelectorAll("main .cscard").length);
  if (CARD_CLS.length){
    const scDom = makeDom({ beforeParse: w2 => {
      pinDate(w2);
      w2.__opened = [];
      w2.open = (u, t, o) => { w2.__opened.push([u, t, o]); };
    }});
    const wsc = scDom.window, dsc = wsc.document;
    wsc.addEventListener("error", e => { console.log("WINDOW ERROR (scard):", e.message); failures++; });
    const first = CARD_CLS[0];
    const cardEl = [...dsc.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === first.n);
    const chip = cardEl && cardEl.querySelector(".cscard");
    check("scorecard chip sits in its class card header", !!chip && !!chip.closest(".cls-head"), first.n);
    check("scorecard chip text", !!chip && chip.textContent.trim() === "scorecard \u2197", chip ? JSON.stringify(chip.textContent) : "missing");
    if (chip){
      chip.click();
      check("scorecard click opens the Drive PDF in a new tab",
            wsc.__opened.length === 1 && wsc.__opened[0][0] === first.card && wsc.__opened[0][1] === "_blank",
            JSON.stringify(wsc.__opened));
      check("scorecard click does not open the class card", !cardEl.classList.contains("open"));
    }
    check("chips only on classes with card data",
          [...dsc.querySelectorAll("main .cscard")].every(n => {
            const num = n.closest(".cls").querySelector(".cnum").textContent;
            return CARD_CLS.some(c => c.n === num);
          }));
    check("scorecard chip declares its own color", /\.cscard\s*\{[^}]*color[^}]*\}/.test(css));
  } else {
    check("scorecard DOM checks skipped (no cards in payload)", true, "no class has card; nothing to render");
  }

  // ---------- dark mode toggle ----------
  const tbtn = doc.getElementById("themeBtn");
  check("theme button present", !!tbtn);
  check("theme default light (jsdom system is light)", !!tbtn && tbtn.textContent === "Dark" && !doc.documentElement.classList.contains("dark"), tbtn ? tbtn.textContent : "missing");
  if (tbtn) tbtn.click();
  check("dark class applied to <html>", doc.documentElement.classList.contains("dark"));
  check("theme label flips to Light + on style", !!tbtn && tbtn.textContent === "Light" && tbtn.classList.contains("on"), tbtn ? tbtn.textContent : "missing");
  check("theme persisted (dark)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").theme === "dark");
  if (tbtn) tbtn.click();
  check("light restored on second click", !doc.documentElement.classList.contains("dark") && !!tbtn && tbtn.textContent === "Dark" && !tbtn.classList.contains("on"));
  check("theme persisted (light)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").theme === "light");

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
  if (HOT_NUM){
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
  const cbSel = doc.getElementById("scopeBtn");
  check("scope enabled with selection", cbSel && cbSel.disabled === false);
  check("scope default label is My classes", !!cbSel && cbSel.textContent === "My classes", cbSel ? cbSel.textContent : "missing");

  // ---------- (9) per-class show all entries ----------
  const c1 = [...doc.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === "1");
  check("class 1 visible after filter", !!c1);
  const call = c1 && c1.querySelector(".call");
  check("show-all button present", !!call, call ? call.textContent : "missing");
  check("filtered rows initially", c1.querySelectorAll(".erow").length === SC_MINE, "got " + c1.querySelectorAll(".erow").length);
  if (call) call.click();
  check("show all expands to full entries", c1.querySelectorAll(".erow").length === SC.e.length, "got " + c1.querySelectorAll(".erow").length);
  const nOther = SC.e.length - SC_MINE;
  check("other riders' rows flagged other", c1.querySelectorAll(".erow.other").length === nOther, "got " + c1.querySelectorAll(".erow.other").length + " vs " + nOther);
  check("my rows not flagged other", [...c1.querySelectorAll(".erow")].filter(r => r.textContent.includes(TRAINER)).every(r => !r.classList.contains("other")));
  check("other rows carry a badge", c1.querySelectorAll(".erow.other .eother").length === nOther && c1.querySelectorAll(".erow:not(.other) .eother").length === 0, "badges " + c1.querySelectorAll(".eother").length + " vs " + nOther);
  // the left column surfaces the entry number — the identity of each entry
  const shownNums = [...c1.querySelectorAll(".erow .eentry")].map(n => n.textContent.trim()).sort();
  const allNums = SC.e.map(e => e[0]).sort();
  check("entry number shown on every row", shownNums.length === allNums.length && shownNums.every((x, i) => x === allNums[i]), shownNums.length + " vs " + allNums.length + (shownNums.length ? "" : "  (no .eentry elements found)"));
  const call2 = c1.querySelector(".call");
  check("call button flips to show mine", !!call2 && call2.textContent === "Show mine " + SC_MINE, call2 ? call2.textContent : "missing");
  if (call2) call2.click();
  check("show mine restores filtered rows", c1.querySelectorAll(".erow").length === SC_MINE, "got " + c1.querySelectorAll(".erow").length);
  check("show mine removes other flags", c1.querySelectorAll(".erow.other").length === 0 && c1.querySelectorAll(".eother").length === 0);

  // ---------- (3)+(5) scope: All classes — show non-matching, muted ----------
  const xbtn = doc.getElementById("scopeBtn");
  check("scope button present", !!xbtn);
  check("scope label My classes before toggling", !!xbtn && xbtn.textContent === "My classes", xbtn ? xbtn.textContent : "missing");
  if (xbtn) xbtn.click();
  check("scope label flips to All classes + on", !!xbtn && xbtn.textContent === "All classes" && xbtn.classList.contains("on"), xbtn ? xbtn.textContent : "missing");
  check("scope shows all classes", doc.querySelectorAll("main .cls").length === TOTAL, "got " + doc.querySelectorAll("main .cls").length);
  check("non-matching classes muted", doc.querySelectorAll("main .cls.muted").length === MUTED_SHOWN, "got " + doc.querySelectorAll("main .cls.muted").length + " vs " + MUTED_SHOWN);
  if (HOT_NUM) check("current card shown in scope", !!doc.querySelector("main .cls.now"));
  check("muted classes not auto-open", doc.querySelectorAll("main .cls.muted.open").length === 0);
  check("view state persisted (scope on)", JSON.parse(w.localStorage.getItem("wchs2026.view.v1") || "{}").scope === true);
  const muted = doc.querySelector("main .cls.muted");
  const mdata = muted && DATA.classes.find(c => c.n === muted.querySelector(".cnum").textContent);
  if (muted) muted.querySelector(".cls-head").click();
  check("muted class opens with all its entries", !!muted && !!mdata && muted.querySelectorAll(".erow").length === mdata.e.length, muted ? muted.querySelectorAll(".erow").length + " vs " + (mdata ? mdata.e.length : "?") : "no muted class");
  check("muted class rows all flagged other", !!muted && !!mdata && muted.querySelectorAll(".erow.other").length === mdata.e.length, muted ? muted.querySelectorAll(".erow.other").length + " vs " + (mdata ? mdata.e.length : "?") : "no muted class");
  check("muted class has no show-all button", !!muted && !muted.querySelector(".call"));
  if (xbtn) xbtn.click();
  check("scope off restores filtered view", doc.querySelectorAll("main .cls").length === FILTERED_SHOWN, "got " + doc.querySelectorAll("main .cls").length + " vs " + FILTERED_SHOWN);

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
    const cbClr = d2.getElementById("scopeBtn");
    check("scope disabled after clear", cbClr && cbClr.disabled === true);

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
    const fInRp = HOT_NUM && DATA.classes.some(c => c.n === HOT_NUM && norm(c.div) === rp);
    const expectedDivs = new Set(DATA.classes.filter(c => norm(c.div) === rp).map(c => c.div));
    if (HOT_NUM && !fInRp) expectedDivs.add(HOT.div);
    const expectedN = DATA.classes.filter(c => norm(c.div) === rp).length + (HOT_NUM && !fInRp ? 1 : 0);
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

        // ---------- persisted theme + legacy scope migration (fresh dom) ----------
        const domT = makeDom({ beforeParse: wt => {
          pinDate(wt);
          wt.localStorage.setItem("wchs2026.view.v1", JSON.stringify({ theme: "dark", context: true }));
          wt.localStorage.setItem("wchs2026.sel.v1", JSON.stringify({ t: [norm(TRAINER)] }));
        } });
        const wT = domT.window, dT = wT.document;
        wT.addEventListener("error", e => { console.log("WINDOW ERROR (theme):", e.message); failures++; });

        (function migrationChecks(){
          check("persisted theme dark applied on load", dT.documentElement.classList.contains("dark"), dT.documentElement.className || "no class");
          const tbT = dT.getElementById("themeBtn");
          check("theme label Light when persisted dark", !!tbT && tbT.textContent === "Light" && tbT.classList.contains("on"), tbT ? tbT.textContent : "missing");
          const sbT = dT.getElementById("scopeBtn");
          check("legacy context:true migrates to All classes", !!sbT && sbT.textContent === "All classes" && sbT.classList.contains("on"), sbT ? sbT.textContent : "missing");
          check("migrated selection + scope show all classes", dT.querySelectorAll("main .cls").length === TOTAL, "got " + dT.querySelectorAll("main .cls").length);
        })();

        // ---------- (10) live update: the shell polls payload.json ----------
        // (jsdom has no fetch; this dom stubs it. __POLL_MS=50 speeds the cycle.)
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const P1_ASOF = "2026-08-25 11:00";
        const liveDom = makeDom({
          url: "https://example.com/index.html",
          beforeParse: w => {
            pinDate(w);
            w.__POLL_MS = 50;
            Object.defineProperty(w, "scrollY", { value: 123, configurable: true });
            w.__scrollCalls = [];
            w.scrollTo = (x, y) => w.__scrollCalls.push([x, y]);
            // phase-1 payload: settle the current up-next class, bump asof
            const p1 = JSON.parse(JSON.stringify(DATA));
            const f1 = p1.classes.find(c => c.n === HOT_NUM);
            if (f1 && f1.e.length) f1.e[0][6] = "1";
            p1.asof = P1_ASOF;
            // The page polls check.json (tiny: asof + data hash) every cycle
            // and only fetches payload.json when the hash differs from the
            // embedded one. "diff-1" guarantees the first poll fetches.
            w.__live = { check: { asof: P1_ASOF, h: "diff-1" }, current: p1,
                         fail: false, checkFetches: 0, payloadFetches: 0 };
            w.fetch = async url => {
              if (w.__live.fail) throw new Error("network down");
              if (String(url).indexOf("check.json") !== -1){
                w.__live.checkFetches++;
                return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(w.__live.check)) };
              }
              w.__live.payloadFetches++;
              return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(w.__live.current)) };
            };
          },
        });
        const w4 = liveDom.window, d4 = w4.document;
        w4.addEventListener("error", e => { console.log("WINDOW ERROR (live):", e.message); failures++; });
        // expectations computed from the fetched payload (the show may be over
        // when this runs: HOT_NUM can be null, then p1 differs only by asof)
        const P1 = w4.__live.current;
        const P1_DONE = P1.classes.filter(isDone).length;
        const P1_HOT = upNextOf(P1.classes, PIN_MS);
        const P1_HOT_NUM = P1_HOT ? P1_HOT.n : null;

        (async () => {
          // tick: the predicted pills advance in place (no re-render).
          // A dedicated dom: __TICK_MS=50 set in beforeParse + the pinDate
          // clock seam. (This dom has no fetch stub, so no polling runs.)
          const tickDom = makeDom({
            url: "https://example.com/index.html",
            beforeParse: wt => { pinDate(wt); wt.__TICK_MS = 50; },
          });
          const w5 = tickDom.window, d5 = w5.document;
          w5.addEventListener("error", e => { console.log("WINDOW ERROR (tick):", e.message); failures++; });
          const firstChild5 = d5.querySelector("#schedule").firstChild;
          const tHot = upNextOf(DATA.classes, PIN_MS);
          if (tHot && tHot.pe != null){
            const hotCard = [...d5.querySelectorAll("main .cls")].find(x => x.dataset.num === tHot.n);
            check("tick: hot card highlighted at pinned clock",
                  !!hotCard && hotCard.classList.contains("now"));
            const delta = tHot.pe * 1000 - PIN_MS + 60000;
            w5.__advance(delta);
            await sleep(300);   // several 50 ms ticks at the advanced clock
            const nowMs2 = PIN_MS + delta;
            const tHot2 = upNextOf(DATA.classes, nowMs2);
            check("tick: no re-render (first child identity)",
                  d5.querySelector("#schedule").firstChild === firstChild5);
            check("tick: old hot card lost .now", !!hotCard && !hotCard.classList.contains("now"));
            check("tick: old hot card gained awaiting pill",
                  !!hotCard && !!hotCard.querySelector(".cpend"));
            if (tHot2){
              const hotCard2 = [...d5.querySelectorAll("main .cls")].find(x => x.dataset.num === tHot2.n);
              check("tick: highlight moved to the next class",
                    !!hotCard2 && hotCard2.classList.contains("now") && !!hotCard2.querySelector(".cnow"));
            } else {
              check("tick: no future class -> no highlight",
                    d5.querySelectorAll("main .cls.now").length === 0);
            }
          } else {
            check("tick: no hot at pinned clock -> no highlight",
                  d5.querySelectorAll("main .cls.now").length === 0);
          }

          await sleep(250);   // several 50 ms polls have landed

          // check 0: the first poll went check.json (hash differed from the
          // embedded one) and only then fetched the full payload
          check("live: first poll fetched payload after check.json",
                w4.__live.checkFetches >= 1 && w4.__live.payloadFetches >= 1,
                "check=" + w4.__live.checkFetches + " payload=" + w4.__live.payloadFetches);
          // now serve a matching hash: quiescent polls must be check-only
          w4.__live.check = { asof: P1_ASOF, h: w4.__live.current.h };
          await sleep(50);   // let any in-flight poll settle on the new hash

          // check 1: the page re-rendered from the fetched data
          check("live: done count matches fetched data", d4.querySelectorAll(".cdone").length === P1_DONE, "got " + d4.querySelectorAll(".cdone").length + " vs " + P1_DONE);
          check("live: done cards tinted", d4.querySelectorAll("main .cls.done").length === P1_DONE, "got " + d4.querySelectorAll("main .cls.done").length);
          check("live: up-next card count", d4.querySelectorAll("main .cls.now").length === (P1_HOT_NUM ? 1 : 0), "got " + d4.querySelectorAll("main .cls.now").length);
          if (P1_HOT_NUM){
            const nowCard = d4.querySelector("main .cls.now");
            check("live: up-next moved to expected class", !!nowCard && nowCard.querySelector(".cnum").textContent === P1_HOT_NUM, (nowCard && nowCard.querySelector(".cnum").textContent) + " vs " + P1_HOT_NUM);
          }
          const upd4 = d4.getElementById("updatedLine");
          check("live: updated line shows fetched asof", /^Updated Aug 25, 2026 · 11:00 AM$/.test(upd4.textContent), upd4 ? upd4.textContent : "missing");

          // check 2: user state survives a re-render (selection + open cards)
          // open a trainer-matched card while no filter is active (pure openCls state)
          const SCN = DATA.classes.find(c => c.e.some(e => norm(e[3]) === tNorm)).n;
          const cardN = [...d4.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCN);
          check("live: trainer class card present pre-filter", !!cardN);
          cardN.querySelector(".cls-head").click();
          // apply the trainer selection
          const gT4 = d4.querySelectorAll("#filters .fgroup")[0];
          const si4 = gT4.querySelector(".fsearch");
          si4.value = "stachowski";
          si4.dispatchEvent(new w4.Event("input", { bubbles: true }));
          const target4 = [...gT4.querySelectorAll(".frow input")].find(cb => cb.closest(".frow").querySelector("label").textContent === TRAINER);
          if (target4) target4.click();
          check("live: selection chip shown", !!(gT4.querySelector(".chip") && gT4.querySelector(".chip").textContent.includes(TRAINER)));
          // context mode: muted cards show and never auto-open, which isolates
          // openCls persistence (matched cards auto-open and would confound it)
          d4.getElementById("scopeBtn").click();
          const muted4 = d4.querySelector("main .cls.muted");
          check("live: context shows muted classes", !!muted4);
          const MNUM = muted4.querySelector(".cnum").textContent;
          muted4.querySelector(".cls-head").click();
          // serve one more update: settle the next up-next class
          const p2 = JSON.parse(JSON.stringify(w4.__live.current));
          const f2 = p2.classes.find(c => c.n === P1_HOT_NUM);
          if (f2 && f2.e.length) f2.e[0][6] = "1";
          p2.asof = "2026-08-25 11:05";
          w4.__live.check = { asof: p2.asof, h: "diff-2" };   // hash changed -> refetch
          w4.__live.current = p2;
          await sleep(200);
          const P2 = w4.__live.current;
          const P2_HOT = upNextOf(P2.classes, PIN_MS);
          const P2_HOT_NUM = P2_HOT ? P2_HOT.n : null;
          const gT4a = d4.querySelectorAll("#filters .fgroup")[0];
          check("live: selection keeps its chip after re-render", !!(gT4a.querySelector(".chip") && gT4a.querySelector(".chip").textContent.includes(TRAINER)));
          check("live: context still shows all classes after re-render", d4.querySelectorAll("main .cls").length === TOTAL, "got " + d4.querySelectorAll("main .cls").length);
          const cardNb = [...d4.querySelectorAll("main .cls")].find(x => x.querySelector(".cnum").textContent === SCN);
          check("live: opened matched card stays open", !!cardNb && cardNb.classList.contains("open"));
          const mutedNb = [...d4.querySelectorAll("main .cls.muted")].find(x => x.querySelector(".cnum").textContent === MNUM);
          check("live: opened muted card stays open (openCls survives)", !!mutedNb && mutedNb.classList.contains("open"));
          const nowCard2 = d4.querySelector("main .cls.now");
          check("live: up-next reflects new data", !P2_HOT_NUM ? !nowCard2 : (!!nowCard2 && nowCard2.querySelector(".cnum").textContent === P2_HOT_NUM), (nowCard2 && nowCard2.querySelector(".cnum").textContent) + " vs " + P2_HOT_NUM);
          // back to the filtered view: the count now follows the new data
          d4.getElementById("scopeBtn").click();
          const P2_MATCHED = P2.classes.filter(c => c.e.some(e => norm(e[3]) === tNorm)).length;
          const P2_HOT_MATCHED = P2_HOT ? P2_HOT.e.some(e => norm(e[3]) === tNorm) : false;
          const P2_FILTERED = P2_MATCHED + (P2_HOT_NUM && !P2_HOT_MATCHED ? 1 : 0);
          check("live: filtered count follows new data", d4.querySelectorAll("main .cls").length === P2_FILTERED, "got " + d4.querySelectorAll("main .cls").length + " vs " + P2_FILTERED);

          // check 3: a matching check hash does not re-render (node identity)
          // and does not refetch the full payload
          w4.__live.check = { asof: p2.asof, h: w4.__live.current.h };
          await sleep(50);   // let any in-flight poll settle on the new hash
          const firstChild = d4.querySelector("#schedule").firstChild;
          const payloadFetches3 = w4.__live.payloadFetches;
          await sleep(150);
          check("live: unchanged check does not re-render", d4.querySelector("#schedule").firstChild === firstChild);
          check("live: unchanged check does not refetch payload.json",
                w4.__live.payloadFetches === payloadFetches3,
                "payload=" + w4.__live.payloadFetches + " was " + payloadFetches3);

          // check 4: repeated failures mark the line (+ hide the ring), recovery clears
          w4.__live.fail = true;
          await sleep(250);
          check("live: 3+ failures show not-updating marker", upd4.textContent.endsWith(" · not updating"), upd4.textContent);
          const ringFg5 = d4.querySelector(".ring-fg");
          check("live: ring hidden while not updating", !!ringFg5 && ringFg5.style.display === "none", ringFg5 ? ringFg5.style.display : "missing");
          w4.__live.fail = false;
          await sleep(150);
          check("live: recovery clears marker", !upd4.textContent.includes("not updating"), upd4.textContent);
          check("live: recovery shows ring again", !!ringFg5 && ringFg5.style.display === "");

          // check 5: ring present, dasharray = circumference, transition spans one cycle
          check("live: ring present when polling", !!ringFg5);
          const dash = ringFg5 ? ringFg5.style.strokeDasharray : "";
          check("live: ring dasharray = circumference (2π·6 ≈ 37.7)", Math.abs(parseFloat(dash) - 2 * Math.PI * 6) < 0.1, dash);
          check("live: ring transition spans one poll cycle", !!ringFg5 && ringFg5.style.transition.indexOf("50ms") !== -1, ringFg5 ? ringFg5.style.transition : "missing");

          // check 6: window scroll restored after re-render
          check("live: scroll position restored after re-render", w4.__scrollCalls.some(c => c[0] === 0 && c[1] === 123), JSON.stringify(w4.__scrollCalls));

          // check 7: re-render deferred while a control has focus
          // (in filtered view the settled frontier may be filtered out, so
          //  assert via the up-next pill, not the done count)
          if (P2_HOT_NUM){
            const si4b = d4.querySelectorAll("#filters .fgroup")[0].querySelector(".fsearch");
            si4b.focus();
            check("live: search input can take focus", d4.activeElement === si4b);
            const firstChildBefore = d4.querySelector("#schedule").firstChild;
            const daysBefore = [...d4.querySelectorAll("main .day")].map(el => el.classList.contains("collapsed"));
            // serve one more update: settle the next up-next class
            const p3 = JSON.parse(JSON.stringify(w4.__live.current));
            const f3 = p3.classes.find(c => c.n === P2_HOT_NUM);
            if (f3 && f3.e.length) f3.e[0][6] = "1";
            p3.asof = "2026-08-25 11:10";
            const P3_HOT = upNextOf(p3.classes, PIN_MS);
            const P3_HOT_NUM = P3_HOT ? P3_HOT.n : null;
            w4.__live.check = { asof: p3.asof, h: "diff-3" };   // hash changed -> refetch
            w4.__live.current = p3;
            await sleep(200);
            const nowWhileDeferred = d4.querySelector("main .cls.now");
            check("live: re-render deferred while focused (body unchanged)", d4.querySelector("#schedule").firstChild === firstChildBefore);
            check("live: body still shows old up-next while deferred", !!nowWhileDeferred && nowWhileDeferred.querySelector(".cnum").textContent === P2_HOT_NUM, (nowWhileDeferred && nowWhileDeferred.querySelector(".cnum").textContent) + " vs " + P2_HOT_NUM);
            check("live: header still shows newest asof while deferred", /^Updated Aug 25, 2026 · 11:10 AM/.test(upd4.textContent), upd4.textContent);
            si4b.blur();
            await sleep(100);
            const nowAfter = d4.querySelector("main .cls.now");
            check("live: blur applies the deferred update", d4.querySelector("#schedule").firstChild !== firstChildBefore);
            check("live: up-next advanced after deferred apply", !P3_HOT_NUM ? !nowAfter : (!!nowAfter && nowAfter.querySelector(".cnum").textContent === P3_HOT_NUM), (nowAfter && nowAfter.querySelector(".cnum").textContent) + " vs " + P3_HOT_NUM);
            const gT4b = d4.querySelectorAll("#filters .fgroup")[0];
            check("live: selection survives the deferred re-render", !!(gT4b.querySelector(".chip") && gT4b.querySelector(".chip").textContent.includes(TRAINER)));
            // check 8: day collapse state survives the re-render
            const daysAfter = [...d4.querySelectorAll("main .day")].map(el => el.classList.contains("collapsed"));
            check("live: day collapse state survives re-render", JSON.stringify(daysAfter) === JSON.stringify(daysBefore), JSON.stringify(daysAfter) + " vs " + JSON.stringify(daysBefore));
          }

          // check 9: live pill + live-filled place + up-next follows merged data
          // (scope mode so every class card is rendered regardless of filters)
          d4.getElementById("scopeBtn").click();
          const p4 = JSON.parse(JSON.stringify(w4.__live.current));
          const f4 = orderedClassesOf(p4.classes).find(c => !isDone(c));
          if (f4){
            if (f4.e.length) f4.e[0][6] = "1";   // live places the frontier class's first entry
            f4.live = 12;                        // fresh live activity (minutes ago)
            p4.asof = "2026-08-25 11:15";
            w4.__live.check = { asof: p4.asof, h: "diff-4" };   // hash changed -> refetch
            w4.__live.current = p4;
            await sleep(200);
            const P4_LIVE_NUMS = p4.classes.filter(c => c.live != null).map(c => c.n).sort();
            const pills = [...d4.querySelectorAll("main .cls .clive")]
              .map(n => n.closest(".cls").querySelector(".cnum").textContent).sort();
            check("live: pill rendered exactly for live classes",
                  JSON.stringify(pills) === JSON.stringify(P4_LIVE_NUMS),
                  pills.join() + " vs " + P4_LIVE_NUMS.join());
            const card4 = [...d4.querySelectorAll("main .cls")]
              .find(x => x.querySelector(".cnum").textContent === f4.n);
            if (card4 && f4.e.length){
              // matched cards auto-open in the trainer view (showing only the
              // matched rows), so make the state deterministic instead of
              // assuming a closed card with all rows
              if (!card4.classList.contains("open")) card4.querySelector(".cls-head").click();
              const callEl4 = card4.querySelector(".call");
              if (callEl4) callEl4.click();   // "Show all N" -> every entry row renders
              const en4 = String(f4.e[0][0]);
              const row4 = [...card4.querySelectorAll(".erow")]
                .find(r => r.querySelector(".eentry")
                           && r.querySelector(".eentry").textContent.trim() === en4);
              check("live: live-filled place renders on its entry row",
                    !!row4 && !!row4.querySelector(".place")
                    && row4.querySelector(".place").textContent.includes("1st"),
                    row4 ? row4.textContent.trim() : "row missing");
            }
            const P4_HOT = upNextOf(p4.classes, PIN_MS);
            const nowCard4 = d4.querySelector("main .cls.now");
            check("live: up-next follows merged data",
                  P4_HOT
                    ? (!!nowCard4 && nowCard4.querySelector(".cnum").textContent === P4_HOT.n)
                    : !nowCard4,
                  (nowCard4 && nowCard4.querySelector(".cnum").textContent) + " vs " + (P4_HOT && P4_HOT.n));
          }

          console.log("\n" + (checks - failures) + "/" + checks + " checks passed" + (failures ? "  —  " + failures + " FAILURES" : "  —  ALL TESTS PASSED"));
          process.exit(failures ? 1 : 0);
        })();
    }, 300);
  }, 300);
}, 300);
