#!/usr/bin/env python3
"""Optional local MLX TTS adapter; run using the project's configured Python."""
import argparse,hashlib,importlib.metadata,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio import load,selected,source,digest,file_hash,put,require

def main():
 ap=argparse.ArgumentParser();ap.add_argument('project',type=Path);ap.add_argument('--chapter',action='append');args=ap.parse_args();root=args.project.resolve();p=load(root);v=p.get('voice',{});require(v.get('model'),'voice.model is required');model_path=source(root,v['model']);require(model_path.is_dir(),'Local model missing; model download is a separate explicit setup step')
 mode=v.get('mode','design');require(mode in ['design','preset','clone'],'Supported adapters: design, preset and clone')
 if mode=='design':require(v.get('instruct'),'design voice needs instruct')
 elif mode=='preset':require(v.get('speaker'),'preset voice needs speaker')
 else:
  require(v.get('ref_audio') and v.get('ref_text'),'clone needs ref_audio and ref_text')
  ref=source(root,v['ref_audio']);require(ref.is_file(),'Reference audio missing; no fallback')
  require(file_hash(ref)==v.get('reference_sha256'),'Reference hash mismatch; no fallback')
  require(read_meta(model_path/'config.json').get('tts_model_type')=='base','Reference cloning requires a Base model')
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 import mlx.core as mx
 import numpy as np
 from mlx_audio.tts.utils import load_model
 from mlx_audio.audio_io import write
 mx.set_cache_limit(256*1024*1024)
 # Metadata signature tracks weight replacement; config hashes and package version track runtime changes.
 model_signature=digest({'files':[(str(x.relative_to(model_path)),x.stat().st_size,x.stat().st_mtime_ns) for x in sorted(model_path.rglob('*')) if x.is_file() and '.cache' not in x.parts],'config':file_hash(model_path/'config.json'),'mlx_audio':importlib.metadata.version('mlx-audio')})
 model=None
 for c in selected(p,args.chapter):
  for s in c['shots']:
   out=root/'audio'/c['id']/(s['id']+'.wav');meta=out.with_suffix('.json');key=digest({'text':s['narration'],'voice':v,'model_signature':model_signature})
   if out.exists() and meta.exists() and read_meta(meta).get('key')==key and read_meta(meta).get('audio_hash')==file_hash(out):print('AUDIO CACHED',c['id'],s['id'],flush=True)
   else:
    if model is None:model=load_model(str(model_path))
    mx.random.seed(v.get('seed',42));opts=dict(text=s['narration'],lang_code=v.get('language','Chinese'),temperature=v.get('temperature',.8),max_tokens=v.get('max_tokens',max(400,len(s['narration'])*15)),verbose=False)
    if mode=='design':opts['instruct']=v['instruct']
    elif mode=='preset':opts['voice']=v['speaker']
    else:opts.update(ref_audio=str(ref),ref_text=v['ref_text'])
    chunks=[]
    for r in model.generate(**opts):chunks.append(np.array(r.audio));sr=r.sample_rate
    require(chunks,'TTS produced no waveform');x=np.concatenate(chunks);require(len(x)/sr>.1,'TTS output is empty');require(np.isfinite(x).all(),'Nonfinite audio');peak=float(np.abs(x).max())
    if peak>.98:x=x*(.98/peak)
    out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_name(out.stem+'.tmp.wav');write(str(tmp),x,sr);tmp.replace(out)
    put(meta,{'key':key,'audio_hash':file_hash(out),'narration_hash':digest(s['narration']),'voice_hash':digest(v),'duration':len(x)/sr,'model_signature':model_signature,'identity_status':'style_reuse_not_identity_lock' if mode=='design' else ('reference_conditioned_pending_listening' if mode=='clone' else 'preset')})
    mx.clear_cache();print('AUDIO GENERATED',c['id'],s['id'],round(len(x)/sr,2),'seconds',flush=True)
   from audio_endings import inspect as inspect_ending
   quality=inspect_ending(out);put(out.with_suffix('.ending.json'),quality)
   if quality['signal_status']!='buffer_ok':print('ENDING REVIEW REQUIRED',c['id'],s['id'],quality['signal_status'],flush=True)
   s['audio']=str(out.relative_to(root));s['generated_audio']=True
 put(root/'project.json',p)
def read_meta(p):return json.loads(p.read_text())
if __name__=='__main__':
 try:main()
 except Exception as e:print('TTS ERROR:',e,file=sys.stderr);sys.exit(1)
