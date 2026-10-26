"""Single-file GeoQuest HTML export — no CDN, no external assets, no network."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .game import (
    BEARING_MARGIN_DEG, DIFFICULTY, MIN_DISTANCE_SHARE, QuestionFactory,
)

# Modes supported in offline HTML (locate and blind_zoom need the QGIS canvas)
HTML_MODES = ("bigger", "distance", "silhouette", "attr_guess", "ordering", "nearest", "direction")

# Only these record fields are needed by the offline engine; layer ids, bboxes
# and display bookkeeping stay out of the shared file.
_EXPORT_FIELDS = ("value", "area", "centroid", "outline")


def available_html_modes(records: list[dict], modes: list[str]) -> list[str]:
    """Return selected offline-capable modes that have fair source data."""
    selected = list(dict.fromkeys(mode for mode in modes if mode in HTML_MODES))
    return QuestionFactory(records, seed=1).available_modes(selected)


def _safe_json(value) -> str:
    """JSON that cannot close the surrounding <script> element."""
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/").replace("<!--", "<\\!--"))


def build_payload(title: str, records: list[dict], modes: list[str], rounds: int,
                  difficulty: str = "Medium", lives: int = 3,
                  value_label: str = "value") -> dict:
    """Return the data the offline engine plays, validated by the Python engine."""
    factory = QuestionFactory(records, seed=1, value_label=value_label)
    selected_modes = list(dict.fromkeys(mode for mode in modes if mode in HTML_MODES))
    active_modes = factory.available_modes(selected_modes)
    if not active_modes:
        raise ValueError(
            "Offline HTML needs at least one selected, data-ready mode: Value Duel, "
            "Distance Guess, Know the Shape, Attribute Guess, Ranking, Nearest Neighbour "
            "or Compass Quest.")
    difficulty = difficulty if difficulty in DIFFICULTY else "Medium"
    export_records = []
    for record in factory.records:
        item = {"label": str(record["display_label"])}
        for key in _EXPORT_FIELDS:
            if record.get(key) is not None:
                item[key] = record[key]
        export_records.append(item)
    scale = factory.distance_scale()
    return {
        "title": str(title or "GeoQuest"),
        "records": export_records,
        "modes": active_modes,
        "rounds": max(1, int(rounds)),
        "lives": max(1, int(lives)),
        "difficulty": difficulty,
        "settings": dict(DIFFICULTY[difficulty]),
        "metric": factory.metric,
        "value_label": factory.value_label,
        "distance": {"unit": scale["unit"], "factor": scale["factor"],
                     "max": scale["input_max"], "widest_m": scale["widest_m"],
                     "min_share": MIN_DISTANCE_SHARE},
        "bearing_margin": BEARING_MARGIN_DEG,
    }


_CSS = """
:root{
  --ink:#17212b;--muted:#5b6b7c;--paper:#f2f6fa;--card:#fff;--line:#dce4ed;
  --violet:#6c4cff;--cyan:#00b8d9;--good:#13a86b;--bad:#e94f64;
  --gold:#f59e0b;--shadow:0 20px 60px #25356a1a;color-scheme:light;
}
[data-theme=dark]{
  --ink:#e2e8f0;--muted:#94a3b8;--paper:#0f172a;--card:#1e293b;--line:#334155;
  --violet:#8b74ff;--shadow:0 20px 60px #00000040;color-scheme:dark;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);min-height:100vh}
.shell{max-width:900px;margin:auto;padding:20px 16px}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 0 20px;flex-wrap:wrap}
.brand{font-weight:900;font-size:26px;letter-spacing:-0.5px}
.brand b{color:var(--violet)}
.brand small{display:block;font-size:13px;font-weight:600;color:var(--muted);letter-spacing:0}
.stats{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:8px 14px;font-weight:700;box-shadow:var(--shadow);font-size:14px;font-variant-numeric:tabular-nums}
.icon-btn{border:1px solid var(--line);background:var(--card);border-radius:9px;padding:8px 12px;cursor:pointer;font-size:16px;color:var(--ink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow);padding:clamp(20px,4vw,40px);margin-bottom:20px}
.badge{color:var(--violet);text-transform:uppercase;letter-spacing:.14em;font-weight:900;font-size:11px;margin-bottom:10px}
h1{font-size:clamp(21px,3.6vw,32px);font-weight:800;margin-bottom:20px;line-height:1.25}
.choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:8px}
@media(max-width:560px){.choices{grid-template-columns:1fr}}
button{font:inherit}
.choice{border:1.5px solid var(--line);background:var(--card);border-radius:16px;padding:14px;cursor:pointer;color:var(--ink);font-weight:700;font-size:15px;transition:transform .15s,border-color .15s,box-shadow .15s;text-align:left;line-height:1.3;display:flex;gap:10px;align-items:flex-start}
.choice kbd{font:700 12px/1 ui-monospace,monospace;border:1px solid var(--line);border-radius:6px;padding:4px 6px;color:var(--muted);flex:none}
.choice:hover:not(:disabled),.choice:focus-visible{border-color:var(--violet);transform:translateY(-2px);box-shadow:0 8px 24px #6c4cff18;outline:none}
.choice:disabled{cursor:default;transform:none}
.choice.good{border-color:var(--good);background:#e9fdf4;color:#166534}
.choice.bad{border-color:var(--bad);background:#fff0f3;color:#9b1c3a}
[data-theme=dark] .choice.good{background:#052e16;color:#4ade80}
[data-theme=dark] .choice.bad{background:#2d0a14;color:#f87171}
.choice.dim{opacity:.5}
.primary{background:linear-gradient(135deg,var(--violet) 0%,#a78bfa 100%);color:#fff;border:0;border-radius:14px;padding:15px 24px;font-weight:800;font-size:16px;cursor:pointer;display:block;width:100%;margin-top:16px;text-align:center}
.primary:hover:not(:disabled){box-shadow:0 12px 32px #6c4cff40}
.primary:focus-visible{outline:3px solid var(--cyan);outline-offset:2px}
.primary:disabled{opacity:.5;cursor:default}
.outline{width:min(360px,80vw);height:240px;display:block;margin:0 auto 20px;filter:drop-shadow(0 12px 20px #4352a730)}
.outline path{fill:var(--violet);stroke:#3d2baa;stroke-width:1.5;stroke-linejoin:round}
#timer-bar{width:100%;height:6px;background:var(--line);border-radius:3px;margin-bottom:18px;overflow:hidden}
#timer-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--violet),var(--cyan));width:100%}
.slider-wrap{padding:8px 0 4px}
input[type=range]{width:100%;accent-color:var(--violet);cursor:pointer}
.slider-val{text-align:center;font-size:30px;font-weight:900;color:var(--violet);margin-bottom:12px;font-variant-numeric:tabular-nums}
.slider-hint{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}
.rank-list{display:grid;gap:8px;margin:8px 0 8px}
.rank-row{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:var(--paper)}
.rank-pos{font-weight:900;color:var(--violet);min-width:1.5em}
.rank-label{flex:1;font-weight:700}
.rank-move{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:6px 10px;min-width:40px;cursor:pointer}
.rank-move:disabled{opacity:.35;cursor:default}
#feedback{min-height:52px;font-size:17px;font-weight:700;margin:14px 0 0;padding:12px 16px;border-radius:12px}
#feedback:empty{display:none}
#feedback.good{background:#e9fdf4;color:#166534;border:1px solid #bbf7d0}
#feedback.bad{background:#fff0f3;color:#9b1c3a;border:1px solid #fecdd3}
[data-theme=dark] #feedback.good{background:#052e16;color:#4ade80;border-color:#166534}
[data-theme=dark] #feedback.bad{background:#2d0a14;color:#f87171;border-color:#9b1c3a}
#feedback small{display:block;font-weight:600;opacity:.85;margin-top:4px}
.pop{animation:pop .45s cubic-bezier(.36,.07,.19,.97) both}
@keyframes pop{0%{transform:scale(1)}30%{transform:scale(1.2)}100%{transform:scale(1)}}
.progress-dots{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--line)}
.dot.correct{background:var(--good)}
.dot.wrong{background:var(--bad)}
.dot.now{outline:2px solid var(--violet);outline-offset:2px}
footer{text-align:center;color:var(--muted);padding:24px 0;font-size:13px}
.hint{color:var(--muted);font-size:13px;margin-top:10px}
.result-card{text-align:center;padding:20px 0}
.result-score{font-size:72px;font-weight:900;color:var(--violet);line-height:1}
.result-label{color:var(--muted);margin:8px 0 24px}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:12px}
.result-stat{background:var(--paper);border-radius:12px;padding:16px;border:1px solid var(--line)}
.result-stat b{display:block;font-size:24px;color:var(--violet)}
.best{color:var(--gold);font-weight:800;margin-top:8px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

_JS = r"""
"use strict";
const G = __PAYLOAD__;
const S = G.settings;
const $ = id => document.getElementById(id);

// ── Randomness: fresh seed per page load, high bits only ─────────────────────
function freshSeed(){
  try{const a=new Uint32Array(1);crypto.getRandomValues(a);return a[0]>>>0;}
  catch(e){return (Date.now()^Math.floor(performance.now()*1e3))>>>0;}
}
let lcg = freshSeed();
function next32(){lcg=(Math.imul(1664525,lcg)+1013904223)>>>0;return lcg;}
const below = n => Math.floor(next32()/4294967296*n);
const pick = a => a[below(a.length)];
function shuffled(a){const r=[...a];for(let i=r.length-1;i>0;i--){const j=below(i+1);[r[i],r[j]]=[r[j],r[i]];}return r;}
const sample = (a,n) => shuffled(a).slice(0,n);

// ── Data helpers (mirror core/game.py) ───────────────────────────────────────
const finite = v => {if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;};
const pointOf = r => {const p=r.centroid;if(!Array.isArray(p)||p.length<2)return null;const lon=finite(p[0]),lat=finite(p[1]);return lon===null||lat===null?null:[lon,lat];};
const distinct = (a,b) => Math.abs(a-b)>Math.max(1e-12,Math.max(Math.abs(a),Math.abs(b))*1e-12);
const RAD = Math.PI/180;
function distanceM(r1,r2){const a=pointOf(r1),b=pointOf(r2);const lat1=a[1]*RAD,lat2=b[1]*RAD,dlat=(b[1]-a[1])*RAD,dlon=(b[0]-a[0])*RAD;const h=Math.sin(dlat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dlon/2)**2;return 12742017.6*Math.asin(Math.min(1,Math.sqrt(h)));}
function bearingDeg(r1,r2){const a=pointOf(r1),b=pointOf(r2);const lat1=a[1]*RAD,lat2=b[1]*RAD,dlon=(b[0]-a[0])*RAD;const y=Math.sin(dlon)*Math.cos(lat2),x=Math.cos(lat1)*Math.sin(lat2)-Math.sin(lat1)*Math.cos(lat2)*Math.cos(dlon);return(Math.atan2(y,x)/RAD+360)%360;}
const DIRS=[['North',0],['North-East',45],['East',90],['South-East',135],['South',180],['South-West',225],['West',270],['North-West',315]];
const compassDir = deg => DIRS[Math.floor(((deg%360)+22.5)/45)%8];
const bearingMargin = deg => {const o=((deg-22.5)%45+45)%45;return Math.min(o,45-o);};

const memo={};
const cached=(k,f)=>k in memo?memo[k]:(memo[k]=f());
const located=()=>cached('located',()=>G.records.filter(pointOf));
const valued=()=>cached('valued',()=>G.records.filter(r=>finite(r.value)!==null));
const valuePairs=()=>cached('vp',()=>{const c=G.records.map(r=>[r,finite(r[G.metric])]).filter(x=>x[1]!==null),out=[];for(let i=0;i<c.length;i++)for(let j=i+1;j<c.length;j++)if(distinct(c[i][1],c[j][1]))out.push([c[i][0],c[j][0],c[i][1],c[j][1]]);return out;});
const distancePairs=()=>cached('dp',()=>{const v=located(),out=[];for(let i=0;i<v.length;i++)for(let j=i+1;j<v.length;j++){const m=distanceM(v[i],v[j]);if(m>0.01)out.push([v[i],v[j],m]);}return out;});
const guessPairs=()=>cached('gp',()=>{const all=distancePairs(),floor=G.distance.widest_m*G.distance.min_share,fair=all.filter(p=>p[2]>=floor);return fair.length?fair:all;});
const directionPairs=()=>cached('dir',()=>{const out=[];distancePairs().forEach(([a,b])=>{[[a,b],[b,a]].forEach(([o,t])=>{const d=bearingDeg(o,t);if(bearingMargin(d)>=G.bearing_margin)out.push([o,t,d]);});});return out.length?out:distancePairs().map(([a,b])=>[a,b,bearingDeg(a,b)]);});
const nearestOptions=()=>cached('no',()=>{const v=located(),out=[];v.forEach(ref=>{const ranked=v.filter(r=>r!==ref).map(r=>[distanceM(ref,r),r]).sort((a,b)=>a[0]-b[0]);if(ranked.length>=4&&ranked[0][0]>0.01&&distinct(ranked[0][0],ranked[1][0]))out.push([ref,ranked.map(x=>x[1])]);});return out;});

// ── Formatting ───────────────────────────────────────────────────────────────
const fmtNum = v => {const a=Math.abs(v);return v.toLocaleString(undefined,{maximumFractionDigits:a>=1000?0:a>=10?1:a>=1?2:4});};
const D=G.distance;
const fmtDist = metres => {const v=metres/D.factor;return (D.unit==='m'?Math.round(v).toLocaleString():v.toLocaleString(undefined,{maximumFractionDigits:v>=100?0:v>=10?1:2}))+' '+D.unit;};
const what = G.value_label;

// ── Labels ───────────────────────────────────────────────────────────────────
const T={bigger:'Value Duel',distance:'Distance Guess',silhouette:'Know the Shape',
  attr_guess:'Attribute Guess',ordering:'Ranking',nearest:'Nearest Neighbour',direction:'Compass Quest'};

// ── State ────────────────────────────────────────────────────────────────────
let score,lives,streak,bestStreak,round,correctCount,current,timerId,bag,lastMode;
let deadline=0,shownAt=0;

function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}

function nextMode(){
  if(!bag.length){bag=shuffled(G.modes);if(bag.length>1&&bag[0]===lastMode)[bag[0],bag[1]]=[bag[1],bag[0]];}
  lastMode=bag.shift();return lastMode;
}

// ── Question builders: each returns false if its data is unusable ───────────
const builders={
  bigger(arena){
    const pairs=valuePairs();if(!pairs.length)return false;
    let [a,b,av,bv]=pick(pairs);if(below(2))[a,b,av,bv]=[b,a,bv,av];
    const answer=av>bv?a.label:b.label;
    current.answer=answer;
    current.detail=`${a.label}: ${fmtNum(av)} · ${b.label}: ${fmtNum(bv)}`;
    current.prompt=G.metric==='value'?`Which one has the greater ${what}?`:'Which one covers the larger area?';
    choices(arena,[a.label,b.label]);return true;
  },
  silhouette(arena){
    const pool=G.records.filter(r=>Array.isArray(r.outline)&&r.outline.length>2);if(pool.length<4)return false;
    const opts=sample(pool,Math.min(S.choices,pool.length)),target=pick(opts);
    current.answer=target.label;current.detail=target.label;current.prompt='Whose silhouette is this?';
    arena.appendChild(silhouette(target.outline));
    choices(arena,shuffled(opts.map(r=>r.label)));return true;
  },
  distance(arena){
    const pairs=guessPairs();if(!pairs.length)return false;
    const [a,b,truth]=pick(pairs);
    current.answer=truth;current.detail=fmtDist(truth);
    current.prompt=`How far is it from ${a.label} to ${b.label}?`;
    const max=D.max,step=max/400;
    const wrap=el('div','slider-wrap'),val=el('div','slider-val',`0 ${D.unit}`),rng=el('input');
    rng.type='range';rng.min='0';rng.max=String(max);rng.step=String(step);rng.value='0';
    rng.setAttribute('aria-label',`Distance in ${D.unit}`);
    rng.oninput=()=>{val.textContent=fmtDist(Number(rng.value)*D.factor);};
    const hint=el('div','slider-hint');hint.append(el('span','',`0 ${D.unit}`),el('span','',`${fmtNum(max)} ${D.unit}`));
    const go=el('button','primary','Submit estimate');go.dataset.submit='1';
    go.onclick=()=>{const guess=Number(rng.value)*D.factor,err=Math.abs(guess-truth)/Math.max(1e-9,truth);
      judge(err<=S.tolerance,Math.max(0.25,1-err),`Your estimate: ${fmtDist(guess)}`);};
    wrap.append(val,rng,hint,go);arena.appendChild(wrap);rng.focus();return true;
  },
  attr_guess(arena){
    const pool=valued(),vals=pool.map(r=>finite(r.value));if(new Set(vals).size<2)return false;
    const target=pick(pool),lo=Math.min(...vals),hi=Math.max(...vals),truth=finite(target.value);
    current.answer=truth;current.detail=fmtNum(truth);current.prompt=`Estimate the ${what} of ${target.label}`;
    const wrap=el('div','slider-wrap'),val=el('div','slider-val'),rng=el('input');
    rng.type='range';rng.min=String(lo);rng.max=String(hi);rng.step=String((hi-lo)/200);rng.value=String((lo+hi)/2);
    rng.setAttribute('aria-label',`Estimated ${what}`);
    const show=()=>{val.textContent=fmtNum(Number(rng.value));};show();rng.oninput=show;
    const hint=el('div','slider-hint');hint.append(el('span','',fmtNum(lo)),el('span','',fmtNum(hi)));
    const go=el('button','primary','Submit guess');go.dataset.submit='1';
    go.onclick=()=>{const guess=Number(rng.value),err=Math.abs(guess-truth)/(hi-lo);
      judge(err<=S.tolerance,Math.max(0.25,1-err),`Your guess: ${fmtNum(guess)}`);};
    wrap.append(val,rng,hint,go);arena.appendChild(wrap);rng.focus();return true;
  },
  ordering(arena){
    const groups=new Map();valued().forEach(r=>{const v=finite(r.value);groups.set(v,[...(groups.get(v)||[]),r]);});
    if(groups.size<3)return false;
    const items=sample([...groups.keys()],Math.min(4,groups.size)).map(v=>pick(groups.get(v)));
    const answer=[...items].sort((a,b)=>finite(b.value)-finite(a.value)).map(r=>r.label);
    let order=shuffled(items);if(order.every((r,i)=>r.label===answer[i]))order=[...order.slice(1),order[0]];
    current.answer=answer;current.prompt=`Rank these from highest to lowest ${what}`;
    current.detail=[...items].sort((a,b)=>finite(b.value)-finite(a.value)).map(r=>`${r.label} (${fmtNum(finite(r.value))})`).join(' > ');
    rankList(arena,order);return true;
  },
  nearest(arena){
    const options=nearestOptions();if(!options.length)return false;
    const [ref,ranked]=pick(options),n=Math.min(Math.max(2,S.choices),ranked.length),others=ranked.slice(1);
    const pool=G.difficulty==='Hard'?others.slice(0,Math.max(n*2,n-1)):G.difficulty==='Medium'?others.slice(0,Math.max(Math.floor(others.length/2),n-1)):others;
    const nearest=ranked[0];
    current.answer=nearest.label;current.detail=`${nearest.label} (${fmtDist(distanceM(ref,nearest))})`;
    current.prompt=`Which feature is closest to ${ref.label}?`;
    choices(arena,shuffled([nearest,...sample(pool,n-1)].map(r=>r.label)));return true;
  },
  direction(arena){
    const pairs=directionPairs();if(!pairs.length)return false;
    const [a,b,deg]=pick(pairs),[name,ang]=compassDir(deg),ans=`${name} (${ang}°)`;
    current.answer=ans;current.detail=`${ans} — true bearing ${deg.toFixed(1)}°`;
    current.prompt=`In which compass direction is ${b.label} from ${a.label}?`;
    const all=DIRS.map(([n,g])=>`${n} (${g}°)`).filter(x=>x!==ans);
    choices(arena,shuffled([ans,...sample(all,S.choices-1)]));return true;
  },
};

function silhouette(outline){
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),path=document.createElementNS(ns,'path');
  const xs=outline.map(p=>p[0]),ys=outline.map(p=>p[1]);
  const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
  const w=maxx-minx||1e-12,h=maxy-miny||1e-12,s=Math.min(320/w,200/h);   // one scale: keep the shape's proportions
  const ox=(360-w*s)/2,oy=(240-h*s)/2;
  path.setAttribute('d',outline.map((p,i)=>`${i?'L':'M'}${(ox+(p[0]-minx)*s).toFixed(2)} ${(240-oy-(p[1]-miny)*s).toFixed(2)}`).join(' ')+'Z');
  svg.setAttribute('viewBox','0 0 360 240');svg.setAttribute('class','outline');svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Feature silhouette');svg.appendChild(path);return svg;
}

function choices(arena,items){
  const box=el('div','choices');
  items.forEach((label,i)=>{const b=el('button','choice');b.dataset.choice=label;
    if(i<9)b.appendChild(el('kbd','',String(i+1)));b.appendChild(el('span','',label));
    b.onclick=()=>judge(label===current.answer,1,'',b);box.appendChild(b);});
  arena.appendChild(box);
}

function rankList(arena,items){
  const list=el('div','rank-list'),go=el('button','primary','Submit ranking');go.dataset.submit='1';
  function redraw(focus){
    list.replaceChildren();
    items.forEach((item,i)=>{
      const row=el('div','rank-row'),up=el('button','rank-move','▲'),down=el('button','rank-move','▼');
      up.setAttribute('aria-label',`Move ${item.label} up`);down.setAttribute('aria-label',`Move ${item.label} down`);
      up.disabled=i===0;down.disabled=i===items.length-1;
      up.onclick=()=>{[items[i-1],items[i]]=[items[i],items[i-1]];redraw([i-1,0]);};
      down.onclick=()=>{[items[i+1],items[i]]=[items[i],items[i+1]];redraw([i+1,1]);};
      row.append(el('span','rank-pos',String(i+1)),el('span','rank-label',item.label),up,down);list.appendChild(row);
    });
    if(focus){const btn=list.children[focus[0]].querySelectorAll('button')[focus[1]];if(btn&&!btn.disabled)btn.focus();}
  }
  go.onclick=()=>judge(items.every((r,i)=>r.label===current.answer[i]),1,'Your order: '+items.map(r=>r.label).join(' > '));
  arena.append(list,go);redraw();
}

// ── Round flow ───────────────────────────────────────────────────────────────
function updateHeader(){
  $('hd-round').textContent=Math.min(round+1,G.rounds);$('hd-lives').textContent=lives;
  $('hd-streak').textContent=streak>=2?` 🔥×${streak}`:'';
  document.querySelectorAll('.dot').forEach((d,i)=>d.classList.toggle('now',i===round&&!current?.done));
}

function make(){
  const card=$('main-card');card.replaceChildren();
  const badge=el('div','badge'),prompt=el('h1'),arena=el('div'),fb=el('div');
  prompt.id='prompt';fb.id='feedback';fb.setAttribute('role','status');fb.setAttribute('aria-live','polite');
  card.append(badge,prompt,arena,fb);
  const order=[nextMode(),...G.modes];
  for(const mode of order){
    arena.replaceChildren();current={mode,done:false};
    if(builders[mode](arena)){badge.textContent=T[mode];prompt.textContent=current.prompt;
      updateHeader();startTimer();return;}
  }
  prompt.textContent='No challenge could be generated from this data.';
}

function startTimer(){
  clearInterval(timerId);shownAt=performance.now();deadline=shownAt+S.timer*1000;
  const fill=$('timer-fill');
  timerId=setInterval(()=>{const left=Math.max(0,deadline-performance.now()),pct=left/(S.timer*1000);
    fill.style.width=(pct*100)+'%';
    fill.style.background=pct>0.5?'linear-gradient(90deg,var(--violet),var(--cyan))':pct>0.25?'linear-gradient(90deg,#f59e0b,#fbbf24)':'linear-gradient(90deg,#ef4444,#f87171)';
    if(left<=0){clearInterval(timerId);judge(false,1,"⏱ Time's up!");}},100);
}

function judge(ok,closeness,note,clicked){
  if(!current||current.done)return;
  current.done=true;clearInterval(timerId);
  const seconds=(performance.now()-shownAt)/1000;
  if(seconds>=S.timer)ok=false;
  round++;let gained=0;
  if(ok){correctCount++;streak++;bestStreak=Math.max(bestStreak,streak);
    const speed=Math.max(0,150-Math.floor(seconds*8)),bonus=Math.min(300,Math.max(0,streak-1)*30);
    gained=Math.floor((500+speed+bonus)*Math.min(1,Math.max(0.25,closeness)));score+=gained;}
  else{lives=Math.max(0,lives-1);streak=0;}
  const dot=$('dot-'+(round-1));if(dot)dot.className='dot '+(ok?'correct':'wrong');
  const chip=$('hd-score');chip.textContent=score.toLocaleString();chip.classList.remove('pop');void chip.offsetWidth;chip.classList.add('pop');
  document.querySelectorAll('#main-card button:not(.primary), #main-card input').forEach(x=>x.disabled=true);
  document.querySelectorAll('[data-submit]').forEach(x=>x.remove());
  document.querySelectorAll('.choice').forEach(b=>{if(b.dataset.choice===current.answer)b.classList.add('good');
    else if(b===clicked)b.classList.add('bad');else b.classList.add('dim');});
  const fb=$('feedback');fb.className=ok?'good':'bad';
  fb.textContent=(ok?`Correct! +${gained.toLocaleString()}`:'Not this time.')+(ok?'':` Answer: ${current.detail}`);
  if(note||ok){const sm=el('small','',[note,ok?current.detail:''].filter(Boolean).join(' · '));fb.appendChild(sm);}
  updateHeader();
  const over=round>=G.rounds||lives<=0,btn=el('button','primary',over?'See results →':'Next challenge →');
  btn.id='next-btn';btn.onclick=over?finish:make;$('main-card').appendChild(btn);btn.focus();
}

function rankTier(s,acc){
  if(s>=3500&&acc>=90)return['Grand Geographer & Master Cartographer','👑'];
  if(s>=2500&&acc>=80)return['Senior Spatial Analyst','🌟'];
  if(s>=1500&&acc>=65)return['Journeyman Surveyor','🧭'];
  if(s>=800&&acc>=50)return['Cartographic Scout','🗺️'];
  return['Apprentice Navigator','📍'];
}

function storageGet(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function storageSet(k,v){try{localStorage.setItem(k,v);}catch(e){}}

function finish(){
  clearInterval(timerId);current=null;
  const acc=round?Math.round(correctCount/round*100):0,[tier,icon]=rankTier(score,acc);
  const key='gq-best:'+G.title+':'+G.difficulty,prev=Number(storageGet(key)||0),isBest=score>prev;
  if(isBest)storageSet(key,String(score));
  const card=$('main-card');card.replaceChildren();
  const box=el('div','result-card');
  box.append(el('div','result-score',score.toLocaleString()),el('div','result-label',`★ Final score · ${icon} ${tier}`));
  const grid=el('div','result-grid');
  [[`${correctCount}/${round}`,'Correct'],[`${acc}%`,'Accuracy'],[String(bestStreak),'Best streak'],[G.difficulty,'Difficulty']]
    .forEach(([v,l])=>{const s=el('div','result-stat');s.append(el('b','',v),document.createTextNode(l));grid.appendChild(s);});
  box.appendChild(grid);
  box.appendChild(el('div','best',isBest&&prev>0?'New personal best on this device!':prev>0?`Personal best: ${prev.toLocaleString()}`:''));
  const again=el('button','primary','Play again ↺');again.onclick=start;box.appendChild(again);
  card.appendChild(box);again.focus();
  $('timer-fill').style.width='0%';
}

function start(){
  score=0;lives=G.lives;streak=0;bestStreak=0;round=0;correctCount=0;current=null;bag=[];lastMode=null;
  $('hd-score').textContent='0';
  const dots=$('dots');dots.replaceChildren();
  for(let i=0;i<G.rounds;i++){const d=el('div','dot');d.id='dot-'+i;dots.appendChild(d);}
  make();
}

// ── Keyboard: 1–9 pick a choice, Enter submits or advances ───────────────────
document.addEventListener('keydown',e=>{
  if(e.altKey||e.ctrlKey||e.metaKey)return;
  if(/^[1-9]$/.test(e.key)&&e.target.tagName!=='INPUT'){
    const btns=[...document.querySelectorAll('.choice:not(:disabled)')],b=btns[Number(e.key)-1];
    if(b){b.click();e.preventDefault();}return;
  }
  if(e.key==='Enter'&&e.target.tagName!=='BUTTON'){
    const b=document.querySelector('[data-submit]')||$('next-btn');if(b){b.click();e.preventDefault();}
  }
});

// ── Theme ────────────────────────────────────────────────────────────────────
function applyTheme(t){document.documentElement.dataset.theme=t;$('theme-btn').textContent=t==='dark'?'☀️':'🌙';}
$('theme-btn').onclick=()=>{const t=document.documentElement.dataset.theme==='dark'?'light':'dark';applyTheme(t);storageSet('gq-theme',t);};
applyTheme(storageGet('gq-theme')||(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));

start();
"""


def build_html(title: str, records: list[dict], modes: list[str], rounds: int,
               difficulty: str = "Medium", lives: int = 3,
               value_label: str = "value") -> str:
    """Return a self-contained HTML quiz. locate and blind_zoom are excluded."""
    payload = build_payload(title, records, modes, rounds, difficulty, lives, value_label)
    safe_title = html.escape(payload["title"])
    rounds_text = str(payload["rounds"])
    lives_text = str(payload["lives"])
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{safe_title} · 02GeoQuest</title>\n'
        f'<style>{_CSS}</style></head><body>\n'
        '<div class="shell">\n<header>\n'
        f'  <div class="brand"><b>02</b>GeoQuest<small>{safe_title}</small></div>\n'
        '  <div class="stats">\n'
        f'    <span class="chip">Round <span id="hd-round">1</span>/{rounds_text}</span>\n'
        '    <span class="chip">★ <span id="hd-score">0</span><span id="hd-streak"></span></span>\n'
        f'    <span class="chip">♥ <span id="hd-lives">{lives_text}</span></span>\n'
        '    <button class="icon-btn" id="theme-btn" type="button" title="Toggle dark mode">🌙</button>\n'
        '  </div>\n</header>\n'
        '<div id="timer-bar"><div id="timer-fill"></div></div>\n'
        '<div class="progress-dots" id="dots"></div>\n'
        '<main class="card" id="main-card"></main>\n'
        f'<footer>{safe_title} · {html.escape(payload["difficulty"])} · '
        'Built with <b>02</b>GeoQuest · Works offline · No data leaves your device'
        '<br><span class="hint">Keys: 1–9 choose · Enter submits / continues</span></footer>\n'
        '</div>\n'
        '<script>' + _JS.replace("__PAYLOAD__", _safe_json(payload)) + '</script>\n'
        '</body></html>\n'
    )


def write_html(path: str, title: str, records: list[dict], modes: list[str],
               rounds: int, difficulty: str = "Medium", lives: int = 3,
               value_label: str = "value") -> None:
    Path(path).write_text(
        build_html(title, records, modes, rounds, difficulty, lives, value_label),
        encoding="utf-8")
