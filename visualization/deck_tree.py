"""Draw a mod's AG deck tree as one self-contained HTML page.

The editor shows one battalion at a time: pick a 师, pick a 营, look at its
company/platoon rows.  That answers "what is in this platoon" but never "what
does the whole mod look like" — how the battalions spread across countries and
divisions, which of them are fat, where the equipment repeats.  This turns the
same object graph into a page you can scroll, search and aggregate.

Six levels, matching the editor's own vocabulary so the two do not drift:

    国家 Nat → 师 Div → 营 Bn → 连 Co → 排 Pl → 条目

Read-only.  It opens the mod's ``Deck.ndfbin`` through the same
:class:`~ndfbin_decks.app.session.Session` the GUI uses, so every number here is
the number the editor would show — there is no second parser to disagree with.

Usage::

    python visualization/deck_tree.py --mod Test --out 编制结构.html
    python visualization/deck_tree.py --mod 3395350736

Why the payload is arrays of numbers rather than objects with keys: a large mod
has ~180k entries, and repeating ``"unit": "T72M1"`` 180k times costs megabytes
for nothing.  Equipment names are interned once into ``u`` and referenced by
index; the tree itself is nested arrays.  The page then renders lazily — a
collapsed branch is data, not DOM — so 237k nodes open in about a second.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Run as a script (``python visualization/deck_tree.py``) puts ``visualization/``
# on the path, not the project root.  Add the root so ``ndfbin_decks`` imports
# the same way it does everywhere else — this tool is meant to be runnable by
# double-clicking a .bat, not only from an installed package.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ndfbin_decks import APP_NAME, __version__          # noqa: E402
from ndfbin_decks.app.session import Session            # noqa: E402
from ndfbin_decks.io import divisions, modlocator       # noqa: E402

#: level names, in the editor's words (the badge on each row)
LEVELS = {
    "country": "国家 Nat",
    "division": "师 Div",
    "battalion": "营 Bn",
    "company": "连 Co",
    "platoon": "排 Pl",
    "entry": "条目",
}


class _Interner:
    """One name → one index.  Equipment repeats constantly; the file should not."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self._index: dict[str, int] = {}

    def __call__(self, name: str | None) -> int:
        if not name:
            return -1
        got = self._index.get(name)
        if got is None:
            got = len(self.names)
            self._index[name] = got
            self.names.append(name)
        return got


def _battalion_name(export_name: str) -> str:
    prefix = "Descriptor_Deck_"
    return export_name[len(prefix):] if export_name.startswith(prefix) else export_name


def build_tree(mod, *, lang: str = "SC") -> dict:
    """The whole tree as compact JSON-ready arrays.

    Layout, one tuple per level (indices are what the page uses):

    * country   ``[code, name, [division...]]``
    * division  ``[label, [battalion...]]``
    * battalion ``[name, export_name, pool_slots, window_sum, [company...]]``
    * company   ``[index, [platoon...]]``
    * platoon   ``[index, is_hq, [entry...], dictionary_name]``
    * entry     ``[unit, count, transporter, experience]`` (-1 = absent)

    ``pool_slots`` vs ``window_sum`` is deliberately carried for every battalion:
    they are equal on healthy data, and where they are not, the page says so —
    that inequality is exactly what makes a deck unsavable.
    """
    started = time.perf_counter()
    session = Session.load(mod.deck_bin, lang=lang, mod=mod)
    intern = _Interner()

    groups: dict[str, list] = {}
    for division in session.divisions():
        groups.setdefault(divisions.country_code(division.path) or "", []).append(division)

    counts = {"countries": 0, "divisions": 0, "battalions": 0,
              "companies": 0, "platoons": 0, "entries": 0}
    countries = []

    # Biggest contingent first, same order the country picker uses; the
    # unlabelled bucket (if any) goes last because it is not a country.
    order = sorted(groups, key=lambda c: (not c, -len(groups[c]), c))
    for code in order:
        divs = []
        for division in sorted(groups[code], key=lambda d: d.label):
            battalions = []
            for bat in sorted(division.battalions, key=lambda b: b.export_name):
                companies = []
                for ci, company in enumerate(bat.companies):
                    platoons = []
                    for si, platoon in enumerate(company.platoons):
                        name = session.platoon_name(platoon.name_hash)
                        # ``⟨未知 hash⟩`` is the resolver saying it does not know;
                        # blank is better than a hex string in a page meant to be
                        # read.  The composition is shown instead, in JS.
                        if name.startswith("⟨"):
                            name = ""
                        rows = []
                        for entry in platoon.entries:
                            rows.append([
                                intern(session.display(entry.unit)),
                                int(entry.count or 0),
                                intern(session.display(entry.transporter))
                                if entry.transporter else -1,
                                -1 if entry.experience is None else int(entry.experience),
                            ])
                        if rows:
                            counts["entries"] += len(rows)
                            counts["platoons"] += 1
                        platoons.append([si, 1 if platoon.is_hq else 0, rows, name])
                    if platoons:
                        counts["companies"] += 1
                    companies.append([ci, platoons])
                if companies:
                    counts["battalions"] += 1
                battalions.append([
                    _battalion_name(bat.export_name),
                    bat.export_name,
                    int(bat.pool_slots),
                    int(bat.window_sum),
                    companies,
                ])
            if battalions:
                counts["divisions"] += 1
            divs.append([division.label, battalions])
        counts["countries"] += 1
        # "SOV  苏联", but "AGF 自动生成" — ``country_name`` already spells some
        # codes out, and prefixing those again reads as a stutter.
        name = divisions.country_name(code) if code else "（未标注国家）"
        if code and not name.startswith(code):
            name = f"{code}  {name}"
        countries.append([code, name, divs])

    deck_path = Path(mod.deck_bin)
    return {
        "meta": {
            "mod": mod.name,
            "deck": deck_path.name,
            "deck_bytes": deck_path.stat().st_size if deck_path.is_file() else 0,
            "generated": time.strftime("%Y-%m-%d %H:%M"),
            "app": f"{APP_NAME} v{__version__}",
            "lang": lang,
            "counts": counts,
            "unique_equipment": len(intern.names),
            "levels": LEVELS,
            "elapsed": round(time.perf_counter() - started, 2),
        },
        "u": intern.names,
        "c": countries,
    }


def render_html(payload: dict) -> str:
    """The page: one file, no network, everything inline."""
    meta = payload["meta"]
    counts = meta["counts"]
    summary = " · ".join([
        f"国家 {counts['countries']}",
        f"师 {counts['divisions']}",
        f"营 {counts['battalions']:,}",
        f"连 {counts['companies']:,}",
        f"排 {counts['platoons']:,}",
        f"条目 {counts['entries']:,}",
        f"装备种数 {meta['unique_equipment']:,}",
    ])
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # ``</script>`` inside the data would end the tag early.  The payload has no
    # such text today, but escaping it costs one replace and removes the class
    # of bug entirely.
    data = data.replace("</", "<\\/")

    return (_TEMPLATE
            .replace("__TITLE__", _escape(f"{meta['mod']} · 编制结构"))
            .replace("__MOD__", _escape(meta["mod"]))
            .replace("__SUMMARY__", _escape(summary))
            .replace("__SOURCE__", _escape(
                f"{meta['deck']}（{meta['deck_bytes']:,} B） · "
                f"生成于 {meta['generated']} · {meta['app']}"))
            .replace("__DATA__", data))


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# The page.  Kept as one string: it is a document, not application code, and
# splitting it across .css/.js files would break the "single file, works
# offline, mail it to someone" property this exists for.
# ---------------------------------------------------------------------------

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --bg:#f5f6f8; --panel:#ffffff; --ink:#1b2026; --muted:#6b7684;
  --line:#e2e6eb; --line2:#eef1f4; --accent:#2f6fdb; --accent-soft:#e8f0fd;
  --warn:#b4530a; --warn-soft:#fdf0e4; --tag:#eef1f5;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:13px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  display:flex; flex-direction:column;
}
header{padding:14px 18px 10px; background:var(--panel); border-bottom:1px solid var(--line)}
h1{margin:0; font-size:16px; font-weight:650; letter-spacing:.2px}
h1 .badge{
  font-size:11px; font-weight:500; color:var(--muted); background:var(--tag);
  border-radius:20px; padding:2px 8px; margin-left:8px; vertical-align:2px;
}
.sub{margin-top:4px; color:var(--muted); font-size:12px}
.sub b{color:var(--ink); font-weight:600}
.toolbar{
  display:flex; gap:8px; align-items:center; padding:9px 18px;
  background:var(--panel); border-bottom:1px solid var(--line); flex-wrap:wrap;
}
input[type=search]{
  flex:1 1 260px; min-width:200px; padding:6px 10px; font-size:13px;
  border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink);
}
input[type=search]:focus{outline:2px solid var(--accent-soft); border-color:var(--accent)}
button{
  font:inherit; font-size:12px; padding:5px 10px; border-radius:6px; cursor:pointer;
  border:1px solid var(--line); background:var(--panel); color:var(--ink);
}
button:hover{border-color:#c9d1da}
button.on{background:var(--accent-soft); border-color:#b9cdf3; color:#1b4ea8}
button:disabled{color:#b3bcc6; cursor:not-allowed; background:var(--panel)}
.seg{display:flex; gap:0}
.seg button:first-child{border-radius:6px 0 0 6px}
.seg button:last-child{border-radius:0 6px 6px 0; border-left:none}
.hint{color:var(--muted); font-size:12px}
main{flex:1; min-height:0; display:flex}
#treePane{flex:1 1 58%; min-width:0; overflow:auto; padding:10px 8px 40px 14px; border-right:1px solid var(--line)}
#side{flex:1 1 42%; min-width:320px; overflow:auto; padding:14px 16px 40px; background:var(--panel)}
#graphPane{display:none; flex:1; overflow:auto; background:var(--panel); padding:10px}
body.graph #treePane,body.graph #side{display:none}
body.graph #graphPane{display:block}

.row{
  display:flex; align-items:baseline; gap:6px; padding:2px 6px 2px 0;
  border-radius:5px; cursor:default; white-space:nowrap;
}
.row:hover{background:#f0f3f7}
.row.sel{background:var(--accent-soft)}
.row.match{background:#fff6d9}
.row.match.sel{background:var(--accent-soft)}
.kids{margin-left:14px; border-left:1px solid var(--line2); padding-left:6px}
.tw{
  width:14px; flex:0 0 14px; text-align:center; color:#9aa5b1;
  cursor:pointer; user-select:none; font-size:10px;
}
.tw.leaf{visibility:hidden}
.lbl{font-size:13px; cursor:pointer}
.entry .lbl{font-family:var(--mono); font-size:12px}
.meta{color:var(--muted); font-size:11.5px; margin-left:12px}
.meta.warn{color:var(--warn)}
.tag{
  font-size:10.5px; color:var(--muted); background:var(--tag);
  border-radius:4px; padding:0 5px; margin-left:2px;
}
.tag.hq{background:#e8f5ec; color:#256b3a}
.k-country .lbl{font-weight:650}
.k-division .lbl{font-weight:600}
.k-battalion .lbl{font-weight:600; color:#243447}
.empty{color:var(--muted); padding:16px 6px}

#side h2{margin:0 0 2px; font-size:14px}
#side .crumb{color:var(--muted); font-size:11.5px; margin-bottom:10px}
#side .crumb span{color:#98a3af}
.cards{display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 14px}
.card{
  background:var(--bg); border:1px solid var(--line); border-radius:8px;
  padding:7px 11px; min-width:92px;
}
.card .k{color:var(--muted); font-size:11px}
.card .v{font-size:16px; font-weight:650; font-variant-numeric:tabular-nums}
.tabs{display:flex; gap:6px; margin:14px 0 8px}
table{width:100%; border-collapse:collapse; font-size:12px}
th,td{padding:4px 6px; border-bottom:1px solid var(--line2); text-align:left}
th{color:var(--muted); font-weight:600; font-size:11.5px; position:sticky; top:0; background:var(--panel)}
td.n,th.n{text-align:right; font-variant-numeric:tabular-nums}
td.mono{font-family:var(--mono); font-size:11.5px}
.tblwrap{max-height:calc(100vh - 340px); overflow:auto}
.legend{color:var(--muted); font-size:11.5px; margin-top:8px; line-height:1.7}
svg text{font:12px var(--mono); fill:var(--ink)}
svg .lbl0{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; font-weight:650; font-size:13px}
svg .lbl1{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; font-size:12px}
svg .meta{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; font-size:11px; fill:#6b7684}
svg path{fill:none; stroke:#c9d3de; stroke-width:1}
footer{padding:6px 18px; color:var(--muted); font-size:11px; background:var(--panel); border-top:1px solid var(--line)}
</style>
</head>
<body>
<header>
  <h1>__MOD__<span class="badge">编制结构</span></h1>
  <div class="sub"><b>__SUMMARY__</b></div>
  <div class="sub">__SOURCE__ · 只读导出</div>
</header>

<div class="toolbar">
  <input id="q" type="search" placeholder="筛选：国家 / 师 / 营 / 连 / 排 / 装备名（留空看全部）" autocomplete="off">
  <button id="clear">清除</button>
  <button id="expand">展开两级</button>
  <button id="collapse">全部折叠</button>
  <div class="seg">
    <button id="viewTree" class="on">结构树</button>
    <button id="viewGraph" disabled>连线图</button>
  </div>
  <span class="hint" id="hint"></span>
</div>

<main>
  <section id="treePane"></section>
  <aside id="side"></aside>
  <section id="graphPane"></section>
</main>

<footer>
  数据来源：<code>Deck.ndfbin</code>，经编辑器同一套读取路径解析；只读，不修改 mod 的任何文件。
</footer>

<script>
const D = __DATA__;
const U = D.u, M = D.meta, C = M.counts;
const LEVEL = M.levels;

/* ---------- data accessors ------------------------------------------- */
/* Each level is a positional array (see build_tree's docstring).  Keeping the
   accessors in one place means the shape is written down once. */

const KID = {
  country:  d => ['division',  d[2]],
  division: d => ['battalion', d[1]],
  battalion:d => ['company',   d[4]],
  company:  d => ['platoon',   d[1]],
  platoon:  d => ['entry',     d[2]],
  entry:    d => null,
};

function labelOf(kind, d){
  switch(kind){
    case 'country':   return d[1] || d[0] || '（未标注国家）';
    case 'division':  return d[0];
    case 'battalion': return d[0];
    case 'company':   return '连Co ' + d[0];
    case 'platoon':   return '排Pl ' + d[0];
    case 'entry':     return U[d[0]];
  }
  return '?';
}

/* Equipment composition of a platoon, top 3 by count — the same fallback the
   editor shows when no PLATOONS dictionary entry exists. */
function composition(entries){
  const tally = new Map();
  for(const e of entries){
    const name = U[e[0]];
    tally.set(name, (tally.get(name) || 0) + (e[1] || 0));
  }
  const parts = [...tally.entries()].sort((a,b) => b[1] - a[1]);
  const shown = parts.slice(0, 3).map(([n,c]) => n + ' ×' + c).join(' · ');
  return shown + (parts.length > 3 ? ' …' : '');
}

const statsCache = new Map();
function stats(kind, d){
  const hit = statsCache.get(d);
  if(hit) return hit;
  let r = {entries: 0, units: 0, platoons: 0, companies: 0, battalions: 0, divisions: 0};
  if(kind === 'entry'){
    r.entries = 1; r.units = d[1] || 0;
  } else {
    const kids = KID[kind](d);
    if(kids){
      for(const child of kids[1]){
        const s = stats(kids[0], child);
        r.entries += s.entries; r.units += s.units;
        r.platoons += s.platoons; r.companies += s.companies;
        r.battalions += s.battalions; r.divisions += s.divisions;
      }
    }
    if(kind === 'platoon') r.platoons = 1;
    if(kind === 'company') r.companies = 1;
    if(kind === 'battalion') r.battalions = 1;
    if(kind === 'division') r.divisions = 1;
  }
  statsCache.set(d, r);
  return r;
}

function metaOf(kind, d){
  const s = stats(kind, d);
  switch(kind){
    case 'country':
      return s.divisions + ' 师 · ' + fmt(s.battalions) + ' 营 · ' + fmt(s.units) + ' 件';
    case 'division':
      return fmt(s.battalions) + ' 营 · ' + fmt(s.platoons) + ' 排 · ' + fmt(s.units) + ' 件';
    case 'battalion': {
      const pool = d[2], sum = d[3];
      let text = s.companies + ' 连 · ' + s.platoons + ' 排 · ' + fmt(s.units) + ' 件';
      text += ' · 池 ' + fmt(pool);
      return {text, warn: sum !== pool ? ('Σ' + fmt(sum) + ' ≠ 池') : ''};
    }
    case 'company':
      return s.platoons + ' 排 · ' + fmt(s.units) + ' 件';
    case 'platoon':
      return (d[3] ? d[3] + ' · ' : '') + fmt(s.units) + ' 件';
    case 'entry': {
      let text = '×' + d[1];
      if(d[2] >= 0) text += '  [' + U[d[2]] + ']';
      if(d[3] >= 0) text += '  ·  经验 ' + d[3];
      return text;
    }
  }
  return '';
}

function fmt(n){ return (n || 0).toLocaleString('en-US'); }

/* ---------- tree rendering (lazy) ------------------------------------ */

const treePane = document.getElementById('treePane');
const side = document.getElementById('side');
let selected = null;          // {kind, data}

function rowEl(kind, d, depth){
  const el = document.createElement('div');
  el.className = 'row k-' + kind + ' ' + kind;
  const kids = KID[kind](d);
  const leaf = !kids || !kids[1].length;

  const tw = document.createElement('span');
  tw.className = 'tw' + (leaf ? ' leaf' : '');
  tw.textContent = '▶';
  el.appendChild(tw);

  const lbl = document.createElement('span');
  lbl.className = 'lbl';
  lbl.textContent = labelOf(kind, d);
  if(kind === 'battalion'){
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = LEVEL.battalion;
    lbl.appendChild(document.createTextNode(' '));
    lbl.appendChild(tag);
  }
  if(kind === 'platoon' && d[1]){
    const tag = document.createElement('span');
    tag.className = 'tag hq';
    tag.textContent = 'HQ';
    lbl.appendChild(document.createTextNode(' '));
    lbl.appendChild(tag);
  }
  el.appendChild(lbl);

  const meta = metaOf(kind, d);
  const m = document.createElement('span');
  if(typeof meta === 'string'){
    m.className = 'meta';
    m.textContent = meta;
  } else {
    m.className = 'meta' + (meta.warn ? ' warn' : '');
    m.textContent = meta.warn ? meta.text + ' · ' + meta.warn : meta.text;
  }
  el.appendChild(m);

  if(kind === 'company' || kind === 'platoon'){
    el.title = composition(kind === 'company'
      ? d[1].flatMap(p => p[2]) : d[2]);
  }

  let box = null;
  const toggle = () => {
    if(leaf) return;
    if(!box){
      box = document.createElement('div');
      box.className = 'kids';
      box.hidden = true;
      const [ck, arr] = KID[kind](d);
      for(const child of arr) box.appendChild(rowEl(ck, child, depth + 1));
      el.after(box);
    }
    box.hidden = !box.hidden;
    tw.textContent = box.hidden ? '▶' : '▼';
    el.classList.toggle('open', !box.hidden);
  };
  tw.onclick = toggle;
  lbl.onclick = () => {
    select(kind, d, el);
    // Selecting a collapsed branch opens it once — otherwise clicking a 师
    // shows its detail on the right while the tree looks unchanged.
    if(!leaf && !el.classList.contains('open')) toggle();
  };
  if(selected && selected.data === d) el.classList.add('sel');
  return el;
}

function renderAll(){
  treePane.textContent = '';
  for(const country of D.c) treePane.appendChild(rowEl('country', country, 0));
}

/* ---------- filtering ------------------------------------------------ */

const q = document.getElementById('q');
const hint = document.getElementById('hint');

function haystack(kind, d){
  const parts = [labelOf(kind, d), LEVEL[kind]];
  const meta = metaOf(kind, d);
  parts.push(typeof meta === 'string' ? meta : meta.text);
  if(kind === 'battalion') parts.push(d[1]);
  return parts.join(' ').toLowerCase();
}

function buildFiltered(kind, d){
  const kids = KID[kind](d);
  const kept = [];
  if(kids) for(const child of kids[1]){
    const sub = buildFiltered(kids[0], child);
    if(sub) kept.push(sub);
  }
  const self = matchSet.has(d);
  if(!keepSet.has(d)) return null;
  return {kind, d, kept, self};
}

/* Two sets on purpose: ``keepSet`` is "must stay visible" (matches *and* the
   ancestors that lead to them), ``matchSet`` is "this one actually matched".
   Sharing one set tinted every ancestor as a hit. */
let keepSet = new Set();
let matchSet = new Set();

/* Typing one letter matches most of 237k nodes.  The walk is cheap; building
   that many rows is not, so beyond this many hits the page says how many there
   are and asks for something more specific. */
const FILTER_LIMIT = 1200;

function applyFilter(){
  const needle = q.value.trim().toLowerCase();
  if(!needle){
    keepSet = new Set();
    matchSet = new Set();
    hint.textContent = '';
    renderAll();
    return;
  }
  keepSet = new Set();
  matchSet = new Set();
  let hits = 0;
  for(const country of D.c){
    // The return value is what marks the ancestors: without it every match
    // would be kept on its own and the tree would render empty, because a
    // child cannot be shown unless its parent is in the set.
    (function walk(kind, d){
      let self = haystack(kind, d).includes(needle);
      let kept = false;
      if(self){
        hits++;
        if(matchSet.size < FILTER_LIMIT){ matchSet.add(d); kept = true; }
      }
      let childHit = false;
      const kids = KID[kind](d);
      if(kids) for(const child of kids[1]){
        if(walk(kids[0], child)) childHit = true;
      }
      if(kept || childHit) keepSet.add(d);
      return kept || childHit;
    })('country', country);
  }

  treePane.textContent = '';
  for(const country of D.c){
    if(!keepSet.has(country)) continue;
    const node = buildFiltered('country', country);
    if(!node) continue;
    treePane.appendChild(buildRow(node, 0));
  }
  hint.textContent = !hits ? '没有匹配的节点'
    : hits > FILTER_LIMIT
      ? '命中 ' + hits.toLocaleString('en-US') + ' 个，只展开前 ' + FILTER_LIMIT + ' 个 — 再输几个字收窄'
      : '命中 ' + hits.toLocaleString('en-US') + ' 个节点';
  if(!hits){
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '没有匹配「' + q.value.trim() + '」的节点。清空输入框可看全部。';
    treePane.appendChild(empty);
  }
}

function buildRow(node, depth){
  // A fragment, because the row and its children are two siblings: returning
  // just the row and calling ``el.after(box)`` would do nothing, since the row
  // has no parent yet.
  const frag = document.createDocumentFragment();
  const el = rowEl(node.kind, node.d, depth);
  frag.appendChild(el);
  if(node.kept && node.kept.length){
    const tw = el.querySelector('.tw');
    const box = document.createElement('div');
    box.className = 'kids';
    for(const child of node.kept) box.appendChild(buildRow(child, depth + 1));
    frag.appendChild(box);
    tw.textContent = '▼';
    el.classList.add('open');
  }
  if(node.self) el.classList.add('match');
  if(selected && selected.data === node.d) el.classList.add('sel');
  return frag;
}

/* ---------- selection & side panel ----------------------------------- */

function select(kind, d, el){
  selected = {kind, data: d};
  for(const old of treePane.querySelectorAll('.row.sel')) old.classList.remove('sel');
  if(el) el.classList.add('sel');
  document.getElementById('viewGraph').disabled = kind !== 'battalion';
  renderSide();
  if(document.body.classList.contains('graph')){
    if(kind === 'battalion') renderGraph();
    else setView('tree');
  }
}

function renderSide(){
  if(!selected){
    side.innerHTML = '<h2>还没有选节点</h2>'
      + '<div class="crumb">在左侧点一个<b>国家 / 师 / 营 / 连 / 排</b>的名字，'
      + '这里会给出它的构成与按装备聚合的表。</div>';
    return;
  }
  const {kind, data} = selected;
  const s = stats(kind, data);
  const crumbs = [];
  let el = side;
  const cards = [];
  if(kind !== 'entry'){
    cards.push(['下辖条目', fmt(s.entries)]);
    cards.push(['单位件数', fmt(s.units)]);
    if(s.platoons) cards.push(['排', fmt(s.platoons)]);
    if(s.companies) cards.push(['连', fmt(s.companies)]);
    if(s.battalions) cards.push(['营', fmt(s.battalions)]);
    if(s.divisions) cards.push(['师', fmt(s.divisions)]);
  }
  if(kind === 'battalion'){
    cards.push(['槽池', fmt(data[2])]);
    if(data[3] !== data[2]) cards.push(['Σ(Number)', fmt(data[3])]);
  }

  const rows = aggregate(kind, data);
  const head = '<h2>' + esc(labelOf(kind, data)) + '</h2>'
    + '<div class="crumb">' + LEVEL[kind]
    + (kind === 'entry' ? '' : ' · ' + s.entries.toLocaleString('en-US') + ' 条装备') + '</div>';

  let html = head + '<div class="cards">';
  for(const [k, v] of cards){
    html += '<div class="card"><div class="k">' + esc(k) + '</div><div class="v">' + v + '</div></div>';
  }
  html += '</div>';

  if(kind === 'battalion' && data[3] !== data[2]){
    html += '<div class="legend" style="color:#b4530a">'
      + '这个营的 Σ(Number) 与槽池长度不一致 —— 槽位有空档或重叠，保存会被校验器拒绝。</div>';
  }

  html += '<table><thead><tr><th>装备</th><th>载具</th><th class="n">经验</th>'
    + '<th class="n">件数</th><th class="n">条目</th><th class="n">排</th></tr></thead><tbody>';
  for(const r of rows.slice(0, 400)){
    html += '<tr><td class="mono">' + esc(r.unit) + '</td>'
      + '<td class="mono">' + (r.transport ? esc(r.transport) : '—') + '</td>'
      + '<td class="n">' + (r.xp >= 0 ? r.xp : '—') + '</td>'
      + '<td class="n">' + fmt(r.units) + '</td>'
      + '<td class="n">' + fmt(r.entries) + '</td>'
      + '<td class="n">' + fmt(r.platoons) + '</td></tr>';
  }
  html += '</tbody></table>';
  if(!rows.length) html += '<div class="empty">这个节点下没有装备条目。</div>';
  else if(rows.length > 400) html += '<div class="legend">只列出前 400 种（共 ' + rows.length + ' 种）。</div>';
  else html += '<div class="legend">按件数从多到少。同一装备在不同排里重复出现时，"条目"与"排"会大于 1。</div>';

  side.innerHTML = html;
}

/* Group every entry under a node by equipment identity (unit, transporter,
   experience), which is what a modder means by "the same equipment". */
function aggregate(kind, data){
  const map = new Map();
  const add = (e, platoonKey) => {
    const key = e[0] + '|' + e[2] + '|' + e[3];
    let r = map.get(key);
    if(!r){
      r = {unit: U[e[0]], transport: e[2] >= 0 ? U[e[2]] : '', xp: e[3],
           units: 0, entries: 0, platoons: new Set()};
      map.set(key, r);
    }
    r.units += e[1] || 0;
    r.entries += 1;
    // An entry has no platoon of its own to speak of; counting it as one
    // would read as "this equipment sits in 1 platoon" beside a 排 column
    // that cannot be true from a leaf.
    if(platoonKey) r.platoons.add(platoonKey);
  };
  (function walk(k, d, pk){
    if(k === 'entry'){ add(d, pk); return; }
    const kids = KID[k](d);
    if(!kids) return;
    for(const child of kids[1]){
      const key = k === 'platoon' ? child : pk;
      walk(kids[0], child, key);
    }
  })(kind, data, null);
  const out = [...map.values()];
  for(const r of out) r.platoons = r.platoons.size;
  out.sort((a, b) => b.units - a.units || b.entries - a.entries);
  return out;
}

function esc(t){
  return String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

/* ---------- node-link graph (one battalion) -------------------------- */

const graphPane = document.getElementById('graphPane');
const COL = [10, 200, 330, 470];
const ROW = 19;

function renderGraph(){
  if(!selected || selected.kind !== 'battalion') return;
  const root = {kind: 'battalion', d: selected.data};
  let y = 0;
  (function layout(node, depth){
    const kids = KID[node.kind](node.d);
    node.depth = depth;
    if(!kids || !kids[1].length){
      node.y = y++;
      return node;
    }
    node.kids = kids[1].map(child => layout({kind: kids[0], d: child}, depth + 1));
    node.y = (node.kids[0].y + node.kids[node.kids.length - 1].y) / 2;
    return node;
  })(root, 0);

  const width = 760;
  const height = Math.max(y * ROW + 30, 200);
  const parts = ['<svg width="' + width + '" height="' + height + '" xmlns="http://www.w3.org/2000/svg">'];

  (function draw(node){
    const x = COL[node.depth] || COL[COL.length - 1];
    const px = x, py = node.y * ROW + 14;
    if(node.kids){
      for(const kid of node.kids){
        const kx = COL[kid.depth], ky = kid.y * ROW + 14;
        const mid = kx - 12;
        parts.push('<path d="M' + (px + 8) + ' ' + py + ' H' + mid + ' V' + ky + ' H' + kx + '"/>');
        draw(kid);
      }
    }
    let text, cls;
    if(node.kind === 'entry'){
      text = U[node.d[0]] + (node.d[1] > 1 ? ' ×' + node.d[1] : '');
      if(node.d[2] >= 0) text += ' [' + U[node.d[2]] + ']';
      cls = 'lbl3';
    } else if(node.kind === 'platoon'){
      text = '排 ' + node.d[0] + (node.d[3] ? ' ' + node.d[3] : '');
      cls = 'lbl2';
    } else if(node.kind === 'company'){
      text = '连 ' + node.d[0];
      cls = 'lbl1';
    } else {
      text = node.d[0];
      cls = 'lbl0';
    }
    // Entries can be long; the SVG is a diagram, the tables carry the detail.
    if(text.length > 34) text = text.slice(0, 33) + '…';
    parts.push('<text class="' + cls + '" x="' + (x + 4) + '" y="' + (py + 4) + '">'
      + esc(text) + '</text>');
  })(root);

  parts.push('</svg>');
  const info = '<div class="legend">' + esc(selected.data[0]) + ' · '
    + stats('battalion', selected.data).companies + ' 连 · '
    + stats('battalion', selected.data).platoons + ' 排 · '
    + fmt(stats('battalion', selected.data).units) + ' 件'
    + '　（连线图只画选中的那一个营；换一个营会重画）</div>';
  graphPane.innerHTML = info + parts.join('');
}

/* ---------- view switching ------------------------------------------- */

function setView(which){
  document.body.classList.toggle('graph', which === 'graph');
  document.getElementById('viewTree').classList.toggle('on', which === 'tree');
  document.getElementById('viewGraph').classList.toggle('on', which === 'graph');
  if(which === 'graph') renderGraph();
}

/* ---------- wiring ---------------------------------------------------- */

let timer = null;
q.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(applyFilter, 140);
});
document.getElementById('clear').onclick = () => {
  q.value = '';
  applyFilter();
  q.focus();
};
document.getElementById('expand').onclick = () => {
  const tops = [...treePane.children].filter(el => el.classList.contains('row'));
  for(const row of tops){
    const lbl = row.querySelector('.lbl');
    if(lbl && !row.classList.contains('open')) lbl.click();
    const kids = row.nextElementSibling;
    if(kids && kids.classList.contains('kids')){
      for(const kid of kids.children){
        const kl = kid.querySelector('.lbl');
        if(kl && !kid.classList.contains('open')) kl.click();
      }
    }
  }
};
document.getElementById('collapse').onclick = () => {
  renderAll();
  hint.textContent = '';
};
document.getElementById('viewTree').onclick = () => setView('tree');
document.getElementById('viewGraph').onclick = () => setView('graph');

renderAll();
renderSide();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把一个 mod 的将军模式编制树导成单文件 HTML。")
    parser.add_argument("--mod", help="mod 名称 / 工坊 id；省略时列出可选的 mod")
    parser.add_argument("--out", help="输出路径（默认 编制结构-<mod>.html）")
    parser.add_argument("--lang", default="SC", help="platoon/company 词典语言，默认 SC")
    args = parser.parse_args(argv)

    if not args.mod:
        mods = modlocator.discover()
        print(f"{len(mods)} 个 mod：")
        for mod in mods:
            print(f"  {mod.name:40s} {mod.label}")
        print("\n用法：python visualization/deck_tree.py --mod <名称|工坊id>")
        return 0

    mod = modlocator.resolve(args.mod)
    print(f"读取 {mod.name} …")
    payload = build_tree(mod, lang=args.lang)
    html = render_html(payload)
    out = Path(args.out) if args.out else Path(f"编制结构-{mod.name}.html")
    out.write_text(html, encoding="utf-8")

    c = payload["meta"]["counts"]
    print(f"  国家 {c['countries']} · 师 {c['divisions']} · 营 {c['battalions']:,} · "
          f"连 {c['companies']:,} · 排 {c['platoons']:,} · 条目 {c['entries']:,}")
    print(f"  {out}  {out.stat().st_size / 1048576:.2f} MB  "
          f"（构建 {payload['meta']['elapsed']:.1f} s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
