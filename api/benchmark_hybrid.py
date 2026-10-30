"""Development-only hybrid comparison on the existing fixed benchmark pairs."""
import csv
import json
from pathlib import Path
from assessments import assess, capture_tank_frame
from hybrid import prepare, combine, BANK

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'benchmark_results/hybrid_v1_tank'
OUT.mkdir(parents=True,exist_ok=True)
bank=json.loads(BANK.read_text())
recipes=json.loads((ROOT/'content/video5_vial_recipes.json').read_text())
source=list(csv.DictReader((ROOT/'benchmark_results/predictions.csv').read_text().splitlines()))
results=[]
for case in source:
    if case['method']!='color_distance' or case['task']!='consistency': continue
    vial=int(case['vial']); supplied=int(case['supplied_recipe'])
    path=OUT/f'{vial}_{supplied}.json'
    if path.exists(): result=json.loads(path.read_text())
    else:
        original=next(r for r in recipes if r['vial']==vial)
        recipe=dict(next(r for r in recipes if r['recipe_id']==supplied),vial=vial)
        record=dict(image=next(r['image'] for r in bank['references'] if r['vial']==vial),recipe=recipe,seconds=original['end_s']-.25,previous_recipes=[],source_video='vial_fill_video_5.mp4')
        record.update(capture_tank_frame(record['seconds']))
        color=prepare(record); record['color']=color
        try: text,model=assess(record); error=None
        except ValueError as exc: text=''; model=''; error=str(exc)
        result=dict(vial=vial,supplied_recipe=supplied,truth=case['truth'],color=color,text=text,model=model,error=error,hybrid=combine(color,text,error))
        path.write_text(json.dumps(result,indent=2))
    results.append(result)
    print(vial,supplied,result['hybrid']['decision'],flush=True)
summary=dict(n=len(results),wrong_pairings=30,original_pairings=30,wrong_flagged=sum(r['truth']=='mismatch' and r['hybrid']['decision']=='review needed' for r in results),wrong_accepted=sum(r['truth']=='mismatch' and r['hybrid']['decision']=='consistent' for r in results),original_flagged=sum(r['truth']=='match' and r['hybrid']['decision']=='review needed' for r in results),insufficient=sum(r['hybrid']['decision']=='insufficient evidence' for r in results),errors=sum(bool(r['error']) for r in results))
(OUT/'metrics.json').write_text(json.dumps(summary,indent=2))
with (OUT/'predictions.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['vial','supplied_recipe','truth','color_status','visual_status','decision','error'])
    writer.writeheader()
    for r in results: writer.writerow(dict(vial=r['vial'],supplied_recipe=r['supplied_recipe'],truth=r['truth'],color_status=r['color']['status'],visual_status=r['hybrid']['visual_status'],decision=r['hybrid']['decision'],error=r['error']))
print(json.dumps(summary),flush=True)

