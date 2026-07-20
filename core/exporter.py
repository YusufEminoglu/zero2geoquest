"""Premium single-file GeoQuest HTML export — no CDN, no external assets."""
from __future__ import annotations

import html
import json
from pathlib import Path

# Modes supported in offline HTML (locate and blind_zoom need QGIS canvas)
_HTML_MODES = {"bigger", "distance", "silhouette", "attr_guess", "nearest"}


def _safe_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(title: str, records: list[dict], modes: list[str],
               rounds: int) -> str:
    """Return a self-contained HTML quiz. locate and blind_zoom are excluded."""
    active_modes = [m for m in modes if m in _HTML_MODES] or list(_HTML_MODES)[:2]
    payload = {
        "title": title,
        "records": records,
        "modes": active_modes,
        "rounds": max(1, int(rounds)),
    }
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} · 02GeoQuest</title>
<style>
:root{{
  --ink:#17212b;--muted:#6b7b8c;--paper:#f2f6fa;--card:#fff;
  --violet:#6c4cff;--cyan:#00b8d9;--good:#13a86b;--bad:#e94f64;
  --gold:#f59e0b;--shadow:0 20px 60px #25356a1a;
}}
[data-theme=dark]{{
  --ink:#e2e8f0;--muted:#94a3b8;--paper:#0f172a;--card:#1e293b;
  --shadow:0 20px 60px #00000040;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--paper);font:16px/1.5 system-ui,sans-serif;color:var(--ink);transition:background .3s,color .3s;min-height:100vh}}
.shell{{max-width:900px;margin:auto;padding:20px 16px}}
header{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 0 20px;flex-wrap:wrap}}
.brand{{font-weight:900;font-size:26px;letter-spacing:-0.5px}}
.brand b{{color:var(--violet)}}
.stats{{display:flex;gap:10px;flex-wrap:wrap}}
.chip{{background:var(--card);border:1px solid #dce4ed;border-radius:999px;padding:8px 14px;font-weight:700;box-shadow:var(--shadow);font-size:14px}}
[data-theme=dark] .chip{{border-color:#334155}}
.dark-btn{{border:1px solid #dce4ed;background:var(--card);border-radius:9px;padding:8px 12px;cursor:pointer;font-size:16px;color:var(--ink)}}
.card{{background:var(--card);border:1px solid #dce4ed;border-radius:24px;box-shadow:var(--shadow);padding:clamp(20px,4vw,40px);margin-bottom:20px;transition:background .3s}}
[data-theme=dark] .card{{border-color:#334155}}
.badge{{color:var(--violet);text-transform:uppercase;letter-spacing:.14em;font-weight:900;font-size:11px;margin-bottom:10px}}
h1{{font-size:clamp(22px,4vw,36px);font-weight:800;margin-bottom:20px;line-height:1.2}}
.choices{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:16px}}
@media(max-width:560px){{.choices{{grid-template-columns:1fr}}}}
button{{border:1.5px solid #d7dfeb;background:var(--card);border-radius:16px;padding:16px 14px;cursor:pointer;color:var(--ink);font-weight:700;font-size:15px;transition:all .15s;text-align:left;line-height:1.3}}
button:hover:not(:disabled){{border-color:var(--violet);transform:translateY(-2px);box-shadow:0 8px 24px #6c4cff18}}
button:disabled{{opacity:.55;cursor:default;transform:none}}
.btn-good{{border-color:var(--good)!important;background:#e9fdf4!important;color:#166534!important}}
.btn-bad{{border-color:var(--bad)!important;background:#fff0f3!important;color:#9b1c3a!important}}
[data-theme=dark] .btn-good{{background:#052e16!important;color:#4ade80!important}}
[data-theme=dark] .btn-bad{{background:#2d0a14!important;color:#f87171!important}}
.primary{{background:linear-gradient(135deg,var(--violet) 0%,#a78bfa 100%);color:#fff;border:0;border-radius:14px;padding:16px 24px;font-weight:800;font-size:16px;cursor:pointer;transition:all .2s;display:block;width:100%;margin-top:16px;text-align:center}}
.primary:hover{{transform:translateY(-2px);box-shadow:0 12px 32px #6c4cff40}}
.primary:disabled{{opacity:.5;cursor:default;transform:none}}
.outline{{width:min(340px,80vw);height:220px;display:block;margin:0 auto 20px;filter:drop-shadow(0 12px 20px #4352a730)}}
.outline path{{fill:#6c4cff;stroke:#3d2baa;stroke-width:1.5}}
#timer-bar{{width:100%;height:6px;background:#e2e8f0;border-radius:3px;margin-bottom:18px;overflow:hidden}}
#timer-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--violet),var(--cyan));transition:width .4s linear}}
[data-theme=dark] #timer-bar{{background:#1e293b}}
.slider-wrap{{padding:8px 0 16px}}
input[type=range]{{width:100%;accent-color:var(--violet);height:6px;cursor:pointer}}
.slider-val{{text-align:center;font-size:28px;font-weight:900;color:var(--violet);margin-bottom:12px}}
.slider-hint{{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}}
#feedback{{min-height:52px;font-size:17px;font-weight:700;margin:14px 0;padding:12px 16px;border-radius:12px;display:none}}
#feedback.good{{display:block;background:#e9fdf4;color:#166534;border:1px solid #bbf7d0}}
#feedback.bad{{display:block;background:#fff0f3;color:#9b1c3a;border:1px solid #fecdd3}}
[data-theme=dark] #feedback.good{{background:#052e16;border-color:#166534}}
[data-theme=dark] #feedback.bad{{background:#2d0a14;border-color:#9b1c3a}}
.score-anim{{animation:scorepop .5s cubic-bezier(.36,.07,.19,.97) both}}
@keyframes scorepop{{0%{{transform:scale(1)}}30%{{transform:scale(1.25)}}100%{{transform:scale(1)}}}}
.streak-fire{{display:none;font-size:22px;margin-left:8px;animation:fire .6s ease-in-out infinite alternate}}
@keyframes fire{{from{{transform:scale(1) rotate(-3deg)}}to{{transform:scale(1.15) rotate(3deg)}}}}
.progress-dots{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}}
.dot{{width:10px;height:10px;border-radius:50%;background:#e2e8f0;transition:background .3s}}
[data-theme=dark] .dot{{background:#334155}}
.dot.done{{background:var(--violet)}}
.dot.correct{{background:var(--good)}}
.dot.wrong{{background:var(--bad)}}
footer{{text-align:center;color:var(--muted);padding:24px 0;font-size:13px}}
.result-card{{text-align:center;padding:40px 20px}}
.result-score{{font-size:72px;font-weight:900;color:var(--violet);line-height:1}}
.result-label{{color:var(--muted);margin:8px 0 24px}}
.result-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}}
.result-stat{{background:var(--paper);border-radius:12px;padding:16px;border:1px solid #dce4ed}}
[data-theme=dark] .result-stat{{border-color:#334155}}
.result-stat b{{display:block;font-size:24px;color:var(--violet)}}
</style></head><body>
<div class="shell">
<header>
  <div class="brand"><b>02</b>GeoQuest</div>
  <div class="stats">
    <span class="chip">Round <span id="hd-round">1</span>/{payload['rounds']}</span>
    <span class="chip">★ <span id="hd-score">0</span><span class="streak-fire" id="fire">🔥</span></span>
    <span class="chip">♥ <span id="hd-lives">3</span></span>
  </div>
  <button class="dark-btn" onclick="toggleDark()" title="Toggle dark mode">🌙</button>
</header>
<div id="timer-bar"><div id="timer-fill" style="width:100%"></div></div>
<div class="progress-dots" id="dots"></div>
<main class="card" id="main-card">
  <div class="badge" id="mode-badge"></div>
  <h1 id="prompt"></h1>
  <div id="arena"></div>
  <div id="feedback"></div>
  <button class="primary" id="next-btn" hidden>Next challenge →</button>
</main>
<footer>{safe_title} · Built with <b>02</b>GeoQuest · Works offline · No data leaves your device</footer>
</div>
<script>
const G={_safe_json(payload)};
const T={{
  locate:'Map Hunt',bigger:'Value Duel',distance:'Distance Guess',
  silhouette:'Know the Shape',attr_guess:'Attribute Guess',
  ordering:'Ranking',nearest:'Nearest Neighbour',blind_zoom:'Blind Zoom',
  greater:'Which one has the greater value?',
  shape:'Whose silhouette is this?',
  nearest_q:'Which feature is closest to',
  attr_q:'Estimate the value of',
  order_q:'Rank these from highest to lowest value',
  correct:'Correct! ',wrong:'Not this time. ',
  next:'Next challenge →',finish:'Quest complete!',again:'Play again ↺',
  rank_btn:'Submit ranking',dist_btn:'Submit estimate',attr_btn:'Submit guess',
}};
let score=0,lives=3,streak=0,round=0,correct_count=0,current=null,timerInterval=null;
const dots_data=[];
const $=id=>document.getElementById(id);
const esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const pick=a=>a[Math.floor(LCG_next()%a.length)];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

// LCG deterministic shuffle
let lcg_state=42;
function LCG_next(){{lcg_state=(1664525*lcg_state+1013904223)>>>0;return lcg_state;}}
function shuffled(a){{let r=[...a];for(let i=r.length-1;i>0;i--){{let j=LCG_next()%(i+1);[r[i],r[j]]=[r[j],r[i]]}};return r;}}
function sample(pool,n){{return shuffled(pool).slice(0,n);}}

// Dark mode
function toggleDark(){{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'':'dark';localStorage.setItem('gq-dark',document.documentElement.dataset.theme);}}
if(localStorage.getItem('gq-dark')==='dark')document.documentElement.dataset.theme='dark';

// Dots
function initDots(){{const c=$('dots');c.innerHTML='';for(let i=0;i<G.rounds;i++){{const d=document.createElement('div');d.className='dot';d.id='dot-'+i;c.appendChild(d);dots_data.push('pending');}}}}

function updateDot(is_correct){{if(round-1<G.rounds){{dots_data[round-1]=is_correct?'correct':'wrong';const d=$('dot-'+(round-1));if(d)d.className='dot '+(is_correct?'correct':'wrong');}}}}

// Timer
let timer_ms=0,timer_max=0;
function startTimer(secs){{clearInterval(timerInterval);timer_ms=secs*1000;timer_max=secs*1000;updateTimerUI();timerInterval=setInterval(()=>{{timer_ms=Math.max(0,timer_ms-200);updateTimerUI();if(timer_ms<=0){{clearInterval(timerInterval);onTimeout();}}}},200);}}
function stopTimer(){{clearInterval(timerInterval);$('timer-fill').style.width='100%';$('timer-fill').style.background='linear-gradient(90deg,#6c4cff,#00b8d9)';}}
function updateTimerUI(){{const pct=timer_ms/timer_max;$('timer-fill').style.width=(pct*100)+'%';const color=pct>0.5?'linear-gradient(90deg,#6c4cff,#00b8d9)':pct>0.25?'linear-gradient(90deg,#f59e0b,#fbbf24)':'linear-gradient(90deg,#ef4444,#f87171)';$('timer-fill').style.background=color;}}
function onTimeout(){{judge(false,'—','Time\'s up!');}}

// Score animation
function animateScore(from,to){{let start=null;const chip=$('hd-score');const step=ts=>{{if(!start)start=ts;const p=Math.min((ts-start)/400,1);chip.textContent=Math.round(from+(to-from)*p);chip.classList.add('score-anim');if(p<1)requestAnimationFrame(step);}};requestAnimationFrame(step);}}

// SVG silhouette
function svg(outline){{if(!outline||outline.length<3)return'';let xs=outline.map(p=>p[0]),ys=outline.map(p=>p[1]);let minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),w=maxx-minx||1,h=maxy-miny||1;let d=outline.map((p,i)=>`${{i?'L':'M'}} ${{20+(p[0]-minx)/w*320}} ${{220-(p[1]-miny)/h*200}}`).join(' ')+' Z';return `<svg class="outline" viewBox="0 0 360 240"><path d="${{d}}"/></svg>`;}}

// Mode dispatcher
function make(){{
  const arena=$('arena');arena.innerHTML='';
  $('feedback').className='';$('next-btn').hidden=true;
  const mode=pick(G.modes);
  $('mode-badge').textContent=T[mode]||mode;

  if(mode==='bigger'){{
    let [a,b]=sample(G.records,2);
    let av=Number(a.value??a.area??0),bv=Number(b.value??b.area??0);
    current={{mode,answer:av>=bv?a.label:b.label,detail:`${{a.label}}: ${{av.toLocaleString(undefined,{{maximumFractionDigits:2}})}}, ${{b.label}}: ${{bv.toLocaleString(undefined,{{maximumFractionDigits:2}})}}`}};
    $('prompt').textContent=T.greater;
    choices([a.label,b.label],current.answer);
  }}
  else if(mode==='silhouette'){{
    let pool=G.records.filter(r=>r.outline&&r.outline.length>2);
    if(pool.length<4){{make();return;}}
    let opts=sample(pool,Math.min(4,pool.length)),target=pick(opts);
    current={{mode,answer:target.label,detail:target.label}};
    $('prompt').textContent=T.shape;
    arena.innerHTML=svg(target.outline);
    choices(shuffled(opts.map(r=>r.label)),current.answer);
  }}
  else if(mode==='distance'){{
    let [a,b]=sample(G.records,2);
    let dx=a.centroid[0]-b.centroid[0],dy=a.centroid[1]-b.centroid[1];
    let truth=Math.hypot(dx,dy)*111320*Math.cos((a.centroid[1]+b.centroid[1])*Math.PI/360);
    current={{mode,answer:truth,detail:`${{(truth/1000).toFixed(2)}} km`}};
    $('prompt').textContent=`${{a.label}} → ${{b.label}}`;
    let max=Math.max(2000,truth*2.5);
    arena.innerHTML=`<div class="slider-wrap">
      <div class="slider-val" id="sv">${{Math.round(max/2/1000)}} km</div>
      <input id="rng" type="range" min="0" max="${{Math.round(max)}}" value="${{Math.round(max/2)}}">
      <div class="slider-hint"><span>0 km</span><span>${{(max/1000).toFixed(0)}} km</span></div>
      <button class="primary" id="dist-submit">${{T.dist_btn}}</button></div>`;
    $('rng').oninput=e=>$('sv').textContent=Math.round(e.target.value/1000)+' km';
    $('dist-submit').onclick=()=>{{let ratio=Math.abs(Number($('rng').value)-truth)/Math.max(1,truth);judge(ratio<=0.25,current.detail,ratio<=0.25?'':'Answer: '+current.detail);}};
  }}
  else if(mode==='attr_guess'){{
    let valued=G.records.filter(r=>r.value!=null);if(valued.length<2){{make();return;}}
    let target=pick(valued);
    let all_vals=valued.map(r=>Number(r.value));
    let min_v=Math.min(...all_vals),max_v=Math.max(...all_vals);
    current={{mode,answer:Number(target.value),detail:Number(target.value).toLocaleString(undefined,{{maximumFractionDigits:2}})}};
    $('prompt').textContent=`${{T.attr_q}}: ${{target.label}}`;
    let init=Math.round((min_v+(max_v-min_v)*0.5));
    arena.innerHTML=`<div class="slider-wrap">
      <div class="slider-val" id="sv">${{init.toLocaleString()}}</div>
      <input id="rng" type="range" min="${{Math.floor(min_v)}}" max="${{Math.ceil(max_v)}}" value="${{init}}" step="${{Math.max(1,Math.round((max_v-min_v)/200))}}">
      <div class="slider-hint"><span>${{min_v.toLocaleString()}}</span><span>${{max_v.toLocaleString()}}</span></div>
      <button class="primary" id="attr-submit">${{T.attr_btn}}</button></div>`;
    $('rng').oninput=e=>$('sv').textContent=Number(e.target.value).toLocaleString();
    $('attr-submit').onclick=()=>{{let guess=Number($('rng').value),truth=current.answer,tol=0.25;let ratio=Math.abs(guess-truth)/Math.max(1,Math.abs(truth));judge(ratio<=tol,current.detail,'Answer: '+current.detail);}};
  }}
  else if(mode==='nearest'){{
    if(G.records.length<5){{make();return;}}
    let pool=sample(G.records,5),ref=pool[0],cands=pool.slice(1);
    let dist=r=>Math.hypot(r.centroid[0]-ref.centroid[0],r.centroid[1]-ref.centroid[1]);
    let nearest=cands.reduce((a,b)=>dist(a)<dist(b)?a:b);
    current={{mode,answer:nearest.label,detail:nearest.label}};
    $('prompt').textContent=`${{T.nearest_q}} ${{ref.label}}?`;
    choices(shuffled(cands.map(r=>r.label)),nearest.label);
  }}
  else {{make();return;}}

  startTimer(30);
}}

function choices(items,answer){{
  const arena=$('arena');
  arena.innerHTML+='<div class="choices">'+items.map(x=>`<button data-a="${{esc(x)}}">${{esc(x)}}</button>`).join('')+'</div>';
  arena.querySelectorAll('button[data-a]').forEach(b=>b.onclick=()=>judge(b.dataset.a===answer,answer));
}}

function judge(ok,answer,extra_detail=''){{
  stopTimer();
  const old_score=score;
  round++;
  if(ok){{score+=500;streak++;correct_count++;}}
  else{{lives=Math.max(0,lives-1);streak=0;}}
  updateDot(ok);
  $('hd-round').textContent=Math.min(round+1,G.rounds);
  animateScore(old_score,score);
  $('hd-lives').textContent=lives;
  $('fire').style.display=streak>=3?'inline':'none';
  const fb=$('feedback');
  fb.className=ok?'good':'bad';
  fb.textContent=(ok?T.correct:T.wrong)+(extra_detail||String(answer));
  $('arena').querySelectorAll('button,input').forEach(x=>x.disabled=true);
  if(ok){{
    $('arena').querySelectorAll(`button[data-a="${{esc(String(answer))}}"]`).forEach(b=>b.className+=' btn-good');
  }}else{{
    $('arena').querySelectorAll(`button[data-a="${{esc(String(answer))}}"]`).forEach(b=>b.className+=' btn-good');
  }}
  const next=$('next-btn');
  next.hidden=false;
  if(round>=G.rounds||lives<=0){{next.textContent=T.finish;next.onclick=finish;}}
  else{{next.textContent=T.next;next.onclick=()=>{{$('main-card').innerHTML='';buildPlayCard();make();}};}}
}}

function buildPlayCard(){{
  const c=$('main-card');
  c.innerHTML=`<div class="badge" id="mode-badge"></div><h1 id="prompt"></h1><div id="arena"></div><div id="feedback"></div><button class="primary" id="next-btn" hidden>${{T.next}}</button>`;
}}

function finish(){{
  stopTimer();
  const acc=round>0?Math.round(correct_count/round*100):0;
  $('main-card').innerHTML=`<div class="result-card">
    <div class="result-score">${{score.toLocaleString()}}</div>
    <div class="result-label">★ Final Score</div>
    <div class="result-grid">
      <div class="result-stat"><b>${{correct_count}}/${{round}}</b>Correct</div>
      <div class="result-stat"><b>${{acc}}%</b>Accuracy</div>
      <div class="result-stat"><b>${{streak>0?streak:'—'}}</b>Final Streak</div>
    </div>
    <button class="primary" onclick="location.reload()">${{T.again}}</button>
  </div>`;
}}

initDots();make();
</script></body></html>"""


def write_html(path: str, title: str, records: list[dict], modes: list[str],
               rounds: int) -> None:
    Path(path).write_text(build_html(title, records, modes, rounds), encoding="utf-8")
