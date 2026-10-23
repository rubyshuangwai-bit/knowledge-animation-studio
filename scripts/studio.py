#!/usr/bin/env python3
"""Portable knowledge-animation project builder, renderer, verifier and merger."""
import argparse, concurrent.futures, hashlib, html, json, math, re, shutil, subprocess, sys, wave
from pathlib import Path
from storage_cleanup import cleanup_render_chunks
SKILL=Path(__file__).resolve().parent.parent
VENDOR=SKILL/'scripts/vendor'
class StudioError(Exception): pass
def require(ok,msg):
    if not ok: raise StudioError(msg)
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def put(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def run(args,log=None):
    if log:
        with Path(log).open('w') as f:r=subprocess.run([str(a) for a in args],stdout=f,stderr=subprocess.STDOUT)
        require(r.returncode==0,f'Command failed; inspect {log}')
    else:subprocess.run([str(a) for a in args],check=True)
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
def source(root,p):
    p=Path(p);return p if p.is_absolute() else root/p
def valid_id(s):return isinstance(s,str) and bool(re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',s))
def custom_source(root,c):
    path=c.get('custom_script','custom.js')
    require(isinstance(path,str) and path,'custom_script must be a source file path')
    return source(root,path)
def validate_semantics(s,duration=None):
    v=s.get('visual',{});units=v.get('units');events=v.get('events')
    if units is not None:
        require(isinstance(units,list) and units,'visual.units must be a nonempty list')
        for u in units:require(all(isinstance(u.get(k),str) and u[k].strip() for k in ['text','target','action']),'Semantic units need text, target, action')
        norm=lambda t:''.join(c.casefold() for c in t if c.isalnum())
        require(norm(''.join(u['text'] for u in units))==norm(s['narration']),'Semantic unit text differs from narration')
    if events is not None:
        require(units and len(events)==len(units),'Semantic events must match units one-to-one')
        prev=0
        for e in events:
            a,b=e.get('start'),e.get('end')
            require(all(isinstance(x,(int,float)) and math.isfinite(x) for x in [a,b]) and prev<=a<b,'Invalid semantic event times')
            if duration is not None:require(b<=duration+.02,'Semantic event exceeds speech duration')
            prev=b
    for t in v.get('key_events',{}).values():
        require(isinstance(t,(int,float)) and math.isfinite(t) and t>=0 and (duration is None or t<=duration+.02),'Invalid key event time')
def check_processing(root,s,voice):
    if not s.get('processing'):return
    record=read(source(root,s['processing']));raw=source(root,s['raw_audio'])
    require(file_hash(raw)==record.get('source_sha256') and file_hash(source(root,s['audio']))==record.get('output_sha256'),'Processed speech input/output changed; prepare narration again')
    require(file_hash(source(root,s['alignment']))==record.get('alignment_sha256'),'Processed alignment changed; prepare narration again')
    meta=raw.with_suffix('.json')
    require((file_hash(meta) if meta.exists() else None)==record.get('source_metadata_sha256'),'Original speech provenance changed; inspect and prepare again')
    if meta.exists():
        m=read(meta)
        if 'voice_hash' in m:require(m['voice_hash']==digest(voice) and m.get('narration_hash')==digest(s['narration']),'Original generated speech no longer matches voice/narration')
    require(digest(s['narration'])==record.get('narration_hash') and s.get('rhythm',{})==record.get('settings',{}).get('rhythm'),'Processed narration/rhythm is stale')
    require(s.get('visual',{}).get('events')==record.get('events') and s.get('visual',{}).get('key_events',{})==record.get('key_events',{}),'Processed visual events are stale')
def load(root):
    p=read(root/'project.json');require(p.get('version')==1,'project.version must be 1')
    require(p.get('title'),'project.title is required')
    require(p.get('chapters'),'At least one chapter is required')
    require(p.get('fps',30)==30,'Bundled renderer currently supports 30fps projects')
    if p.get('voice',{}).get('mode')=='clone':
        v=p['voice'];ref=source(root,v['ref_audio']);require(ref.is_file() and file_hash(ref)==v.get('reference_sha256'),'Clone reference changed or missing: restore approved sample')
    known={x['id'] for x in p.get('sources',[])};ids=set()
    for c in p['chapters']:
        require(valid_id(c.get('id')) and c['id'] not in ids,'Chapter ids must be unique, ASCII, path-safe identifiers');ids.add(c['id']);require(c.get('title') and c.get('shots'),'Chapter title and shots are required');shots=set()
        for s in c['shots']:
            require(valid_id(s.get('id')) and s['id'] not in shots,'Shot ids must be unique within a chapter');shots.add(s['id'])
            require(bool(s.get('narration','').strip()),'Every shot needs narration')
            require(bool(s.get('explain','').strip()),'Each shot needs a concrete learning objective in explain')
            require(bool(s.get('change','').strip()),'Each shot needs a meaningful visual change, beyond camera motion')
            require(s.get('claim_type') in ['factual','illustrative'],'Set claim_type to factual or illustrative')
            refs=s.get('source_ids',[]);require(all(x in known for x in refs),'Unknown source id')
            require(s['claim_type']!='factual' or refs,'Factual shots need checked source_ids')
            validate_semantics(s)
            v=s.get('visual',{});require(v.get('kind') in ['flow','comparison','bars','matrix','layers','attention','custom'],'Unsupported visual.kind')
            if v['kind']=='custom':require(custom_source(root,c).is_file(),'custom visual requires chapter.custom_script or project/custom.js')
            elif v['kind']=='bars':
                vals=v.get('values',[]);require(1<=len(vals)<=6 and all(isinstance(x,(int,float)) and math.isfinite(x) and x>=0 for x in vals),'bars need 1–6 nonnegative finite values');require(len(v.get('labels',[]))==len(vals),'bar labels must match values')
            elif v['kind']=='matrix':
                a=v.get('values',[]);require(1<=len(a)<=4 and all(isinstance(r,list) and 1<=len(r)<=4 for r in a) and len({len(r) for r in a})==1,'matrix needs a rectangular array, at most 4×4')
            elif v['kind']=='comparison':
                require(len(v.get('groups',[]))==2,'comparison needs two groups');require(all(g.get('title') and len(g.get('items',[]))<=3 for g in v['groups']),'comparison groups need titles and at most 3 short items')
            else:
                require(2<=len(v.get('labels',[]))<=6,'flow/layers/attention need 2–6 labels')
                if v['kind']=='attention' and 'weights' in v:require(len(v['weights'])==len(v['labels'])-1 and all(isinstance(x,(int,float)) and math.isfinite(x) and x>=0 for x in v['weights']),'attention.weights must match candidate labels and be finite/nonnegative')
    voice=p.get('voice',{})
    if not voice or voice.get('profile')=='approved-male-v1':
        profile=read(SKILL/'assets/voices/approved-male.json')
        ref=SKILL/'assets/voices'/profile['ref_audio']
        require(ref.is_file() and file_hash(ref)==profile['reference_sha256'],'Approved male reference missing or changed; do not fall back to voice design')
        local=SKILL.parent/'运行环境/tts.json'
        settings=read(local) if local.exists() else {}
        profile['ref_audio']=str(ref)
        p['voice']={**profile,**settings,**voice,'profile':'approved-male-v1'}
        require(p['voice']['mode']=='clone','Approved male profile requires clone mode')
    return p
def selected(p,ids):
    if not ids:return p['chapters']
    known={c['id'] for c in p['chapters']};require(set(ids)<=known,'Unknown chapter id');return [c for c in p['chapters'] if c['id'] in ids]
def chapter_dir(root,c):return root/'chapters'/c['id']
def build_key(p,c):
    return digest({'chapter':c,'highlights':p.get('highlights',[]),'emphasis':p.get('emphasis',[]),'voice':p.get('voice',{}),'fps':p.get('fps',30),'assets':{x:file_hash(SKILL/'assets'/x) for x in ['handdraw.html','scenes.js']},'build_tools':{x:file_hash(VENDOR/x) for x in ['生成timeline.mjs','动效部件.js']},'builder':file_hash(Path(__file__))})
def timecode(t):
    m=round(t*1000);return f'{m//3600000:02}:{m//60000%60:02}:{m//1000%60:02},{m%1000:03}'
def srt(cues):return '\n\n'.join(f"{i+1}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}" for i,c in enumerate(cues))+'\n'
def split_cues(text,limit=18):
    pieces=[]
    for part in re.findall(r'[^，。；：！？!?]+[，。；：！？!?]?',text):
        while len(part)>limit:pieces.append(part[:limit]);part=part[limit:]
        if part:pieces.append(part)
    return pieces or [text]
def build(root,p,c):
    d=chapter_dir(root,c);d.mkdir(parents=True,exist_ok=True);work=d/'audio';work.mkdir(exist_ok=True)
    cues=[];chars=[];shots=[];visuals=[];raw=[];t=0;alignment=[]
    for s in c['shots']:
        require(s.get('audio'),f"Missing audio for {c['id']}/{s['id']}; supply it or run tts")
        inp=source(root,s['audio']);require(inp.is_file(),f'Missing audio: {inp}')
        check_processing(root,s,p.get('voice',{}))
        from audio_endings import check_shot
        check_shot(root,s)
        meta=inp.with_suffix('.json')
        if s.get('generated_audio'):
            require(meta.exists(),'Generated audio provenance is missing')
            m=read(meta);require(m.get('narration_hash')==digest(s['narration']) and m.get('voice_hash')==digest(p.get('voice',{})),'Generated audio is stale: run tts after narration or voice changes')
        out=work/(s['id']+'.wav');run(['ffmpeg','-v','error','-y','-i',inp,'-ar','24000','-ac','1','-c:a','pcm_s16le',out])
        with wave.open(str(out),'rb') as w:x=w.readframes(w.getnframes());duration=w.getnframes()/24000
        require(duration>0,'Empty audio')
        validate_semantics(s,duration)
        pause=.12;raw.append(x+b'\x00\x00'*round(pause*24000));end=t+duration+pause
        if s.get('alignment'):
            a=read(source(root,s['alignment']));require(a.get('method') in ['manual','asr','forced'],'alignment.method must be manual/asr/forced')
            units=a.get('cues',[]);require(units,'Alignment has no cues');norm=lambda z:re.sub(r'\W','',z,flags=re.UNICODE).casefold()
            require(norm(''.join(u['text'] for u in units))==norm(s['narration']),'Alignment text differs from narration')
            prev=0
            for u in units:
                require(prev<=u['start']<u['end']<=duration+.02,'Invalid alignment times');prev=u['end']
            method=a['method']
        else:
            pieces=split_cues(s['narration']);total=sum(map(len,pieces));off=0;units=[]
            for piece in pieces:
                units.append({'text':piece,'start':duration*off/total,'end':duration*(off+len(piece))/total});off+=len(piece)
            method='estimated'
        cue_ids=[]
        for j,u in enumerate(units):
            cid=len(cues)+1;cue_ids.append(cid);start=t+u['start'];finish=t+u['end'];hide=t+(units[j+1]['start'] if j+1<len(units) else duration+pause)
            cues.append(dict(id=cid,text=u['text'],start=start,end=finish,show=start,hide=hide))
            for k,ch in enumerate(u['text']):chars.append(dict(text=ch,start=start+(finish-start)*k/len(u['text']),end=start+(finish-start)*(k+1)/len(u['text']),cue=cid))
        shots.append(dict(id=len(shots)+1,start=t,end=end,title=s.get('title',s['explain']),cues=cue_ids));visuals.append(s['visual']);alignment.append({'shot':s['id'],'method':method,'word_timing':'estimated'});t=end
    t=math.ceil(t*30-1e-8)/30;audio=b''.join(raw);audio+=b'\x00\x00'*max(0,round(t*24000)-len(audio)//2)
    with wave.open(str(d/'口播.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(audio)
    shots[-1]['end']=t;cues[-1]['hide']=t
    put(d/'字幕.json',dict(duration=t,cues=cues,chars=chars));put(d/'分镜.json',dict(duration=t,标题=c['title'],高亮=p.get('highlights',[]),字幕强调=p.get('emphasis',[]),shots=shots,素材={'visuals':visuals,'chapter':c['id']}))
    put(d/'作品.json',dict(audio='口播.wav',subtitles='字幕.json',storyboard='分镜.json',timeline='timeline.js',page='index.html',output=c['id']+'.mp4',format='jpeg'))
    (d/'字幕.srt').write_text(srt(cues));(d/'稿子.txt').write_text('\n'.join(s['narration'] for s in c['shots']))
    template=(SKILL/'assets/handdraw.html').read_text().replace('/* STUDIO_SCENES */',(SKILL/'assets/scenes.js').read_text())
    template=template.replace('<title>手绘笔记 · 通用模板</title>','<title>'+html.escape(c['title'])+'</title>')
    template=template.replace('<script src="timeline.js"></script>','<script src="timeline.js"></script>\n<script src="custom.js"></script>')
    (d/'index.html').write_text(template);(d/'custom.js').write_text(custom_source(root,c).read_text() if custom_source(root,c).exists() else '// no custom scene\n')
    shutil.copy2(VENDOR/'动效部件.js',d/'动效部件.js');run(['node',VENDOR/'生成timeline.mjs',d],d/'build.log')
    put(d/'build.json',{'key':build_key(p,c),'duration':t,'alignment':alignment,'audio_inputs':{s['id']:file_hash(source(root,s['audio'])) for s in c['shots']},'alignment_inputs':{s['id']:file_hash(source(root,s['alignment'])) for s in c['shots'] if s.get('alignment')},'custom':file_hash(custom_source(root,c)) if custom_source(root,c).exists() else None});print('BUILT',c['id'],round(t,2),'seconds',flush=True)
def check_build(root,p,c):
    d=chapter_dir(root,c);require((d/'build.json').exists(),'Run build first');b=read(d/'build.json')
    require(b['key']==build_key(p,c),'Project or template changed: rebuild this chapter')
    from audio_endings import check_shot
    for s in c['shots']:
        check_processing(root,s,p.get('voice',{}))
        check_shot(root,s)
    require(all(file_hash(source(root,s['audio']))==b['audio_inputs'].get(s['id']) for s in c['shots']),'Audio changed: rebuild')
    require(all(file_hash(source(root,s['alignment']))==b.get('alignment_inputs',{}).get(s['id']) for s in c['shots'] if s.get('alignment')),'Alignment changed: rebuild')
    require(b.get('custom')==(file_hash(custom_source(root,c)) if custom_source(root,c).exists() else None),'Custom scene changed: rebuild');return d
def preflight(root,p,c):
    d=check_build(root,p,c);times=[];offset=0;count=0
    for s in c['shots']:
        with wave.open(str(d/'audio'/(s['id']+'.wav')),'rb') as w:duration=w.getnframes()/w.getframerate()
        events=s.get('visual',{}).get('events')
        require(not s.get('visual',{}).get('units') or events,'Semantic units have no audio events; align before preflight')
        events=events or [dict(start=0,end=duration)]
        for e in events:
            times.append(offset+(e['start']+e['end'])/2);count+=1
        offset+=duration+.12
    out=d/'preflight';out.mkdir(exist_ok=True)
    run(['node',VENDOR/'render.mjs',d/'index.html','--stills',','.join(f'{x:.3f}' for x in times),'--outdir',out],d/'preflight.log')
    put(out/'manifest.json',dict(render_key=render_key(d),semantic_stages=count,times=times,status='captured_pending_visual_review'))
    print('PREFLIGHT',c['id'],count,'stages; inspect images',flush=True)

def render_key(d):
    return digest({**{f:file_hash(d/f) for f in ['index.html','custom.js','timeline.js','动效部件.js','口播.wav','作品.json']},'renderer':file_hash(VENDOR/'render.mjs')})
def render(root,p,c):
    d=check_build(root,p,c);key=render_key(d);mp4=d/(c['id']+'.mp4');state=d/'render.json'
    if state.exists() and mp4.exists() and read(state).get('key')==key and read(state).get('video_hash')==file_hash(mp4):print('CACHED',c['id'],flush=True);return
    run(['node',VENDOR/'render.mjs',d/'index.html'],d/'render.log');require(mp4.exists(),'Renderer did not produce a video');put(state,{'key':key,'video_hash':file_hash(mp4)});print('RENDERED',c['id'],flush=True)
def current(root,p,c):
    d=check_build(root,p,c);mp4=d/(c['id']+'.mp4');require((d/'render.json').exists() and mp4.exists(),'Render this chapter first');r=read(d/'render.json');require(r['key']==render_key(d) and r['video_hash']==file_hash(mp4),'Render is stale');return d,mp4,r

def verify(root,p,c):
    d,mp4,r=current(root,p,c);info=probe(mp4);v=next(x for x in info['streams'] if x['codec_type']=='video');a=next((x for x in info['streams'] if x['codec_type']=='audio'),None)
    require(v['width']==1920 and v['height']==1080 and v['r_frame_rate']=='30/1' and a,'Unexpected output streams')
    require(abs(float(v['duration'])-read(d/'build.json')['duration'])<=1/30+.001,'Video duration differs from timeline')
    run(['node',VENDOR/'render.mjs',d/'index.html','--check-determinism','auto'],d/'determinism.log')
    run(['node',VENDOR/'render.mjs',d/'index.html','--scan'],d/'scan.log')
    run(['node',VENDOR/'丰富度检查.mjs',mp4],d/'motion.log')
    run(['ffmpeg','-v','error','-i',mp4,'-f','null','-'],d/'decode.log')
    motion=(d/'motion.log').read_text();warnings=[]
    if '判定：不过' in motion:warnings.append('Low pixel-change score; inspect whether a meaningful hold or a missing explanation, rather than adding decorative movement to raise the score.')
    alignment=read(d/'build.json')['alignment']
    if any(x['method']=='estimated' for x in alignment):warnings.append('Caption boundaries within shots are estimated; no ASR/forced-alignment accuracy claim.')
    put(d/'verify.json',{'video_hash':r['video_hash'],'render_key':r['key'],'technical_pass':True,'warnings':warnings,'alignment':alignment,'checker_hashes':{x:file_hash(VENDOR/x) for x in ['render.mjs','丰富度检查.mjs']}});print('VERIFIED',c['id'],'warnings:',len(warnings),flush=True)
def valid_verify(d,r):
    require((d/'verify.json').exists(),'Run verify first');v=read(d/'verify.json');require(v.get('technical_pass') and v.get('video_hash')==r['video_hash'] and v.get('render_key')==r['key'],'Verification is stale');require(v.get('checker_hashes')=={x:file_hash(VENDOR/x) for x in ['render.mjs','丰富度检查.mjs']},'Verification tools changed: rerun verify');return v

def merge(root,p):
    paths=[];audio=[];merged_cues=[];chapters=[];offset=0
    for c in p['chapters']:
        d,mp4,r=current(root,p,c);valid_verify(d,r)
        require((d/'review.json').exists(),'Visual/semantic review is required before delivery/merge')
        review=read(d/'review.json');require(review.get('video_hash')==r['video_hash'] and review.get('pass'),'Visual review is stale or failed')
        duration=float(next(x for x in probe(mp4)['streams'] if x['codec_type']=='video')['duration'])
        with wave.open(str(d/'口播.wav'),'rb') as w:pcm=w.readframes(w.getnframes())
        size=round(duration*24000)*2;audio.append(pcm[:size]+b'\x00'*max(0,size-len(pcm)))
        for q in read(d/'字幕.json')['cues']:merged_cues.append(dict(text=q['text'],start=q['start']+offset,end=q['end']+offset))
        chapters.append({'id':c['id'],'title':c['title'],'start':offset,'end':offset+duration});offset+=duration;paths.append(mp4)
    out=root/'delivery';out.mkdir(exist_ok=True)
    with wave.open(str(out/'narration.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b''.join(audio))
    # Paths go into the concat file, never through a shell.
    esc=lambda s:str(s).replace("'", "'\\''")
    (out/'concat.txt').write_text(''.join("file '"+esc(x)+"'\n" for x in paths))
    escape_meta=lambda s:str(s).replace('\\','\\\\').replace('=','\\=').replace(';','\\;').replace('#','\\#').replace('\n',' ')
    meta=';FFMETADATA1\ntitle='+escape_meta(p['title'])+'\n'
    for x in chapters:meta+=f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(x['start']*1000)}\nEND={round(x['end']*1000)}\ntitle={escape_meta(x['title'])}\n"
    (out/'chapters.ffmeta').write_text(meta);temp=out/'complete.rendering.mp4'
    run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',out/'concat.txt','-i',out/'narration.wav','-i',out/'chapters.ffmeta','-map','0:v:0','-map','1:a:0','-map_metadata','2','-map_chapters','2','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(offset),'-movflags','+faststart',temp],out/'merge.log')
    run(['ffmpeg','-v','error','-i',temp,'-f','null','-'],out/'decode.log');temp.replace(out/'complete.mp4');(out/'complete.srt').write_text(srt(merged_cues));put(out/'delivery.json',{'title':p['title'],'chapters':chapters,'timeline_duration':offset,'video_hash':file_hash(out/'complete.mp4'),'alignment_warnings':[read(chapter_dir(root,c)/'verify.json')['warnings'] for c in p['chapters']],'audio_review_status':{c['id']:read(chapter_dir(root,c)/'review.json').get('audio_status','pending') for c in p['chapters']},'status':'ready' if all(read(chapter_dir(root,c)/'review.json').get('audio_status','pending')!='pending' for c in p['chapters']) else 'preview_pending_audio_review'});print('DELIVERED',out/'complete.mp4',flush=True)
    for c in p['chapters']:
        cleanup_render_chunks(root,c['id'])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['validate','build','tts','render','verify','review','merge','status','doctor','preflight']);ap.add_argument('project',type=Path);ap.add_argument('--chapter',action='append');ap.add_argument('--jobs',type=int,default=1);ap.add_argument('--notes');ap.add_argument('--audio-status',choices=['pending','listened','user-confirmed'],default='pending');ap.add_argument('--evidence',action='append',default=[]);args=ap.parse_args();root=args.project.resolve();p=load(root);cs=selected(p,args.chapter)
    if args.command=='validate':print('VALID',len(p['chapters']),'chapters',sum(len(c['shots']) for c in p['chapters']),'shots');return
    if args.command=='doctor':
        for cmd in ['python3','node','ffmpeg','ffprobe']:
            require(shutil.which(cmd),f'Missing runtime: {cmd}');print(cmd,shutil.which(cmd))
        run(['node','--input-type=module','-e',"if(typeof WebSocket==='undefined')throw Error('Node 22+ required'); const m=await import(process.argv[1]);const c=m.findChrome();if(!c)throw Error('Chrome missing');console.log('Chrome:',c)",(VENDOR/'render.mjs').as_uri()]);return
    if args.command=='tts':
        voice=p.get('voice',{});require(voice.get('python'),'Configure voice.python or provide audio directly');cmd=[voice['python'],SKILL/'scripts/synthesize.py',root]
        for c in args.chapter or []:cmd+=['--chapter',c]
        run(cmd);return
    if args.command=='merge':merge(root,p);return
    if args.command=='render':
        require(1<=args.jobs<=4,'jobs must be 1–4')
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:list(pool.map(lambda c:render(root,p,c),cs))
        return
    for c in cs:
        if args.command=='build':build(root,p,c)
        elif args.command=='preflight':preflight(root,p,c)
        elif args.command=='verify':verify(root,p,c)
        elif args.command=='review':
            d,mp4,r=current(root,p,c);valid_verify(d,r);require(args.notes and args.evidence,'Review requires notes and inspected image evidence paths');paths=[source(root,x) for x in args.evidence];require(all(x.is_file() for x in paths),'Review evidence is missing');put(d/'review.json',{'pass':True,'video_hash':r['video_hash'],'notes':args.notes,'audio_status':args.audio_status,'evidence':[{'path':str(x),'hash':file_hash(x)} for x in paths]});print('REVIEWED',c['id'])
        elif args.command=='status':
            try:current(root,p,c);print(c['id'],'current')
            except (StudioError,FileNotFoundError) as e:print(c['id'],'STALE:',str(e))
if __name__=='__main__':
    try:main()
    except (StudioError,subprocess.CalledProcessError,KeyError,ValueError) as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
