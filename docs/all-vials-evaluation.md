# All-vial video-5 comparison

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
| single_frame_fixed | 29 | 75.9% | 88.9% | 57.1% | 69.6% | 6/20 | 1/9 |
| multi_frame_fixed | 29 | 69.0% | 88.9% | 50.0% | 64.0% | 8/20 | 1/9 |
| flowsight_multi_frame_adaptive | 29 | 75.9% | 88.9% | 57.1% | 69.6% | 6/20 | 1/9 |
