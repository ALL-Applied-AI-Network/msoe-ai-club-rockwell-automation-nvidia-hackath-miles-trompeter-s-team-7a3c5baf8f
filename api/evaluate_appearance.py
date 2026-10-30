"""Descriptive appearance audit on original recipes, never synthetic labels."""
import csv
import json
from pathlib import Path
from appearance import prepare, sequence_findings

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'appearance_results'
OUT.mkdir(exist_ok=True)
recipes=json.loads((ROOT/'content/video5_vial_recipes.json').read_text())
bank=json.loads((ROOT/'content/hybrid_references.json').read_text())
records=[]
for row in recipes:
    path=OUT/f"vial_{row['vial']:02}.json"
    if path.exists(): record=json.loads(path.read_text())
    else:
        image=next(r['image'] for r in bank['references'] if r['vial']==row['vial'])
        record=dict(id=f"appearance-{row['vial']}",recipe=row,image=image,seconds=row['end_s']-.25,source_video='vial_fill_video_5.mp4')
        record['color']=prepare(record,records)
        path.write_text(json.dumps(record,indent=2))
    records.append(record)
    print(row['vial'],record['color']['status'],flush=True)
findings=sequence_findings(records,recipes)
summary=[]
for record in records:
    color=record['color']; finding=findings.get(record['id'],{})
    summary.append(dict(vial=record['recipe']['vial'],recipe=record['recipe']['recipe_id'],frames=len(color.get('samples',[])),temporal_spread=color.get('temporal_spread'),earlier_vial_distance=color.get('distance'),exploratory_tolerance=color.get('threshold'),online_finding=color['status'],retrospective_finding=finding.get('decision','insufficient evidence')))
with (OUT/'measurements.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0])); writer.writeheader(); writer.writerows(summary)
(OUT/'sequences.json').write_text(json.dumps(findings,indent=2))
groups=[findings[r['id']] for r in records if r['recipe']['vial']%3==1 and r['id'] in findings]
metrics=dict(vials=len(records),measurable_vials=sum('lab' in r['color'] for r in records),sequences=len(groups),sequence_findings={label:sum(g['decision']==label for g in groups) for label in ('no clear appearance deviation','appearance deviation - review','possible carryover pattern','insufficient evidence')},ground_truth_defect_labels_available=False,accuracy=None,precision=None,recall=None)
(OUT/'descriptive_metrics.json').write_text(json.dumps(metrics,indent=2))
report='''# Appearance / possible carryover audit

All original intended recipes are retained. No wrong-recipe substitutions or
assumed clean vials are used. This is a descriptive development audit, not a
validated defect-detection benchmark. Accuracy, precision and recall are unknown.

Each vial is sampled at crop time minus 1 second, minus 0.5 seconds, and crop time.
At least two centered detections are required. The fixed interior liquid region
uses median CIELAB per frame and median across frames. Temporal spread is the
maximum distance from that median. Online comparisons use earlier measured vials
of the same recipe only. Offline crop times use supplied fill-end labels, not the
online departure detector; therefore detector timing performance is not evaluated.

An exploratory tolerance of max(3 CIELAB units, 3 times maximum temporal spread)
is used to describe differences above short-term variability. It is not a
validated perceptual or contamination limit and was not fitted to defect labels.
The factor and floor are engineering heuristics, not established accuracy claims.

Retrospective findings wait for all three vials. An agreeing later pair with a
different first vial is an appearance deviation. If that first vial is also
closer to the last measured output of the previous recipe than both later vials
by more than the tolerance, report a possible carryover pattern. This measures
resemblance, not a linear dye mixture or proven causation. Disagreement among
all three yields insufficient evidence. The first group has no prior-recipe
context. Every retrospective finding records when future evidence became available.

No appearance agreement proves correct composition. Later vials and prior outputs
are never treated as certified clean. No new in-person data is used for training,
reference collection or tuning. Do not claim accuracy/recall without independent
quality labels. Earlier benchmark_results recipe-pairing metrics are auxiliary
and are not performance estimates for this task.

Artifacts: measurements.csv, sequences.json, descriptive_metrics.json and per-vial
JSON with exact sampled crops and timestamps. Cached runs must be kept separate
when changing protocol. This development audit does not evaluate Cosmos descriptions.

## Measured counts

'''+json.dumps(metrics,indent=2)
(OUT/'REPORT.md').write_text(report)
print(json.dumps(metrics),flush=True)
