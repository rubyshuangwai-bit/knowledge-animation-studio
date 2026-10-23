#!/usr/bin/env python3
"""Conservative end-of-speech audit. Signal checks do not establish word completeness."""
import argparse,array,json,math,sys,wave
from pathlib import Path
from studio import StudioError,file_hash,read,put,source

def require(ok,message):
    if not ok:raise ValueError(message)

POLICY='speech-end-v1'
def inspect(path):
    with wave.open(str(path),'rb') as w:
        require(w.getsampwidth()==2 and w.getcomptype()=='NONE','Ending audit requires PCM16 WAV; convert a separate copy first')
        rate=w.getframerate();channels=w.getnchannels();x=array.array('h',w.readframes(w.getnframes()))
    if sys.byteorder!='little':x.byteswap()
    require(len(x)>0,'Empty audio')
    # A loud channel must not be hidden by averaging opposing channels.
    mono=[max(abs(v) for v in x[i:i+channels])/32768 for i in range(0,len(x),channels)]
    width=max(1,round(.01*rate));rms=[math.sqrt(sum(v*v for v in mono[i:i+width])/len(mono[i:i+width])) for i in range(0,len(mono),width)]
    threshold=max(10**(-48/20),max(rms)*.03)
    active=[i for i,v in enumerate(rms) if v>threshold]
    duration=len(mono)/rate
    require(active,'No speech-like signal detected; do not certify silence as valid narration')
    last_end=min(len(mono),(active[-1]+1)*width)/rate;quiet=max(0,duration-last_end)
    edge=quiet<.08
    return dict(policy=POLICY,audio_sha256=file_hash(path),duration=duration,quiet_tail_seconds=quiet,threshold_rms=threshold,last_50ms_rms=math.sqrt(sum(v*v for v in mono[-max(1,round(.05*rate)):])/min(len(mono),max(1,round(.05*rate)))),signal_status='needs_end_review' if edge else ('short_buffer' if quiet<.35 else 'buffer_ok'),word_completeness='not_established',signal_only=True)

def validate_review(path,audio):
    review=read(path)
    require(review.get('audio_sha256')==file_hash(audio),'Ending listening review is stale')
    require(review.get('status')=='listened_complete' and bool(review.get('notes','').strip()),'Ending review must record actual listening and complete final words, with notes')
    return review

def check_buffer_provenance(audio):
    manifest=audio.with_suffix('.end.json')
    if not manifest.exists():return
    m=read(manifest);original=Path(m['source']);review=Path(m['review_path'])
    require(file_hash(audio)==m['output_sha256'] and file_hash(original)==m['source_sha256'],'Tail-buffer source/output changed')
    require(file_hash(review)==m['review_sha256'],'Tail-buffer listening review changed')
    validate_review(review,original)

def check_shot(root,shot):
    audio=source(root,shot['audio']);check_buffer_provenance(audio);result=inspect(audio)
    # When audio is derived, padding cannot erase an unresolved source warning.
    if shot.get('processing'):
        raw=source(root,shot['raw_audio']);check_buffer_provenance(raw);original=inspect(raw)
        if original['signal_status']=='needs_end_review':
            require(shot.get('source_end_review'),f"{shot['id']}: original speech reaches file edge; listen/regenerate before build, silence cannot recover words")
            validate_review(source(root,shot['source_end_review']),raw)
    if result['signal_status']=='needs_end_review':
        require(shot.get('audio_end_review'),f"{shot['id']}: suspected abrupt speech ending; inspect/regenerate, do not render first")
        validate_review(source(root,shot['audio_end_review']),audio)
    require(result['quiet_tail_seconds']>=.35,f"{shot['id']}: ending buffer under 0.35s; confirm complete speech then add a separately tracked tail buffer")
    return result

def pad(original,output,review_path,seconds=.45):
    require(original.resolve()!=output.resolve(),'Keep original audio immutable; output must be a separate file')
    require(not output.exists(),'Output exists; choose a new derivative rather than overwrite')
    result=inspect(original);review=validate_review(review_path,original)
    require(.35<=seconds<=2,'Target tail buffer must be 0.35–2 seconds')
    # Listening can establish that a naturally voiced final sound is complete; padding is still not a missing-word repair.
    extra=max(0,seconds-result['quiet_tail_seconds'])
    with wave.open(str(original),'rb') as w:params=w.getparams();pcm=w.readframes(w.getnframes())
    output.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(output),'wb') as w:w.setparams(params);w.writeframes(pcm+b'\x00'*(round(extra*params.framerate)*params.nchannels*2))
    put(output.with_suffix('.end.json'),dict(policy=POLICY,source=str(original.resolve()),source_sha256=file_hash(original),output_sha256=file_hash(output),review_path=str(review_path.resolve()),review_sha256=file_hash(review_path),added_seconds=extra,source_signal=result,speed_change=False,fade_applied=False,meaning='Buffer only; does not restore missing words'))
    return inspect(output)

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    a=sub.add_parser('audit');a.add_argument('project',type=Path);a.add_argument('--output',type=Path)
    b=sub.add_parser('pad');b.add_argument('audio',type=Path);b.add_argument('output',type=Path);b.add_argument('--review',type=Path,required=True);b.add_argument('--seconds',type=float,default=.45)
    args=ap.parse_args()
    if args.command=='pad':print(json.dumps(pad(args.audio,args.output,args.review,args.seconds),ensure_ascii=False));return
    root=args.project.resolve();p=read(root/'project.json');rows=[]
    for c in p['chapters']:
        for s in c['shots']:
            paths={'current':source(root,s['audio'])}
            if s.get('raw_audio'):paths['original']=source(root,s['raw_audio'])
            rows.append(dict(chapter=c['id'],shot=s['id'],audio={k:inspect(v) for k,v in paths.items()}))
    report=dict(policy=POLICY,shots=rows,meaning='Signal screening only; inspect final words and the picture transition by listening')
    if args.output:put(args.output,report)
    else:print(json.dumps(report,ensure_ascii=False,indent=2))
    if any(v['signal_status']!='buffer_ok' for row in rows for v in row['audio'].values()):sys.exit(2)

if __name__=='__main__':
    try:main()
    except (StudioError,FileNotFoundError,ValueError,wave.Error) as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
