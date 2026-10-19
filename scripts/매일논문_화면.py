"""매일논문/{날짜}/의 목록.json과 D*.md로 보기 화면 매일논문/보기.html을 만든다.

사용: python3 scripts/매일논문_화면.py
"""
import json, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "매일논문"

days = {}
for f in sorted(OUT.glob("*/목록.json"), reverse=True):
    papers = json.loads(f.read_text())
    for p in papers:
        md = f.parent / f"{p['id']}.md"
        p["summary"] = md.read_text() if md.exists() else ""
        if p["summary"]:
            p.pop("abstract", None)  # 요약이 없으면 초록을 그대로 보여 준다(LLM 없이 쓸 때)
    days[f.parent.name] = papers

# 바깥에서 온 글은 JSON으로만 넣고 화면에서 textContent로 그린다(HTML로 해석하지 않음)
data = json.dumps(days, ensure_ascii=False).replace("</", "<\\/")
html = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>매일 논문</title>
<style>
:root{
 --paper:#f5f0e6;--paper2:#ece5d6;--ink:#1c1a16;--ink2:#4a463d;--mute:#857e70;--rule:#1c1a16;--hair:#d6cdbb;
 --red:#9b2226;--ok:#3d6b45;
 --serif:"Iowan Old Style","Charter","Georgia","Noto Serif KR","AppleMyungjo","Nanum Myeongjo",serif;
 --sans:-apple-system,"Apple SD Gothic Neo","Helvetica Neue",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --paper:#17150f;--paper2:#201d16;--ink:#ece5d6;--ink2:#c4bcaa;--mute:#8d8574;--rule:#ece5d6;--hair:#3a352a;--red:#e2786b;--ok:#8fbf8f}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 var(--serif);-webkit-font-smoothing:antialiased}
main{max-width:980px;margin:0 auto;padding:28px 16px 64px}
a{color:inherit;text-decoration:none}a:hover{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.sans{font-family:var(--sans)}
/* 마스트헤드 */
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;font:600 11px/1 var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--ink2);padding-bottom:10px}
.nav{display:flex;align-items:center;gap:6px}
.nav button,.nav select{font:600 11px var(--sans);letter-spacing:.08em;color:var(--ink);background:transparent;border:1px solid var(--hair);border-radius:2px;padding:6px 9px;cursor:pointer}
.nav button:disabled{opacity:.3;cursor:default}
.mast{border-top:3px double var(--rule);border-bottom:1px solid var(--rule);text-align:center;padding:18px 0 14px}
.mast h1{margin:0;font-weight:700;font-size:clamp(40px,8vw,76px);line-height:1;letter-spacing:-.02em}
.mast .ko{display:block;margin-top:8px;font:500 13px var(--sans);letter-spacing:.5em;color:var(--ink2)}
.strip{display:flex;justify-content:center;flex-wrap:wrap;gap:6px 22px;border-bottom:3px double var(--rule);padding:9px 0;font:600 11px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--ink2)}
.strip b{color:var(--ink);font-weight:700}
.disc{margin:14px 0 0;text-align:center;font-style:italic;font-size:14px;color:var(--mute)}
/* 본문 */
.sec{margin-top:40px}
.kicker{display:flex;align-items:center;gap:12px;font:700 11px var(--sans);letter-spacing:.2em;text-transform:uppercase;color:var(--red);margin-bottom:14px}
.kicker::after{content:"";flex:1;border-top:1px solid var(--hair)}
.kicker .n{color:var(--mute);font-weight:600}
.feat{padding:0 0 26px;margin-bottom:26px;border-bottom:1px solid var(--hair)}
.feat:last-child{border-bottom:0;margin-bottom:0}
.feat h2{margin:0;font-size:clamp(23px,3.2vw,32px);line-height:1.18;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.dek{margin:10px 0 0;font-style:italic;font-size:19px;line-height:1.5;color:var(--ink2);max-width:44em}
.by{margin-top:12px;font:13px/1.5 var(--sans);color:var(--mute)}
.by .who{color:var(--ink);font-weight:600}
.tags{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 16px;font:600 11px var(--sans);letter-spacing:.1em;text-transform:uppercase}
.tags .ok{color:var(--ok)}.tags .bad{color:var(--red)}.tags a{color:var(--ink2);border-bottom:1px solid var(--hair)}
details{margin-top:14px}
summary{list-style:none;cursor:pointer;display:inline-block;font:600 11px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--ink);border-bottom:1px solid var(--ink);padding-bottom:2px}
summary::-webkit-details-marker{display:none}
details[open] summary{color:var(--red);border-color:var(--red)}
dl{margin:16px 0 0;padding:18px 22px;background:var(--paper2);border-left:3px solid var(--red);display:grid;grid-template-columns:max-content 1fr;gap:10px 20px;font-size:15.5px;line-height:1.6}
dt{font:700 11px/2 var(--sans);letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
dd{margin:0}
.note{font:600 11px var(--sans);letter-spacing:.1em;text-transform:uppercase;color:var(--mute);grid-column:1/-1}
/* 짧은 소식 */
.briefs{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:0 36px}
.brief{padding:14px 0;border-top:1px solid var(--hair)}
.brief h3{margin:0;font-size:18px;line-height:1.3;font-weight:600}
.brief .by{margin-top:6px}
.empty{text-align:center;padding:80px 0;font-style:italic;color:var(--mute)}
footer{margin-top:56px;border-top:3px double var(--rule);padding-top:12px;text-align:center;font:11px var(--sans);letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
@media (max-width:600px){dl{grid-template-columns:1fr;gap:2px;padding:14px 16px}dd{margin-bottom:10px}.top{flex-direction:column;align-items:flex-start}}
</style></head><body><main>
<div class="top"><span id="issue"></span><div class="nav">
 <button id="prev" aria-label="이전 날짜">‹ 이전</button><select id="day" aria-label="날짜 고르기"></select><button id="next" aria-label="다음 날짜">다음 ›</button></div></div>
<header class="mast"><h1>The Daily Paper</h1><span class="ko">매일 논문</span></header>
<div class="strip" id="strip"></div>
<p class="disc">초록 기준 후보입니다. 원문을 읽기 전에는 초안의 근거로 쓰지 않습니다.</p>
<div id="list"></div>
<footer>OpenAlex에서 수집 · 조테로에 저장 · paper-reader 요약</footer>
</main>
<script>
const DAYS=__DATA__, KEYS=Object.keys(DAYS);
const $=id=>document.getElementById(id);
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e};
const link=(href,txt,c)=>{const a=el('a',c,txt);a.href=href;a.target='_blank';a.rel='noopener';return a};
const WD=['일','월','화','수','목','금','토'];
const longDate=d=>{const x=new Date(d+'T00:00:00');return `${x.getFullYear()}년 ${x.getMonth()+1}월 ${x.getDate()}일 ${WD[x.getDay()]}요일`};
const authors=a=>!a||!a.length?'':a.length>3?a.slice(0,3).join(', ')+' 외':a.join(', ');
// 요약 md를 "라벨: 내용" 줄로 나눈다
function parse(md){const rows=[];let note='';
 md.split('\\n').forEach(l=>{l=l.trim();if(l.startsWith('※'))note=l.slice(1).trim();
  const m=l.match(/^- ([^:]+):\\s*(.*)$/);if(m)rows.push([m[1].trim(),m[2].replace(/\\s*\\(초록\\)/g,'').trim()])});
 return{rows,note}}
function dek(p){const r=parse(p.summary).rows.find(r=>r[0]==='결과');return r?r[1]:''}
function byline(p){const b=el('div','by');b.append(el('span','who',authors(p.authors)));
 const rest=[p.year,p.venue].filter(Boolean).join(' · ');if(rest)b.append(document.createTextNode(' — '+rest));return b}
function tags(p){const t=el('div','tags');
 t.append(el('span',p.zotero_saved?'ok':'bad',p.zotero_saved?'✓ 조테로 저장':'조테로 미저장'));
 if(p.oa_url)t.append(link(p.oa_url,'오픈 액세스 원문'));
 t.append(link(p.url,'DOI · 출처'));return t}
function feature(p){const a=el('article','feat'),h=el('h2');h.append(link(p.url,p.title));a.append(h);
 const d=dek(p);if(d)a.append(el('p','dek',d));a.append(byline(p),tags(p));
 const {rows,note}=parse(p.summary);const det=el('details'),s=el('summary',null,'요약 전문 읽기');const dl=el('dl');
 if(note)dl.append(el('div','note',note));rows.forEach(([k,v])=>dl.append(el('dt',null,k),el('dd',null,v)));
 det.append(s,dl);a.append(det);return a}
function brief(p){const a=el('article','brief'),h=el('h3');h.append(link(p.url,p.title));a.append(h,byline(p),tags(p));
 if(p.abstract){const det=el('details');det.append(el('summary',null,'초록 읽기'),el('p','dek',p.abstract));a.append(det)}return a}
function section(title,items,render,wrapCls){const s=el('section','sec'),k=el('div','kicker');
 k.append(el('span',null,title),el('span','n',items.length+'편'));s.append(k);
 const w=wrapCls?el('div',wrapCls):s;items.forEach(p=>w.append(render(p)));if(wrapCls)s.append(w);return s}
function show(d){const list=$('list');list.replaceChildren();$('strip').replaceChildren();
 if(!d){$('issue').textContent='No.000';list.append(el('p','empty','아직 수집한 논문이 없습니다.'));return}
 const i=KEYS.indexOf(d),P=DAYS[d];
 $('issue').textContent=`No.${String(KEYS.length-i).padStart(3,'0')} · ${longDate(d)}`;
 $('prev').disabled=i>=KEYS.length-1;$('next').disabled=i<=0;
 const st=[['수집',P.length],['요약',P.filter(p=>p.summary).length],['조테로',P.filter(p=>p.zotero_saved).length],['오픈 액세스',P.filter(p=>p.oa_url).length]];
 st.forEach(([k,v])=>{const s=el('span',null,k+' ');s.append(el('b',null,v));$('strip').append(s)});
 const feats=P.filter(p=>p.summary),rest=P.filter(p=>!p.summary);
 const byKw={};feats.forEach(p=>(byKw[p.keyword]=byKw[p.keyword]||[]).push(p));
 Object.entries(byKw).forEach(([k,ps])=>list.append(section(k,ps,feature)));
 if(rest.length)list.append(section('함께 들어온 논문',rest,brief,'briefs'))}
KEYS.forEach(d=>$('day').append(new Option(d,d)));
$('day').onchange=e=>show(e.target.value);
const go=s=>{const i=KEYS.indexOf($('day').value)+s;if(KEYS[i]){$('day').value=KEYS[i];show(KEYS[i])}};
$('prev').onclick=()=>go(1);$('next').onclick=()=>go(-1);
show(KEYS[0]);
</script></body></html>
""".replace("__DATA__", data)
(OUT / "보기.html").write_text(html)
print(f"화면 갱신: {OUT / '보기.html'}")
