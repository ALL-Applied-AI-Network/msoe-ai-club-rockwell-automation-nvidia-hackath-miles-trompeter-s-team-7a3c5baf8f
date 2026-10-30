"""Appearance measurements and retrospective transition analysis; no quality labels."""
from functools import lru_cache
import json
from pathlib import Path
import cv2
import numpy as np
from hybrid import decode, encode, measure

ROOT=Path(__file__).resolve().parent
VERSION='appearance-v2'

@lru_cache(maxsize=1)
def detector():
    from ultralytics import YOLO
    paths=list((ROOT/'models/jar_crop/runs').glob('train*/weights/best.pt'))
    if not paths: raise ValueError('No vial detector available')
    return YOLO(str(max(paths,key=lambda p:p.stat().st_mtime)))

def prepare(record, history=()):
    """Only frames at or before this crop, and already observed comparison vials."""
    try:
        labs=[]; samples=[]
        timestamp=record['seconds']
        if record.get('source_video')!='vial_fill_video_5.mp4':
            raise ValueError('Multi-frame measurement currently supports video 5 only')
        cap=cv2.VideoCapture(str(ROOT/'content/vial_fill_video_5.mp4'))
        try:
            for seconds in (timestamp-1,timestamp-.5,timestamp):
                if seconds<record['recipe']['start_s']: continue
                cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000)
                ok,frame=cap.read()
                if not ok: continue
                boxes=detector().predict(frame,conf=.45,device='cpu',verbose=False)[0].boxes.xyxyn.cpu().tolist()
                boxes=[b for b in boxes if .46<=(b[0]+b[2])/2<=.51]
                if not boxes: continue
                b=min(boxes,key=lambda b:abs((b[0]+b[2])/2-.48))
                h,w=frame.shape[:2]
                crop=frame[int(b[1]*h):int(b[3]*h),int(b[0]*w):int(b[2]*w)]
                lab,_,_=measure(crop); labs.append(lab)
                samples.append(dict(seconds=seconds,lab=lab.tolist(),image=encode(crop)))
        finally: cap.release()
        if len(labs)<2: raise ValueError('Fewer than two usable station frames; cannot estimate stability')
        median=np.median(labs,axis=0)
        spread=float(max(np.linalg.norm(lab-median) for lab in labs))
        _,swatch,overlay=measure(decode(record['image']))
        prior=[r for r in history if r.get('recipe') and r['recipe']['recipe_id']==record['recipe']['recipe_id'] and r['seconds']<timestamp and r.get('color',{}).get('lab') and (r['recipe']['vial']-1)%3 != 0]
        distances=[float(np.linalg.norm(median-np.array(r['color']['lab']))) for r in prior]
        margin=max(3.,3*max([spread,*[r['color']['temporal_spread'] for r in prior]]))
        # This engineering tolerance is not a validated quality threshold.
        status='insufficient evidence' if not prior else ('appearance deviation - review' if max(distances)>margin else 'no clear appearance deviation')
        return dict(version=VERSION,status=status,lab=median.tolist(),swatch=swatch,overlay=overlay,samples=samples,temporal_spread=round(spread,3),distance=round(max(distances),3) if distances else None,threshold=round(margin,3),reference_vials=[r['recipe']['vial'] for r in prior],reason='Comparison uses earlier observed vials only; project documentation identifies second/third fills as clean, but the first can contain carryover. Tolerance is exploratory.',reference_image=comparison_image(prior[-2:]) if prior else None)
    except (ValueError,OSError,KeyError,IndexError,cv2.error) as exc:
        return dict(version=VERSION,status='insufficient evidence',reason=str(exc))

def comparison_image(records):
    tiles=[]
    for r in records:
        im=decode(r['image']); h,w=im.shape[:2]
        size=(min(180,max(1,round(w*240/h))),240)
        tile=np.full((270,180,3),245,np.uint8)
        tile[30:,:size[0]]=cv2.resize(im,size)
        cv2.putText(tile,'Earlier vial '+str(r['recipe']['vial']),(4,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(20,20,20),1)
        tiles.append(tile)
    return encode(np.hstack(tiles))

def sequence_findings(records, recipes):
    findings={}
    groups=[]
    for row in sorted(recipes,key=lambda r:r['start_s']):
        if not groups or groups[-1][-1]['recipe_id']!=row['recipe_id']: groups.append([])
        groups[-1].append(row)
    measured={r['recipe']['vial']:r for r in records if r.get('recipe') and r.get('color',{}).get('lab')}
    for gi,group in enumerate(groups):
        ids=[r['vial'] for r in group]
        available=[measured[i] for i in ids if i in measured]
        result=dict(decision='insufficient evidence',retrospective=True,vials=ids,reason='Waiting for all three measured vials; the project identifies the third vial as a clean reference, available only after it finishes.')
        if len(ids)==3 and len(available)==3:
            colors=[np.array(r['color']['lab']) for r in available]
            margin=max(3.,3*max(r['color']['temporal_spread'] for r in available))
            d12,d13,d23=[float(np.linalg.norm(colors[a]-colors[b])) for a,b in ((0,1),(0,2),(1,2))]
            result.update(distances=dict(first_second=d12,first_third=d13,second_third=d23),tolerance=margin,available_after_seconds=max(r['seconds'] for r in available))
            if max(d12,d13,d23)<=margin:
                result.update(decision='no clear appearance deviation',reason='All three appearances agree within the exploratory stability tolerance; this does not establish correctness.')
            elif d23<=margin and min(d12,d13)>margin:
                result.update(decision='appearance deviation - review',reason='First vial differs while the later two agree; the cause is unconfirmed.')
                previous=measured.get(groups[gi-1][-1]['vial']) if gi else None
                if previous:
                    ds=[float(np.linalg.norm(c-np.array(previous['color']['lab']))) for c in colors]
                    result['distance_from_previous_output']=ds
                    if ds[0]+margin<min(ds[1:]):
                        result.update(decision='possible carryover pattern',reason='First vial resembles the previous output more than the later pair does. This supports a transition pattern, not proof of residual liquid.')
            else:
                result.update(reason='The three vials vary without an agreeing later pair; cannot separate mixture differences from imaging or mixing effects.')
        for r in available:
            individual = dict(result)
            if len(ids)==3 and len(available)==3:
                reference = available[-1]
                distance = float(np.linalg.norm(np.array(r['color']['lab'])-np.array(reference['color']['lab'])))
                tolerance = max(3.,3*max(r['color']['temporal_spread'],reference['color']['temporal_spread']))
                individual['third_vial_comparison'] = dict(reference_vial=ids[-1],distance=round(distance,3),tolerance=round(tolerance,3),decision='reference only - not scored' if r['recipe']['vial']==ids[-1] else ('appearance deviation - review' if distance>tolerance else 'no clear appearance deviation'),provenance='project_desc.txt identifies the third vial as clean; retrospective only')
            findings[r['id']]=individual
    return findings

def combine(color,text,error=None):
    # Model text never assigns quality or upgrades the measured finding.
    return dict(decision=color.get('status','insufficient evidence'),visual_status='unavailable' if error or not text else 'description available',model_error=error,version=VERSION)


