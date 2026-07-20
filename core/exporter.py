"""Create a dependency-free, single-file GeoQuest web game."""
from __future__ import annotations

import html
import json
from pathlib import Path


def _safe_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_html(title: str, records: list[dict], modes: list[str], rounds: int,
               language: str = "en") -> str:
    """Return a standalone HTML quiz; no CDN, network or external assets."""
    payload = {
        "title": title,
        "records": records,
        "modes": modes,
        "rounds": max(1, int(rounds)),
        "language": language,
    }
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="{html.escape(language)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} · 02GeoQuest</title>
<style>
:root{{--ink:#17212b;--muted:#6b7b8c;--paper:#f2f6fa;--card:#fff;--violet:#6c4cff;--cyan:#00b8d9;--good:#13a86b;--bad:#e94f64}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 10% 0,#dfe8ff,transparent 35%),var(--paper);font:16px system-ui,sans-serif;color:var(--ink)}}
.shell{{max-width:880px;margin:auto;padding:22px}} header{{display:flex;justify-content:space-between;align-items:center;gap:12px}} .brand{{font-weight:900;font-size:24px}} .brand b{{color:var(--violet)}}
.stats{{display:flex;gap:8px;flex-wrap:wrap}} .chip{{background:#fff;border:1px solid #dce4ed;border-radius:999px;padding:7px 12px;font-weight:700}}
.card{{margin-top:20px;background:rgba(255,255,255,.94);border:1px solid #dce4ed;border-radius:22px;box-shadow:0 18px 50px #25356a18;padding:clamp(18px,4vw,38px)}}
.mode{{color:var(--violet);text-transform:uppercase;letter-spacing:.12em;font-weight:900;font-size:12px}} h1{{font-size:clamp(24px,5vw,42px);margin:10px 0 22px}} #arena{{min-height:300px;display:grid;place-items:center}}
.choices{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;width:100%}} button{{border:1px solid #d7dfeb;background:#fff;border-radius:14px;padding:16px;cursor:pointer;color:var(--ink);font-weight:800;font-size:16px}} button:hover{{border-color:var(--violet);transform:translateY(-1px)}}
.primary{{background:linear-gradient(135deg,var(--violet),#8f65ff);color:#fff;border:0}} .outline{{width:min(360px,80vw);height:240px;filter:drop-shadow(0 10px 14px #4352a725)}}
.outline path{{fill:#6c4cff;stroke:#3d2baa;stroke-width:1.5}} .slider{{width:100%}} input[type=range]{{width:100%;accent-color:var(--violet)}}
#feedback{{min-height:46px;font-size:18px;font-weight:800;margin-top:16px}} .good{{color:var(--good)}} .bad{{color:var(--bad)}} footer{{text-align:center;color:var(--muted);margin-top:20px;font-size:13px}}
@media(max-width:600px){{.choices{{grid-template-columns:1fr}} header{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><div class="shell"><header><div class="brand"><b>02</b>GeoQuest</div><div class="stats"><span class="chip" id="round">1/{payload['rounds']}</span><span class="chip">★ <span id="score">0</span></span><span class="chip">♥ <span id="lives">3</span></span></div></header>
<main class="card"><div class="mode" id="mode"></div><h1 id="prompt"></h1><div id="arena"></div><div id="feedback"></div><button class="primary" id="next" hidden>Next challenge →</button></main><footer>{safe_title} · Built with 02GeoQuest · Works offline</footer></div>
<script>const G={_safe_json(payload)};
const T={{en:{{locate:'Map hunt',bigger:'Value duel',distance:'Distance guess',silhouette:'Silhouette',find:'Which place is this?',greater:'Which one has the greater value?',shape:'Whose silhouette is this?',correct:'Correct!',wrong:'Not this time.',next:'Next challenge →',done:'Quest complete!',again:'Play again'}},tr:{{locate:'Haritada bul',bigger:'Değer düellosu',distance:'Mesafe tahmini',silhouette:'Silüet',find:'Bu yer hangisi?',greater:'Hangisinin değeri daha büyük?',shape:'Bu silüet kimin?',correct:'Doğru!',wrong:'Bu kez olmadı.',next:'Sonraki soru →',done:'Macera tamamlandı!',again:'Tekrar oyna'}}}}[G.language]||null;
let score=0,lives=3,round=0,current=null; const $=id=>document.getElementById(id); const pick=a=>a[Math.floor(Math.random()*a.length)]; const esc=x=>String(x).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll("\\\"","&quot;").replaceAll("'","&#39;");
function sample(n,pool=G.records){{return [...pool].sort(()=>Math.random()-.5).slice(0,n)}} function label(r){{return String(r.label||('Feature '+r.fid))}}
function svg(outline){{if(!outline||outline.length<3)return '';let xs=outline.map(p=>p[0]),ys=outline.map(p=>p[1]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),w=maxx-minx||1,h=maxy-miny||1;let d=outline.map((p,i)=>`${{i?'L':'M'}} ${{20+(p[0]-minx)/w*320}} ${{220-(p[1]-miny)/h*200}}`).join(' ')+' Z';return `<svg class="outline" viewBox="0 0 360 240"><path d="${{d}}"/></svg>`}}
function choices(items,answer){{$('arena').innerHTML='<div class="choices">'+items.map(x=>`<button data-a="${{esc(x)}}">${{esc(x)}}</button>`).join('')+'</div>';$('arena').querySelectorAll('button').forEach(b=>b.onclick=()=>judge(b.dataset.a===String(answer),String(answer)))}}
function make(){{let mode=pick(G.modes),pool=G.records;if(mode==='silhouette')pool=pool.filter(r=>r.outline&&r.outline.length>2);if(mode==='silhouette'&&pool.length<4)mode='bigger';$('mode').textContent=T[mode];$('feedback').textContent='';$('next').hidden=true;
if(mode==='bigger'){{let [a,b]=sample(2);let av=Number(a.value??a.area??0),bv=Number(b.value??b.area??0);$('prompt').textContent=T.greater;choices([label(a),label(b)],av>=bv?label(a):label(b));}}
else if(mode==='silhouette'){{let opts=sample(4,pool),target=pick(opts);$('prompt').textContent=T.shape;$('arena').innerHTML=svg(target.outline)+'<div class="choices">'+opts.sort(()=>Math.random()-.5).map(r=>`<button data-a="${{esc(label(r))}}">${{esc(label(r))}}</button>`).join('')+'</div>';$('arena').querySelectorAll('button').forEach(b=>b.onclick=()=>judge(b.dataset.a===label(target),label(target)));}}
else if(mode==='distance'){{let [a,b]=sample(2),dx=a.centroid[0]-b.centroid[0],dy=a.centroid[1]-b.centroid[1],truth=Math.hypot(dx,dy)*111000,max=Math.max(1000,truth*2);current=truth;$('prompt').textContent=`${{label(a)}} → ${{label(b)}}`; $('arena').innerHTML=`<div class="slider"><h2 id="guess">${{Math.round(max/2/1000)}} km</h2><input id="range" type="range" min="0" max="${{Math.round(max)}}" value="${{Math.round(max/2)}}"><button class="primary" id="submit">OK</button></div>`;$('range').oninput=e=>$('guess').textContent=Math.round(e.target.value/1000)+' km';$('submit').onclick=()=>{{let ratio=Math.abs(Number($('range').value)-truth)/Math.max(1,truth);judge(ratio<=.25,Math.round(truth/1000)+' km')}};}}
else{{let opts=sample(Math.min(4,G.records.length)),target=pick(opts);$('prompt').textContent=T.find;choices(opts.map(label).sort(()=>Math.random()-.5),label(target));}}}}
function judge(ok,answer){{round++;if(ok)score+=500;else lives--;$('score').textContent=score;$('lives').textContent=lives;$('feedback').className=ok?'good':'bad';$('feedback').textContent=(ok?T.correct:T.wrong)+' '+answer;$('arena').querySelectorAll('button,input').forEach(x=>x.disabled=true);$('next').hidden=false;if(round>=G.rounds||lives<=0)finish();else $('next').onclick=()=>{{$('round').textContent=(round+1)+'/'+G.rounds;make()}}}}
function finish(){{$('next').hidden=false;$('next').textContent=T.again;$('next').onclick=()=>location.reload();$('feedback').textContent=T.done+' ★ '+score}} $('round').textContent='1/'+G.rounds;$('next').textContent=T.next;make();</script></body></html>"""


def write_html(path: str, title: str, records: list[dict], modes: list[str],
               rounds: int, language: str = "en") -> None:
    Path(path).write_text(build_html(title, records, modes, rounds, language), encoding="utf-8")
