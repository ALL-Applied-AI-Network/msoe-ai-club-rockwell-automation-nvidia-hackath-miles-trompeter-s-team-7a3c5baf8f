"""All 30 video-5 predictions; 29 scored with documented-clean peer references."""
import csv
import json
from pathlib import Path
import numpy as np
from evaluate_single_frame import summarize

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'final_evaluation/all_vials'; OUT.mkdir(parents=True,exist_ok=True)
recipes=json.loads((ROOT/'content/video5_vial_recipes.json').read_text())
records={r['vial']:json.loads((ROOT/f"appearance_results/vial_{r['vial']:02}.json").read_text()) for r in recipes}
groups=[]
for row in recipes:
    if not groups or groups[-1][-1]['recipe_id']!=row['recipe_id']:groups.append([])
    groups[-1].append(row)
assert len(groups)==10 and all(len(g)==3 for g in groups)
rows=[]
for gi,group in enumerate(groups):
    for position,target in enumerate(group):
        reference=group[1] if position==2 else group[2]
        assert reference['vial']!=target['vial']
        a=records[target['vial']]['color']; b=records[reference['vial']]['color']
        single=float(np.linalg.norm(np.array(max(a['samples'],key=lambda s:s['seconds'])['lab'])-np.array(max(b['samples'],key=lambda s:s['seconds'])['lab'])))
        multi=float(np.linalg.norm(np.array(a['lab'])-np.array(b['lab'])))
        tolerance=max(3.,3*max(a['temporal_spread'],b['temporal_spread']))
        truth=None if gi==0 and position==0 else position==0
        for method,distance,threshold in [('single_frame_fixed',single,3.),('multi_frame_fixed',multi,3.),('flowsight_multi_frame_adaptive',multi,tolerance)]:
            rows.append(dict(method=method,vial=target['vial'],recipe=target['recipe_id'],reference_vial=reference['vial'],expected_carryover=truth,scored=truth is not None,flagged=distance>threshold,distance=distance,threshold=threshold))
methods=list(dict.fromkeys(r['method'] for r in rows))
metrics={method:summarize([r for r in rows if r['method']==method and r['scored']]) for method in methods}
for method in methods:
    subset=[r for r in rows if r['method']==method]
    assert len(subset)==30 and len({r['vial'] for r in subset})==30
    assert sum(r['scored'] for r in subset)==29
    assert sum(r['expected_carryover'] is True for r in subset)==9
    assert sum(r['expected_carryover'] is False for r in subset)==20
# The original 19 target/reference pairs must retain identical predictions.
prior=list(csv.DictReader((ROOT/'final_evaluation/single_frame_baseline/predictions.csv').read_text().splitlines()))
for old in prior:
    current=next(r for r in rows if r['method']==old['method'] and r['vial']==int(old['vial']))
    assert current['flagged']==(old['flagged']=='True') and current['reference_vial']==int(old['reference_vial'])
with (OUT/'predictions.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(OUT/'metrics.json').write_text(json.dumps(metrics,indent=2))
text='''# All-vial video-5 comparison

30 vials evaluated; 29 scored. The first vial has unknown preceding transition
and no independently established outcome, so its prediction is exported but is
excluded from the confusion matrix. Labels for the other 29 follow project_desc.txt:
9 first-after-change carryover cases, 20 clean second/third cases.

## Protocol change from the original 19-vial result

First and second vials still use their batch's documented-clean third vial.
Third vials now use the documented-clean second vial, NEVER themselves. All
methods use the same target/reference identities, ROI, cached measurements and
unchanged thresholds. Single-frame threshold = 3 CIELAB units; current FlowSight
threshold = max(3, three times temporal spread). No retraining, tuning, new model
calls or collection. The original 19 predictions are checked to remain unchanged.

This evaluates more target vials, but does NOT add independent batches or data.
The second/third comparisons are reciprocal: their distances and symmetric
thresholds are identical, so their decisions are correlated. Do not interpret
29 as 29 independent experiments or claim stronger generalization. Different
class balance can change accuracy even without improved detection.

This is a development clean-peer comparison and is retrospective overall.
Third-vial comparisons use earlier clean peers; first/second comparisons require
future third fills. It is not immediate, leave-one-recipe-out, or independent
plant evaluation. It scores measured color findings, not Cosmos explanations or
fill defects. These results do not silently change the application's reference-only
status for third vials; this is a separate evaluation protocol.

## Results

| Method | Scored | Accuracy | Recall | Precision | F1 | False alarms | Misses |
|---|---:|---:|---:|---:|---:|---:|---:|
'''
for method,m in metrics.items():
    text+=f"| {method} | {m['n']} | {m['accuracy']:.1%} | {m['recall']:.1%} | {m['precision']:.1%} | {m['f1']:.1%} | {m['fp']}/20 | {m['fn']}/9 |\n"
(OUT/'REPORT.md').write_text(text,encoding='utf-8')
(ROOT.parent/'docs/all-vials-evaluation.md').write_text(text,encoding='utf-8')
print(json.dumps(metrics,indent=2))
