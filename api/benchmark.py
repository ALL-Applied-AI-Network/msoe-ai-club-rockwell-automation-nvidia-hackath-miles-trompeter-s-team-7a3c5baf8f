"""Offline video-5 recipe benchmark. Run: python benchmark.py [--cosmos]."""
import argparse
import base64
import csv
import json
import os
import re
import time
from pathlib import Path
import cv2
import numpy as np
import requests
from dotenv import load_dotenv
from assessments import capture_tank_frame

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'benchmark_results'

def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def data_url(img):
    ok, encoded = cv2.imencode('.jpg', img)
    if not ok: raise ValueError('JPEG encoding failed')
    return 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode()

def tile(img, label, width=200, height=240):
    result = np.full((height, width, 3), 245, np.uint8)
    ratio = min((width-12)/img.shape[1], (height-36)/img.shape[0])
    resized = cv2.resize(img, None, fx=ratio, fy=ratio)
    h,w = resized.shape[:2]
    result[30:30+h, (width-w)//2:(width-w)//2+w] = resized
    cv2.putText(result, label, (8,20), cv2.FONT_HERSHEY_SIMPLEX, .45, (20,20,20), 1)
    return result

def prepare(rows):
    from ultralytics import YOLO
    model = YOLO(str(max((ROOT/'models/jar_crop/runs').glob('train*/weights/best.pt'), key=lambda p:p.stat().st_mtime)))
    video = cv2.VideoCapture(str(ROOT/'content/vial_fill_video_5.mp4'))
    crops, features, manifest = {}, {}, []
    try:
        for row in rows:
            vid = row['vial']; path = OUT/f'vial_{vid:02}.jpg'
            if not path.exists():
                seconds = row['end_s'] - .25
                video.set(cv2.CAP_PROP_POS_MSEC, seconds*1000)
                ok, frame = video.read()
                if not ok: raise ValueError(f'Cannot read vial {vid}')
                boxes = model.predict(frame, conf=.45, device='cpu', verbose=False)[0].boxes.xyxyn.cpu().tolist()
                boxes = [b for b in boxes if .43 <= (b[0]+b[2])/2 <= .53]
                if not boxes: raise ValueError(f'No station vial at labeled end of vial {vid}')
                b = min(boxes, key=lambda b:abs((b[0]+b[2])/2-.48))
                h,w = frame.shape[:2]
                crop = frame[int(b[1]*h):int(b[3]*h), int(b[0]*w):int(b[2]*w)]
                cv2.imwrite(str(path), crop)
            crop = cv2.imread(str(path)); crops[vid] = crop
            h,w = crop.shape[:2]
            # Fixed interior ROI: excludes neck, edges and bottom. No test-label tuning.
            roi = crop[int(h*.65):int(h*.90), int(w*.3):int(w*.7)]
            lab = cv2.cvtColor(roi.astype(np.float32)/255, cv2.COLOR_BGR2LAB)
            features[vid] = np.median(lab.reshape(-1,3), axis=0)
            manifest.append(dict(vial=vid, recipe=row['recipe_id'], seconds=row['end_s']-.25, roi='x=30:70%,y=65:90%', crop=path.name))
    finally: video.release()
    write_csv(OUT/'manifest.csv', manifest)
    cv2.imwrite(str(OUT/'all_crops.jpg'), np.vstack([np.hstack([tile(crops[r['vial']], f"V{r['vial']} R{r['recipe_id']}") for r in rows[i:i+6]]) for i in range(0,30,6)]))
    return crops, features

def metrics(rows):
    result = {}
    for method in sorted({r['method'] for r in rows}):
        subset = [r for r in rows if r['method']==method]
        recognition = [r for r in subset if r['task']=='recognition']
        binary = [r for r in subset if r['task']=='consistency']
        pos = [r for r in binary if r['truth']=='mismatch']; neg = [r for r in binary if r['truth']=='match']
        rate = lambda n,d: round(n/d,4) if d else None
        scores=[]
        for label in range(5,15):
            tp=sum(r['prediction']==str(label) and r['truth']==str(label) for r in recognition)
            fp=sum(r['prediction']==str(label) and r['truth']!=str(label) for r in recognition)
            fn=sum(r['prediction']!=str(label) and r['truth']==str(label) for r in recognition)
            scores.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
        result[method] = dict(recognition_n=len(recognition), recognition_accuracy=rate(sum(r['prediction']==r['truth'] for r in recognition),len(recognition)), macro_f1=round(sum(scores)/10,4), consistency_n=len(binary), mismatch_recall=rate(sum(r['prediction']=='mismatch' for r in pos),len(pos)), false_accept_rate=rate(sum(r['prediction']=='match' for r in pos),len(pos)), false_reject_rate=rate(sum(r['prediction']=='mismatch' for r in neg),len(neg)), uncertain_rate=rate(sum(r['prediction']=='uncertain' for r in binary),len(binary)), decision_coverage=rate(sum(r['prediction'] in ('match','mismatch') for r in binary),len(binary)), errors=sum(r['prediction']=='error' for r in subset), mean_seconds=round(sum(r['seconds'] for r in subset)/len(subset),3))
    return result

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--cosmos', action='store_true'); args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    rows=json.loads((ROOT/'labels_5/video5_vial_recipes (1).json').read_text())
    crops, features=prepare(rows)
    groups={rid:[r for r in rows if r['recipe_id']==rid] for rid in range(5,15)}
    predictions=[]
    load_dotenv(ROOT/'.env', override=False)
    base=os.getenv('COSMOS_BASE_URL','').rstrip('/')
    session=requests.Session(); session.headers['Authorization']='Bearer '+os.getenv('COSMOS_API_KEY','')
    model=os.getenv('COSMOS_MODEL','nvidia/Cosmos-Reason2-8B')
    if args.cosmos:
        response=session.get(base+'/models',timeout=15)
        if response.status_code!=200: raise ValueError(f'Cosmos connectivity HTTP {response.status_code}')
    for fold in range(3):
        refs={rid:[r for i,r in enumerate(group) if i!=fold] for rid,group in groups.items()}
        centers={rid:np.mean([features[r['vial']] for r in group],axis=0) for rid,group in refs.items()}
        # Tune on training-only leave-one-out positives and negatives.
        distances=[]
        for rid,group in refs.items():
            for i,r in enumerate(group):
                distances.append((np.linalg.norm(features[r['vial']]-features[group[1-i]['vial']]), True))
                for other in centers:
                    if other!=rid: distances.append((np.linalg.norm(features[r['vial']]-centers[other]), False))
        candidates=sorted({0.,*[float(d) for d,_ in distances]})
        def score(t):
            return sum(d<=t for d,p in distances if p)/20 + sum(d>t for d,p in distances if not p)/180
        threshold=max(candidates,key=score)
        reference_sheet=np.vstack([np.hstack([tile(crops[r['vial']],f'Recipe {rid}') for rid in range(start,start+5) for r in refs[rid]]) for start in (5,10)])
        cv2.imwrite(str(OUT/f'references_fold_{fold}.jpg'),reference_sheet)
        for rid in groups:
            row=groups[rid][fold]; vid=row['vial']
            wrong=5+(rid-5+fold+1)%10
            for task,supplied,truth in [('recognition',None,str(rid)),('consistency',rid,'match'),('consistency',wrong,'mismatch')]:
                start=time.perf_counter()
                ds={key:float(np.linalg.norm(features[vid]-center)) for key,center in centers.items()}
                pred=str(min(ds,key=ds.get)) if task=='recognition' else ('match' if ds[supplied]<=threshold else 'mismatch')
                common=dict(vial=vid,fold=fold,task=task,supplied_recipe=supplied,truth=truth)
                predictions.append(dict(**common,method='color_distance',prediction=pred,seconds=time.perf_counter()-start,threshold=threshold))
                if task=='consistency': predictions.append(dict(**common,method='always_match',prediction='match',seconds=0.,threshold=''))
                if args.cosmos:
                    path=OUT/f'cosmos_{vid}_{task}_{supplied}.json'
                    if path.exists(): saved=json.loads(path.read_text())
                    else:
                        tank=capture_tank_frame(row['end_s']-.25)
                        tank_img=cv2.imdecode(np.frombuffer(base64.b64decode(tank['tank_image'].split(',')[1]),np.uint8),cv2.IMREAD_COLOR)
                        target=np.hstack([tile(crops[vid],'TARGET VIAL',400,400),tile(tank_img,'TANK FRAME',600,400)])
                        prompt='Image 1 contains two training reference vials per recipe (labels are recipe IDs). These are dataset-labeled examples, not verified chemically correct samples. Image 2 contains the held-out target vial and tank frame. Tanks left to right: 100 clear, 200 orange, 300 unknown, 400 blue. Concentrations unknown. Compare liquid appearance, allowing glare. Do not infer exact quantities or chemical purity. '
                        prompt+=('Choose the closest reference recipe for the target. Reply only with one integer from 5 through 14, or uncertain.' if task=='recognition' else f'Does the target visually match recipe {supplied}? Reply only match, mismatch, or uncertain.')
                        payload=dict(model=model,messages=[dict(role='user',content=[dict(type='text',text=prompt),dict(type='image_url',image_url=dict(url=data_url(reference_sheet))),dict(type='image_url',image_url=dict(url=data_url(target)))])],temperature=0,max_tokens=1024,stream=False)
                        start=time.perf_counter()
                        try:
                            response=session.post(base+'/chat/completions',json=payload,timeout=(10,180))
                            if response.status_code!=200: raise ValueError(f'HTTP {response.status_code}')
                            answer=response.json(); choice=answer['choices'][0]
                            output=(choice['message'].get('content') or '').strip().lower().strip('.')
                            allowed={str(i) for i in range(5,15)}|{'uncertain'} if task=='recognition' else {'match','mismatch','uncertain'}
                            prediction=output if choice.get('finish_reason')=='stop' and output in allowed else 'error'
                            saved=dict(prediction=prediction,response=answer,seconds=time.perf_counter()-start,prompt=prompt,model=model)
                        except Exception as exc: saved=dict(prediction='error',error=type(exc).__name__,seconds=time.perf_counter()-start,prompt=prompt,model=model)
                        path.write_text(json.dumps(saved,indent=2))
                    # Accept the unambiguous 'Recipe N' format without another inference call.
                    if task=='recognition' and 'response' in saved:
                        choice=saved['response']['choices'][0]
                        match=re.fullmatch(r'(?:recipe\s+)?(5|6|7|8|9|10|11|12|13|14)[.]?', (choice['message'].get('content') or '').strip().lower())
                        if match and choice.get('finish_reason')=='stop': saved['prediction']=match.group(1)
                    predictions.append(dict(**common,method='cosmos',prediction=saved['prediction'],seconds=saved['seconds'],threshold=''))
                    print(f"Vial {vid} {task} {supplied}: {saved['prediction']}",flush=True)
                write_csv(OUT/'predictions.csv',predictions)
                (OUT/'metrics.json').write_text(json.dumps(metrics(predictions),indent=2))
    print(json.dumps(metrics(predictions),indent=2),flush=True)

if __name__=='__main__': main()


