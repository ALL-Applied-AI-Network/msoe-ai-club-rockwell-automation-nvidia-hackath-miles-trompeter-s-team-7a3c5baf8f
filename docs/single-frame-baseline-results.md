# Single-frame baseline vs FlowSight

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
| single_frame_fixed | 78.9% | 88.9% | 72.7% | 80.0% | 3 / 10 | 1 / 9 |
| multi_frame_fixed | 73.7% | 88.9% | 66.7% | 76.2% | 4 / 10 | 1 / 9 |
| flowsight_multi_frame_adaptive | 78.9% | 88.9% | 72.7% | 80.0% | 3 / 10 | 1 / 9 |

## Vials whose flags changed (baseline -> current method)

None.
