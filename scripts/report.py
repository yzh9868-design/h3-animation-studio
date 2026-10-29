"""Render the authored film as an offline review package; record real consent.

No LLM, prompt rewriting, image synthesis, TTS, network or GPU calls.
"""
from pathlib import Path
import argparse, html, json, shutil
from urllib.parse import quote
from common import (load_film, settings, review_digest, ready_errors, read, save, sha, stamp, need, locate,
                    selected_segments, segment_digest, authorization_record, load_approval)

def esc(value):return html.escape(str(value if value is not None else ''))
def block(value):return '<p>'+esc(value).replace('\n','<br>')+'</p>'

CSS='''
:root{--ink:#203b3a;--muted:#647673;--paper:#f6f4ed;--line:#dce4de;--accent:#b85436}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1280px;margin:auto;padding:40px 28px 90px}header{padding:25px 0 32px;border-bottom:2px solid var(--ink)}h1{font-size:38px;line-height:1.25;margin:12px 0}h2{font-size:25px;margin:0 0 20px}h3{font-size:19px;margin:0 0 10px}p{white-space:normal;margin:8px 0}a{color:var(--accent)}.eyebrow,.muted{color:var(--muted)}.eyebrow{letter-spacing:.13em;font-size:12px}.pill{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:3px 12px;margin:6px 6px 0 0;font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:15px;margin:20px 0}section{scroll-margin-top:20px;background:white;border:1px solid var(--line);border-radius:16px;padding:28px;margin-top:25px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.assets{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}.card{border:1px solid var(--line);border-radius:10px;overflow:hidden;padding:16px}figure{margin:0}.card img{width:100%;max-height:320px;object-fit:contain;background:#f1f3ed;border-radius:7px}.card audio,.card video{width:100%;max-height:360px}figcaption{font-size:14px;color:var(--muted);margin-top:8px}.script{white-space:pre-wrap;line-height:1.95}.shot{padding:16px 0;border-bottom:1px solid var(--line)}.shot:last-child{border:0}.shot-title{font-weight:700}.dialogue{border-left:3px solid var(--accent);padding-left:15px;margin:13px 0}.prompt{background:#fafbf8;border:1px solid var(--line);border-radius:10px;padding:18px;min-width:0}.prompt h3{display:flex;align-items:center;justify-content:space-between}.prompt pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 ui-monospace,Consolas,monospace}button{cursor:pointer;background:var(--ink);color:white;border:0;border-radius:6px;padding:7px 13px;font:inherit;font-size:13px}.missing{padding:13px;background:#fff1e8;border-radius:7px;color:#8d3820}.notice{padding:15px;border-left:3px solid var(--accent);background:#fcf5ee}details{margin-top:18px;color:var(--muted)}summary{cursor:pointer}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}.voice{color:#5d492e;background:#fbf6ec;padding:10px;border-radius:6px}#toast{position:fixed;right:25px;bottom:25px;padding:10px 20px;background:var(--ink);color:white;border-radius:8px;display:none}footer{margin-top:28px;font-size:13px;color:var(--muted)}@media(max-width:800px){main{padding:20px 14px 50px}.grid{grid-template-columns:1fr}section{padding:19px}h1{font-size:29px}}@media print{body{background:white}nav,button,#toast{display:none}section{break-inside:auto}.grid{display:block}.prompt{margin:15px 0}}
'''
JS='''
const texts=JSON.parse(document.getElementById('prompt-data').textContent);
document.querySelectorAll('button[data-copy]').forEach(b=>b.addEventListener('click',async()=>{
 const text=texts[b.dataset.copy];let ok=false;
 try{if(navigator.clipboard){await navigator.clipboard.writeText(text);ok=true;}}catch(e){}
 if(!ok){const t=document.createElement('textarea');t.value=text;t.style.position='fixed';t.style.left='-10000px';document.body.appendChild(t);t.select();try{ok=document.execCommand('copy');}catch(e){}t.remove();}
 const toast=document.getElementById('toast');toast.textContent=ok?'已复制完整原文':'请手动选择下方完整原文复制';toast.style.display='block';setTimeout(()=>toast.style.display='none',2200);
}));
'''

def render(project):
    project=Path(project).resolve();film=load_film(project);out=project/'review';media=out/'assets';media.mkdir(parents=True,exist_ok=True)
    errors=ready_errors(project,film);digest=review_digest(project,film);payload={};asset_cards={};asset_records=[]
    for a in film.get('assets',[]):
        p=locate(project,a.get('path','__missing__'))
        caption=esc(a['id'])+' · '+esc(a.get('role',a.get('kind','素材')))
        if p.is_file():
            name=sha(p)[:16]+p.suffix.lower();dest=media/name
            if not dest.exists() or sha(dest)!=sha(p):shutil.copy2(p,dest)
            url='assets/'+quote(name)
            if a.get('kind')=='image':preview=f'<img src="{url}" alt="{caption}" loading="lazy">'
            elif a.get('kind')=='audio':preview=f'<audio controls preload="none" src="{url}"></audio>'
            elif a.get('kind')=='video':preview=f'<video controls preload="metadata" src="{url}"></video>'
            else:preview=f'<a href="{url}">打开素材</a>'
            asset_records.append(dict(id=a['id'],sha256=sha(p),report_path='assets/'+name))
        else:preview='<div class="missing">待生成/提供的素材；不是已有参考图</div>'
        extra='<details><summary>图片制作提示词</summary>'+block(a['prompt'])+'</details>' if a.get('prompt') else ''
        asset_cards[a['id']]=f'<figure class="card">{preview}<figcaption>{caption}</figcaption>{extra}</figure>'
    title=esc(film['title']);duration=sum(s['edit_seconds'] for s in film['segments'])
    parts=[f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · H3制作审阅</title><style>{CSS}</style><main>',
        f'<header><div class="eyebrow">H3 ANIMATION STUDIO · 创作审阅</div><h1>{title}</h1>{block(film.get("brief",""))}<span class="pill">{duration:g}秒剪辑计划</span><span class="pill">{len(film["segments"])}个生成单元</span><span class="pill">H3原生声画</span><span class="pill">'+('草稿 · 有待补齐项' if errors else '前期包完整 · 等待用户确认')+'</span></header>',
        '<nav><a href="#script">完整剧本</a><a href="#characters">角色与声音</a><a href="#assets">参考素材</a>'+''.join(f'<a href="#{esc(s["id"])}">{esc(s["id"])}</a>' for s in film['segments'])+'</nav>']
    if errors:parts.append('<div class="notice"><strong>本包尚不可确认执行</strong>'+''.join(block(e) for e in errors)+'</div>')
    parts.append('<section id="script"><h2>完整剧本</h2><div class="script">'+esc(film.get('script','尚未完成'))+'</div></section>')
    parts.append('<section id="characters"><h2>角色与声音设定</h2><div class="assets">')
    for c in film.get('characters',[]):
        parts.append(f'<article class="card"><h3>{esc(c.get("name",c["id"]))}</h3>{block(c.get("appearance",""))}')
        for key, label in [('personality','性格倾向'),('signature_actions','招牌动作'),('locomotion','移动方式'),('deformation','身体夸张范围')]:
            value = c.get(key)
            if isinstance(value, list): value = '；'.join(str(item) for item in value)
            if value: parts.append('<p><strong>'+label+'：</strong>'+esc(value)+'</p>')
        parts.append('<div class="voice">声线：'+esc(c.get('voice','尚未定义'))+'</div></article>')
    parts.append('</div><p class="muted">对白、口型与动作在H3同次生成；声线描述跨段复用。生成前这里展示声音设计，不冒充已生成音频。</p></section>')
    parts.append('<section id="assets"><h2>实际参考素材</h2><div class="assets">'+''.join(asset_cards.values())+'</div></section>')
    cursor=0
    for s in film['segments']:
        sid=s['id'];end=cursor+s['edit_seconds'];parts.append(f'<section id="{esc(sid)}"><div class="eyebrow">{esc(sid)} · 成片 {cursor:g}—{end:g} 秒</div><h2>{esc(s.get("title",s.get("purpose",sid)))}</h2>')
        for shot in s.get('shots',[]):
            parts.append('<article class="shot"><div class="shot-title">'+esc(shot.get('id','镜头'))+' · '+esc(shot.get('duration_seconds',''))+'秒</div>'+block(shot.get('action',''))+'<p class="muted">镜头：'+esc(shot.get('camera',''))+'</p>')
            for d in shot.get('dialogue',[]):parts.append('<div class="dialogue"><strong>'+esc(d.get('character_id',''))+'</strong>：'+esc(d.get('text',''))+'<br><span class="muted">'+esc(d.get('delivery',''))+'</span></div>')
            parts.append('</article>')
        if s.get('references'):
            parts.append('<h3>本单元参考顺序与用途</h3><div class="assets">')
            for ref in s['references']:parts.append('<div><strong>&lt;'+esc(ref['label'])+'&gt;</strong>'+asset_cards[ref['asset_id']]+'</div>')
            parts.append('</div>')
        if s.get('continuity_from'):parts.append('<p class="muted">连续参考：执行时从 '+esc(s['continuity_from'])+' 的实际剪出末帧取得下一Picture标签；此时尚无该实际画面。</p>')
        parts.append('<div class="grid">')
        for key,label in [('prompt_zh','中文声画执行稿'),('prompt_en','英文H3最终提示词')]:
            pid=sid+'_'+key;payload[pid]=s.get(key,'')
            parts.append(f'<article class="prompt"><h3>{label}<button data-copy="{esc(pid)}">复制全文</button></h3><pre>{esc(s.get(key,"尚未完成"))}</pre></article>')
        parts.append('</div><details><summary>生成参数</summary>'+block('模式：'+s.get('mode','Ref2VA')+'；编辑时长：'+str(s['edit_seconds'])+'秒；源帧数：'+str(s.get('source_frames','按所选工作流规划'))+'；原生声画')+'</details></section>');cursor=end
    parts.append('<footer>本页为创作审阅包。打开或复制本页不代表批准执行。确认后提交此处同一版本的英文和对应素材；生成结果由用户审查。</footer></main><div id="toast"></div>')
    data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    parts.append('<script type="application/json" id="prompt-data">'+data+'</script><script>'+JS+'</script></html>')
    target=out/'index.html';target.write_text('\n'.join(parts),encoding='utf8')
    manifest=dict(generated_at=stamp(),review_digest=digest,html_sha256=sha(target),html=str(target),ready=not errors,missing=errors,assets=asset_records,prompt_source='film.json unchanged; clipboard payload preserves exact authored strings')
    save(out/'review_manifest.json',manifest)
    return manifest

def approve(project,evidence,segments=None,repair=False):
    project=Path(project).resolve();f=load_film(project)
    need(isinstance(evidence,str) and evidence.strip(),'Record the actual user confirmation; do not invent consent')
    need(not repair or segments,'A repair request must name the authorized segment IDs')
    chosen=[s['id'] for s in selected_segments(f,segments.split(',') if segments else None)]
    errors=ready_errors(project,f,chosen if repair else None)
    need(not errors,'Not approvable: '+'; '.join(errors))
    old=None
    if (project/'approval.json').is_file():
        old=load_approval(project,f,allow_stale_legacy=True)
    need(not repair or old is not None,'Confirm the initial complete HTML package before using local repair')
    # Local repair records the user's explicit request and updates its presentation
    # in one command. It never asks for a second full-film creative approval.
    m=render(project) if repair else read(project/'review/review_manifest.json')
    if not repair: need(m.get('ready'),'Report is a draft')
    need(m['review_digest']==review_digest(project,f),'Report is stale: render it again before confirming')
    need(sha(project/'review/index.html')==m['html_sha256'],'Rendered report changed')
    records=dict(old.get('records',{})) if old else {}
    for sid in chosen:
        if not repair and sid in records and records[sid].get('segment_digest')==segment_digest(project,f,sid):
            continue
        records[sid]=authorization_record(project,f,sid,evidence,'repair' if repair else 'initial',m)
    a=dict(version=2,confirmed_at=stamp(),user_confirmation=evidence,segment_ids=list(records),records=records,
           review_digest=m['review_digest'],html_sha256=m['html_sha256'])
    a['initial_approval']=old.get('initial_approval',old) if repair else dict(user_confirmation=evidence,confirmed_at=a['confirmed_at'],review_digest=m['review_digest'],html_sha256=m['html_sha256'])
    if old and old.get('suspended_legacy_approval'):a['suspended_legacy_approval']=old['suspended_legacy_approval']
    save(project/'approval.json',a);return a

def repair(project,evidence,segments):
    return approve(project,evidence,segments,repair=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['render','approve','repair']);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--user-confirmation');parser.add_argument('--segments',help='Comma-separated authorized segments; required for repair, otherwise default whole report')
    args=parser.parse_args()
    result=render(args.project) if args.action=='render' else approve(args.project,args.user_confirmation,args.segments,repair=args.action=='repair')
    print(json.dumps(result,ensure_ascii=False,indent=2))
