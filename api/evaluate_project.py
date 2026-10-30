"""Project-protocol evaluation: unseen recipes and separate retrospective scoring."""
import csv,json
from pathlib import Path
import cv2
import numpy as np
from inspection_context import recipe_context,fill_check
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'final_evaluation'; OUT.mkdir(exist_ok=True)
recipes=json.loads((ROOT/'content/video5_vial_recipes.json').read_text())
records={r['vial']:json.loads((ROOT/f"appearance_results/vial_{r['vial']:02}.json").read_text()) for r in recipes}
groups=[recipes[i:i+3] for i in range(0,len(recipes),3)]

def metrics(rows):
    rows=[r for r in rows if r['truth'] is not None]
    tp=sum(r['truth'] and r['flag'] for r in rows); fn=sum(r['truth'] and not r['flag'] for r in rows)
    fp=sum(not r['truth'] and r['flag'] for r in rows); tn=sum(not r['truth'] and not r['flag'] for r in rows)
    ratio=lambda a,b:round(a/b,4) if b else None
    return dict(n=len(rows),tp=tp,fn=fn,fp=fp,tn=tn,accuracy=ratio(tp+tn,len(rows)),recall=ratio(tp,tp+fn),precision=ratio(tp,tp+fp),f1=ratio(2*tp,2*tp+fp+fn),false_alarm_rate=ratio(fp,fp+tn))

def composition(row):
    x=np.array([row['tanks'].get(k,0) for k in ('100','200','400')],float)
    return x/x.sum()

predictions=[]; contexts=[]
for gi,group in enumerate(groups):
    held=group[0]['recipe_id']
    refs=[g[-1] for g in groups if g[0]['recipe_id']!=held]
    nearest=min(refs,key=lambda r:float(np.linalg.norm(composition(r)-composition(group[0]))))
    clean=group[-1]
    for position,row in enumerate(group):
        record=records[row['vial']]; color=record['color']
        truth=None if gi==0 and position==0 else position==0
        # LORO reference selection uses recipe composition only, never held-out color.
        for mode,ref in [('leave_one_recipe_out',nearest),('retrospective_third_vial',clean)]:
            if mode=='retrospective_third_vial' and position==2: continue
            rc=records[ref['vial']]['color']
            distance=float(np.linalg.norm(np.array(color['lab'])-np.array(rc['lab'])))
            tolerance=max(3.,3*max(color['temporal_spread'],rc['temporal_spread']))
            predictions.append(dict(mode=mode,vial=row['vial'],held_out_recipe=held,reference_recipe=ref['recipe_id'],reference_vial=ref['vial'],truth=truth,flag=distance>tolerance,distance=round(distance,3),tolerance=round(tolerance,3)))
        predictions.append(dict(mode='transition_schedule_only',vial=row['vial'],held_out_recipe=held,reference_recipe=None,reference_vial=None,truth=truth,flag=position==0 and gi>0,distance=None,tolerance=None))
        contexts.append(dict(vial=row['vial'],process=recipe_context(row,recipes[:row['vial']-1]),fill=fill_check(record['image'])))
with (OUT/'predictions.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(predictions[0])); writer.writeheader(); writer.writerows(predictions)
summary={mode:metrics([r for r in predictions if r['mode']==mode]) for mode in sorted({r['mode'] for r in predictions})}
(OUT/'metrics.json').write_text(json.dumps(summary,indent=2))
(OUT/'process_and_fill.json').write_text(json.dumps(contexts,indent=2))
# Metadata/time-range audit; equal FPS cannot prove synchronized clocks.
audit={}
for camera in ('vial_fill','tank_level','cap_seal'):
    path=ROOT/f'content/{camera}_video_5.mp4'
    if not path.exists(): audit[camera]=dict(status='missing'); continue
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS); count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
    failures=[]
    for seconds in (0,recipes[len(recipes)//2]['end_s'],recipes[-1]['end_s']):
        cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000); ok,frame=cap.read()
        if ok: cv2.imwrite(str(OUT/f'{camera}_{seconds:.2f}.jpg'),frame)
        else: failures.append(seconds)
    cap.release()
    audit[camera]=dict(fps=fps,frames=count,duration_seconds=count/fps if fps else None,failed_sample_times=failures,clock_offset_verified=False,drift_verified=False)
(OUT/'camera_audit.json').write_text(json.dumps(audit,indent=2))
report='''# Pre-test evaluation against project_desc.txt

Labels are derived from the project narrative, not individual measured assays:
first-after-recipe-change is expected carryover; second and third are clean.
Vial 1 is excluded from scoring because the preceding recipe/transition is unknown.
There are 9 expected carryover cases and 20 clean cases in the full 29-vial set.

## Three deliberately separate comparisons

1. Leave-one-recipe-out (29 scored targets): all three vials of the target recipe
are excluded from reference selection. Choose the other recipe's clean third
vial with closest normalized tank-volume proportions, then measure CIELAB distance.
This is a simple unseen-recipe baseline, NOT a validated physical mixture model.
No real-data parameter fitting is performed. The tolerance is the unchanged
max(3, 3*temporal spread) heuristic. Similar recipes need not have identical hues.
2. Retrospective third-vial comparison (19 scored targets): compare first/second
vials to their own recipe's third vial. The third vial is excluded from scoring
because it is the reference. This uses future evidence and is NOT LORO or an
immediate-alert result. It is a task-relevant diagnostic benchmark.
3. Transition-schedule baseline: flag first fills after known recipe changes.
Its labels and predictions use the same dataset narrative, so perfect performance
is tautological and demonstrates NO visual detection ability or generalization.

These are development results after inspecting this dataset. They are not a fresh
independent test. Accuracy is conditional on the project-derived labels. Real
in-person evaluation must remain untouched. Cosmos explanation accuracy is not
measured by these numbers. No fill-defect labels or calibrated volume measurements
are available, so fill performance is unscored.

## Training provenance: unresolved project-compliance issue

The checkpoint's args.yaml points to api/data_vial/data.yaml. The preparation
script copies/relabels api/data; its metadata identifies a Roboflow export.
Training filenames include timestamped vial_fill_20260922 frames; visual inspection
of one training image confirms real station footage. Thus the existing detector
was trained on real images, contrary to the project's digital-twin training goal.
No digital-twin assets were found in the workspace. Do not claim synthetic-only
training or a fully compliant final model. No retraining was performed. Replacing
this detector with a verified synthetic-trained checkpoint remains outstanding.

## Camera and fill limitations

camera_audit.json records metadata and reads beginning/middle/end frames. This
checks availability and time coverage, NOT physical clock synchronization. Offset
and drift remain unverified; inspect saved timestamp overlays. cap/seal is absent.
A same-time cap/seal frame would not by itself identify the same downstream vial.
The fill check is an uncalibrated visible colored-liquid surface proxy. Clear
liquid and rail-obscured menisci produce insufficient evidence, never 'empty'.
It does not measure mL, prove overflow or identify underfill reliably. Requested
volumes and equipment limits are checked separately and do not measure delivery.

## Results

'''
report+='| Mode | N | Accuracy | Recall | Precision | F1 | False alarms | Misses |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
for mode,m in summary.items():
    pct=lambda v:'N/A' if v is None else f'{100*v:.1f}%'
    report+=f"| {mode} | {m['n']} | {pct(m['accuracy'])} | {pct(m['recall'])} | {pct(m['precision'])} | {pct(m['f1'])} | {m['fp']} | {m['fn']} |\n"
(OUT/'REPORT.md').write_text(report,encoding='utf-8')
print(json.dumps(summary,indent=2))
