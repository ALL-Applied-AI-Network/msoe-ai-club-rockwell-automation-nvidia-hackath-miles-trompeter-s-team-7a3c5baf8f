"""Matched retrospective baseline comparison; cached measurements, no tuning."""
import csv
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'final_evaluation/single_frame_baseline'
FIXED_THRESHOLD=3.0  # Existing system floor, fixed before this experiment.

def summarize(rows):
    tp=sum(r['expected_carryover'] and r['flagged'] for r in rows)
    fn=sum(r['expected_carryover'] and not r['flagged'] for r in rows)
    fp=sum(not r['expected_carryover'] and r['flagged'] for r in rows)
    tn=sum(not r['expected_carryover'] and not r['flagged'] for r in rows)
    ratio=lambda a,b:a/b if b else None
    return dict(n=len(rows),tp=tp,fn=fn,fp=fp,tn=tn,accuracy=ratio(tp+tn,len(rows)),recall=ratio(tp,tp+fn),precision=ratio(tp,tp+fp),f1=ratio(2*tp,2*tp+fp+fn),false_alarm_rate=ratio(fp,fp+tn))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    recipes=json.loads((ROOT/'content/video5_vial_recipes.json').read_text())
    records={r['vial']:json.loads((ROOT/f"appearance_results/vial_{r['vial']:02}.json").read_text()) for r in recipes}
    groups=[]
    for recipe in recipes:
        if not groups or groups[-1][-1]['recipe_id']!=recipe['recipe_id']: groups.append([])
        groups[-1].append(recipe)
    assert len(groups)==10 and all(len(g)==3 for g in groups)
    predictions=[]
    for group_index,group in enumerate(groups):
        reference=records[group[-1]['vial']]
        for position,recipe in enumerate(group[:2]):
            if group_index==0 and position==0: continue
            record=records[recipe['vial']]
            target_last=max(record['color']['samples'],key=lambda r:r['seconds'])
            reference_last=max(reference['color']['samples'],key=lambda r:r['seconds'])
            assert target_last['seconds']<=record['seconds'] and reference_last['seconds']<=reference['seconds']
            single=float(np.linalg.norm(np.array(target_last['lab'])-np.array(reference_last['lab'])))
            multi=float(np.linalg.norm(np.array(record['color']['lab'])-np.array(reference['color']['lab'])))
            adaptive=max(FIXED_THRESHOLD,3*max(record['color']['temporal_spread'],reference['color']['temporal_spread']))
            for method,distance,threshold in [('single_frame_fixed',single,FIXED_THRESHOLD),('multi_frame_fixed',multi,FIXED_THRESHOLD),('flowsight_multi_frame_adaptive',multi,adaptive)]:
                predictions.append(dict(method=method,vial=recipe['vial'],recipe=recipe['recipe_id'],reference_vial=reference['recipe']['vial'],expected_carryover=position==0,flagged=distance>threshold,color_distance=distance,threshold=threshold,target_last_frame_seconds=target_last['seconds'],reference_last_frame_seconds=reference_last['seconds']))
    methods=list(dict.fromkeys(r['method'] for r in predictions))
    metrics={m:summarize([r for r in predictions if r['method']==m]) for m in methods}
    original=json.loads((ROOT/'final_evaluation/metrics.json').read_text())['retrospective_third_vial']
    assert all(metrics[methods[-1]][key]==original[key] for key in ('n','tp','fn','fp','tn')),'Current method no longer reproduces the prior result'
    with (OUT/'predictions.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(predictions[0]));writer.writeheader();writer.writerows(predictions)
    (OUT/'metrics.json').write_text(json.dumps(metrics,indent=2))
    text='''# Single-frame baseline vs FlowSight

Matched retrospective comparison: same 19 targets, same third-vial reference
identities, same fixed liquid ROI, same CIELAB distance, same project-derived
labels. Nine expected carryover cases and ten clean cases. Vial 1 is excluded
because its preceding transition is unknown; reference vials are never scored.

## Frozen protocol

- Single-frame baseline: use the latest usable saved frame for both target and
  reference; flag Euclidean CIELAB distance > 3.0. The fixed threshold is the
  existing system's tolerance floor, selected before running this experiment.
- Multi-frame fixed-threshold ablation: use saved median multi-frame colors but
  keep the same > 3.0 threshold. This isolates the multi-frame color estimate.
- Current FlowSight: same multi-frame medians with tolerance max(3.0, three times
  the larger target/reference temporal spread). This reproduces the previous run.
- Cached per-frame Lab measurements avoid extra JPEG recompression or different
  detector crops. Frame timestamps are saved in predictions.csv. No retraining,
  threshold sweep, Cosmos inference, or new real data collection was performed.

This is one straightforward baseline, not a claim to outperform an optimally
calibrated single-frame system. All methods use later third-vial references:
these are development retrospective results, NOT immediate/live/held-out plant
performance. The small sample and narrative-derived quality labels limit claims.
The result evaluates color measurement, not Cosmos explanations or fill checks.

## Results

| Method | Accuracy | Recall | Precision | F1 | False alarms | Misses |
|---|---:|---:|---:|---:|---:|---:|
'''
    pct=lambda v:'N/A' if v is None else f'{v:.1%}'
    for method,m in metrics.items():
        text+=f"| {method} | {pct(m['accuracy'])} | {pct(m['recall'])} | {pct(m['precision'])} | {pct(m['f1'])} | {m['fp']} / 10 | {m['fn']} / 9 |\n"
    text+='\n## Vials whose flags changed (baseline -> current method)\n\n'
    baseline={r['vial']:r for r in predictions if r['method']==methods[0]}
    current={r['vial']:r for r in predictions if r['method']==methods[-1]}
    changes=[v for v in baseline if baseline[v]['flagged']!=current[v]['flagged']]
    for v in changes:
        text+=f"- Vial {v}: {baseline[v]['flagged']} -> {current[v]['flagged']}; expected carryover = {baseline[v]['expected_carryover']}.\n"
    if not changes:text+='None.\n'
    (OUT/'REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
