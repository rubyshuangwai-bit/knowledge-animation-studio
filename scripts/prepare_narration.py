#!/usr/bin/env python3
"""Prepare semantic pauses, captions and visual events from original speech timings."""
import argparse, array, copy, difflib, hashlib, json, math, re, sys, wave
from pathlib import Path
from studio import StudioError, require, read, put, file_hash, digest, source, load, selected, split_cues


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def normalize_factory(chinese=False):
    convert = lambda s: s
    if chinese:
        try:
            from opencc import OpenCC
        except ImportError as e:
            raise StudioError('Chinese normalization requires OpenCC in this Python environment; no dependency was installed') from e
        convert = OpenCC('t2s').convert
    return lambda s: ''.join(c.casefold() for c in convert(s) if c.isalnum())


def extract_mapping(narration, record, norm, duration):
    method = record.get('method')
    require(method in ('manual', 'asr', 'forced'), 'Timing method must be manual/asr/forced')
    rows = record.get('segments', record.get('cues', []))
    require(rows, 'No source timings')
    actual, times, warnings = '', [], []
    last = 0
    for row in rows:
        for w in row.get('words') or [row]:
            text = norm(w.get('word', w.get('text', '')))
            a, b = w.get('start'), w.get('end')
            require(finite(a) and finite(b) and last <= a <= b <= duration + .02, 'Invalid or overlapping source timings; inspect ASR before processing')
            last = b
            if not text:
                continue
            if b == a:
                warnings.append(dict(text=w.get('word',w.get('text','')),time=a,reason='zero_duration_ignored_for_matching'))
                continue
            actual += text
            times.extend((a + (b-a)*j/len(text), a + (b-a)*(j+1)/len(text)) for j in range(len(text)))
    expected, mapping = norm(narration), {}
    require(expected, 'Narration has no matchable characters')
    for block in difflib.SequenceMatcher(None, expected, actual, autojunk=False).get_matching_blocks():
        for j in range(block.size):
            mapping[block.a+j] = times[block.b+j]
    return mapping, len(mapping)/len(expected), actual, warnings


def process_shot(shot, raw, record, norm, max_chars=18, min_coverage=.85):
    with wave.open(str(raw), 'rb') as f:
        require(f.getnchannels() == 1 and f.getsampwidth() == 2 and f.getcomptype() == 'NONE', 'Source must be mono PCM16 WAV; convert an independent copy first')
        rate = f.getframerate()
        samples = array.array('h', f.readframes(f.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    duration = len(samples)/rate
    require(duration > 0, 'Empty source audio')
    require(record.get('audio_sha256') == file_hash(raw), 'Timings do not identify this source audio; supply audio_sha256 for the actual WAV')
    mapping, coverage, recognized, timing_warnings = extract_mapping(shot['narration'], record, norm, duration)
    require(coverage >= min_coverage, f'ASR/text match {coverage:.1%} below {min_coverage:.1%}; inspect recognition, normalization and audio separately')
    units = shot.get('visual', {}).get('units') or [{'text': shot['narration']}]
    require(norm(''.join(u['text'] for u in units)) == norm(shot['narration']), 'Semantic unit text must concatenate to narration')
    spans, ranges, offset = [], [], 0
    for u in units:
        n = len(norm(u['text']))
        hits = [mapping[j] for j in range(offset, offset+n) if j in mapping]
        require(n > 0 and len(hits)/n >= .6, 'A semantic unit is insufficiently matched; review its timings')
        a, b = hits[0][0], hits[-1][1]
        require(not spans or a >= spans[-1][1], 'Semantic event order is not monotonic')
        spans.append((a,b)); ranges.append((offset,offset+n)); offset += n
    pauses = shot.get('rhythm', {}).get('pauses', [])
    edits, cuts, used = [], [], set()
    window = max(1, round(.015*rate))
    for pause in pauses:
        i, target = pause.get('after'), pause.get('min_gap')
        require(isinstance(i,int) and 0 <= i < len(spans)-1 and i not in used, 'pause.after must uniquely identify a non-final semantic unit')
        require(finite(target) and 0 <= target <= 5, 'min_gap must be finite seconds between 0 and 5')
        used.add(i)
        end, nxt = spans[i][1], spans[i+1][0]
        natural = nxt-end; extra = max(0,target-natural)
        if extra > .02:
            # Search only this observed gap and a narrow uncertainty margin. Never cut voiced speech blindly.
            lo, hi = max(0,round((end-.04)*rate)), min(len(samples),round((nxt+.04)*rate))
            candidates = range(lo, max(lo+1,hi-window+1), max(1,round(.005*rate)))
            rms = lambda j: math.sqrt(sum(v*v for v in samples[j:j+window])/max(1,len(samples[j:j+window])))/32768
            pos = min(candidates, key=rms)
            require(rms(pos) <= .012, f'No quiet insertion point after unit {i}; inspect boundary or regenerate speech')
            pos += window//2
            cuts.append((pos,round(extra*rate)))
        else:
            pos = None
        edits.append(dict(after=i,natural_gap=natural,min_gap=target,added_seconds=extra if extra>.02 else 0,cut_sample=pos))
    cuts.sort()
    require(all(cuts[j][0] < cuts[j+1][0] for j in range(len(cuts)-1)), 'Pause cuts overlap')
    result, last = array.array('h'), 0
    for pos,n in cuts:
        result.extend(samples[last:pos]);result.extend(array.array('h',[0])*n);last=pos
    result.extend(samples[last:])
    def moved(t):
        return t + sum(n/rate for pos,n in cuts if pos/rate <= t)
    events = [dict(start=moved(a),end=moved(b)) for a,b in spans]
    cues=[]
    for u,(a,b),(first,stop) in zip(units,spans,ranges):
        cursor=first
        for text in split_cues(u['text'],max_chars):
            n=len(norm(text))
            if not n:
                if cues:cues[-1]['text']+=text
                continue
            hits=[mapping[j] for j in range(cursor,cursor+n) if j in mapping]
            start=hits[0][0] if hits else a+(b-a)*(cursor-first)/(stop-first)
            end=hits[-1][1] if hits else a+(b-a)*(cursor+n-first)/(stop-first)
            start=max(moved(start),cues[-1]['end'] if cues else 0);end=moved(end)
            require(end>start,'Unreliable caption boundary; inspect timings')
            cues.append(dict(text=text,start=start,end=end));cursor+=n
    key_events={}
    text=norm(shot['narration'])
    for phrase in shot.get('rhythm',{}).get('key_phrases',[]):
        needle=norm(phrase);at=text.find(needle)
        require(needle and at>=0 and text.find(needle,at+1)<0,'Key phrase must occur exactly once; use reviewed manual events for repeated phrases')
        hits=[mapping[j] for j in range(at,at+len(needle)) if j in mapping]
        require(hits,'Key phrase was not matched');key_events[phrase]=moved(hits[0][0])
    require(not shot.get('visual',{}).get('key_events') or key_events, 'Existing key_events require explicit rhythm.key_phrases; stale times cannot be reused')
    if sys.byteorder != 'little':result.byteswap()
    return result.tobytes(),rate,dict(method=record['method'],cues=cues,match_coverage=coverage,word_timing='interpolated',provenance='Matched source timings; missing characters interpolated; selective silence insertion; not an audio listening review'),events,key_events,dict(original_duration=duration,duration=len(result)/rate,changes=edits,coverage=coverage,recognized_text=recognized,timing_warnings=timing_warnings,speed_change=False,audio_status='pending')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('project',type=Path);ap.add_argument('--chapter',action='append');ap.add_argument('--timings',type=Path,help='Directory containing <chapter>/<shot>.json, each identifying original WAV hash')
    ap.add_argument('--model',help='Local faster-whisper model path; no downloads');ap.add_argument('--language',default='zh');ap.add_argument('--prompt',default='');ap.add_argument('--retry-asr',action='store_true',help='Re-recognize without prompt, using independent chunks; inspect before accepting')
    ap.add_argument('--normalize-chinese',action='store_true');ap.add_argument('--max-caption-chars',type=int,default=18);ap.add_argument('--min-coverage',type=float,default=.85);ap.add_argument('--apply',action='store_true')
    args=ap.parse_args();root=args.project.resolve();p=load(root);updated=read(root/'project.json');norm=normalize_factory(args.normalize_chinese)
    require(4<=args.max_caption_chars<=40 and .5<=args.min_coverage<=1,'Invalid caption length or coverage threshold')
    require(args.timings or args.model,'Provide source timings or an explicitly configured local ASR model')
    model=None
    if args.model:
        require(Path(args.model).is_dir(),'ASR model must be an existing local directory')
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:raise StudioError('faster-whisper is unavailable in this Python environment; no dependency was installed') from e
        model=WhisperModel(args.model,device='cpu',compute_type='int8',local_files_only=True)
    for c in selected(p,args.chapter):
        for shot in c['shots']:
            require(shot.get('raw_audio'),'Set raw_audio to immutable original speech; processed audio must never become the next input')
            raw=source(root,shot['raw_audio']);require(raw.is_file(),'Original speech is missing')
            out=root/'prepared'/c['id']/shot['id'];timing=(args.timings/c['id']/(shot['id']+'.json')) if args.timings else out/'recognition.json'
            if model:
                import dataclasses
                segments,_=model.transcribe(str(raw),language=args.language,word_timestamps=True,initial_prompt=None if args.retry_asr else (args.prompt or None),condition_on_previous_text=False,vad_filter=True,chunk_length=15,beam_size=3)
                record=dict(method='asr',audio_sha256=file_hash(raw),segments=[dataclasses.asdict(s) for s in segments])
                # Preserve independent retries rather than destroying diagnostic evidence.
                timing=out/('recognition.retry.json' if args.retry_asr else 'recognition.json');put(timing,record)
            else:record=read(timing)
            pcm,rate,alignment,events,keys,report=process_shot(shot,raw,record,norm,args.max_caption_chars,args.min_coverage)
            out.mkdir(parents=True,exist_ok=True);audio=out/'narration.wav'
            with wave.open(str(audio),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm)
            put(out/'alignment.json',alignment)
            report.update(alignment_sha256=file_hash(out/'alignment.json'),source_metadata_sha256=file_hash(raw.with_suffix('.json')) if raw.with_suffix('.json').is_file() else None,source_audio=str(raw),source_sha256=file_hash(raw),output_sha256=file_hash(audio),narration_hash=digest(shot['narration']),timings_sha256=file_hash(timing),settings=dict(rhythm=shot.get('rhythm',{}),max_caption_chars=args.max_caption_chars,min_coverage=args.min_coverage,normalize_chinese=args.normalize_chinese),processor_sha256=file_hash(Path(__file__)),events=events,key_events=keys)
            put(out/'processing.json',report)
            target=next(s for ch in updated['chapters'] if ch['id']==c['id'] for s in ch['shots'] if s['id']==shot['id'])
            target.update(audio=str(audio.relative_to(root)),generated_audio=False,alignment=str((out/'alignment.json').relative_to(root)),processing=str((out/'processing.json').relative_to(root)))
            target['visual']['events']=events
            if keys:target['visual']['key_events']=keys
            print('PREPARED',c['id'],shot['id'],round(report['duration'],2),flush=True)
    put(root/'prepared/project.json',updated)
    if args.apply:
        backup=root/'prepared/project.before-apply.json'
        require(not backup.exists(),'Apply backup already exists; inspect it before another apply')
        put(backup,read(root/'project.json'));put(root/'project.json',updated)
    print('Applied project configuration' if args.apply else 'Preview configuration: prepared/project.json; review before --apply')

if __name__=='__main__':
    try:main()
    except (StudioError,FileNotFoundError,KeyError,ValueError) as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
