"""Frozen video-5 color references and conservative hybrid decision policy."""
import base64
import json
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
BANK=ROOT/'content/hybrid_references.json'
VERSION='hybrid-v1'

def decode(url):
    image=cv2.imdecode(np.frombuffer(base64.b64decode(url.split(',',1)[1]),np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise ValueError('Invalid vial image')
    return image

def encode(image):
    ok, buffer=cv2.imencode('.jpg',image)
    if not ok: raise ValueError('Image encoding failed')
    return 'data:image/jpeg;base64,'+base64.b64encode(buffer).decode()

def measure(image):
    h,w=image.shape[:2]
    x1,x2,y1,y2=int(w*.3),int(w*.7),int(h*.65),int(h*.9)
    roi=image[y1:y2,x1:x2]
    if roi.size<30: raise ValueError('Liquid sampling region is too small')
    lab=np.median(cv2.cvtColor(roi.astype(np.float32)/255,cv2.COLOR_BGR2LAB).reshape(-1,3),axis=0)
    bgr=np.median(roi.reshape(-1,3),axis=0).astype(int)
    overlay=image.copy(); cv2.rectangle(overlay,(x1,y1),(x2,y2),(255,180,0),1)
    return lab, '#'+''.join(f'{v:02x}' for v in bgr[::-1]), encode(overlay)

def prepare(record):
    try:
        bank=json.loads(BANK.read_text())
        # Replay identity comes from timestamp-matched recipe, never capture count.
        # Exclude its entire fold, including different-recipe calibration examples.
        vial=record['recipe'].get('vial') if record.get('source_video')=='vial_fill_video_5.mp4' else None
        fold=(vial-1)%3 if vial is not None else None
        refs=[r for r in bank['references'] if fold is None or r['fold']!=fold]
        groups={rid:[r for r in refs if r['recipe_id']==rid] for rid in range(5,15)}
        rid=record['recipe']['recipe_id']
        if rid not in groups or len(groups[rid])<2: raise ValueError('No reference for this recipe')
        centers={key:np.mean([r['lab'] for r in values],axis=0) for key,values in groups.items()}
        calibration=[]
        for key,values in groups.items():
            for r in values:
                other=np.mean([x['lab'] for x in values if x['vial']!=r['vial']],axis=0)
                calibration.append((float(np.linalg.norm(np.array(r['lab'])-other)),True))
                calibration.extend((float(np.linalg.norm(np.array(r['lab'])-center)),False) for k,center in centers.items() if k!=key)
        positive=sum(p for _,p in calibration); negative=len(calibration)-positive
        threshold=max(sorted({0.,*[d for d,_ in calibration]}),key=lambda t:sum(d<=t for d,p in calibration if p)/positive+sum(d>t for d,p in calibration if not p)/negative)
        lab,swatch,overlay=measure(decode(record['image']))
        distance=float(np.linalg.norm(lab-centers[rid]))
        selected=groups[rid]
        # Small recipe-specific sheet; target is never included.
        tiles=[]
        for r in selected:
            im=decode(r['image']); h,w=im.shape[:2]
            resized=cv2.resize(im,(max(1,round(w*240/h)),240))
            tile=np.full((270,180,3),245,np.uint8)
            if resized.shape[1]>180: resized=cv2.resize(resized,(180,240))
            tile[30:270,:resized.shape[1]]=resized
            cv2.putText(tile,'Reference '+str(r['vial']),(5,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(20,20,20),1)
            tiles.append(tile)
        return dict(version=VERSION,status='match' if distance<=threshold else 'mismatch',distance=round(distance,3),threshold=round(threshold,3),lab=lab.tolist(),swatch=swatch,overlay=overlay,reference_vials=[r['vial'] for r in selected],excluded_fold=fold,reference_image=encode(np.hstack(tiles)),provenance='Video 5 recipe-labeled references; quality unverified')
    except (ValueError,KeyError,OSError,IndexError,cv2.error) as exc:
        return dict(version=VERSION,status='unavailable',reason=str(exc))

def target_context(record):
    """Keep target and synchronized tank frame within one model image slot."""
    target=decode(record['image']); tank=decode(record['tank_image'])
    canvas=np.full((390,720,3),245,np.uint8)
    for image,x,width,label in ((target,0,240,'TARGET VIAL'),(tank,240,480,'TANK FRAME')):
        h,w=image.shape[:2]; scale=min(width/w,350/h)
        resized=cv2.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
        canvas[35:35+resized.shape[0],x:x+resized.shape[1]]=resized
        cv2.putText(canvas,label,(x+5,20),cv2.FONT_HERSHEY_SIMPLEX,.5,(20,20,20),1)
    return encode(canvas)

def combine(color, text, error=None):
    first=(text or '').splitlines()[0].strip().upper() if text else ''
    visual=first if first in ('MATCH','MISMATCH','UNCERTAIN') else 'UNAVAILABLE'
    if color.get('status')=='mismatch' or visual=='MISMATCH': decision='review needed'
    elif color.get('status')=='match' and visual=='MATCH' and not error: decision='consistent'
    else: decision='insufficient evidence'
    return dict(decision=decision,visual_status=visual.lower(),color_status=color.get('status','unavailable'),model_error=error,version=VERSION)

def build():
    rows=json.loads((ROOT/'labels_5/video5_vial_recipes (1).json').read_text())
    refs=[]
    for r in rows:
        image=cv2.imread(str(ROOT/f"benchmark_results/vial_{r['vial']:02}.jpg"))
        if image is None: raise ValueError('Run benchmark crop extraction first')
        lab,_,_=measure(image)
        refs.append(dict(vial=r['vial'],fold=(r['vial']-1)%3,recipe_id=r['recipe_id'],lab=lab.tolist(),image=encode(image)))
    BANK.write_text(json.dumps(dict(version=VERSION,source='video5; existing development data only',roi=[.3,.65,.7,.9],references=refs)))
    print('Frozen 30 existing reference crops:',BANK)

if __name__=='__main__': build()

