"""Summarize saved benchmark predictions; no model calls."""
import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'benchmark_results'
rows = list(csv.DictReader((OUT / 'predictions.csv').read_text().splitlines()))
metrics = json.loads((OUT / 'metrics.json').read_text())
for method in ('color_distance', 'cosmos'):
    selected = [r for r in rows if r['method'] == method and r['task'] == 'recognition']
    labels = [str(i) for i in range(5, 15)] + ['uncertain', 'error']
    with (OUT / f'{method}_confusion.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['true_recipe', *labels])
        for truth in labels[:10]:
            writer.writerow([truth, *[sum(r['truth']==truth and r['prediction']==pred for r in selected) for pred in labels]])
lines = ['# Video 5 recipe-consistency benchmark', '',
         '| Method | Recipe accuracy (30) | Macro-F1 | Mismatches detected (30) | Wrong pairings accepted (30) | Original pairings rejected (30) |',
         '|---|---:|---:|---:|---:|---:|']
for method in ('always_match', 'color_distance', 'cosmos'):
    m=metrics[method]
    accuracy = 'N/A' if m['recognition_accuracy'] is None else f"{m['recognition_accuracy']:.1%}"
    lines.append(f"| {method} | {accuracy} | {m['macro_f1']:.3f} | {round(m['mismatch_recall']*30)}/30 | {round(m['false_accept_rate']*30)}/30 | {round(m['false_reject_rate']*30)}/30 |")
lines += ['', 'Uniform random recipe choice has 10% expected accuracy. Binary accuracy: always-match 50%, color baseline 65%, Cosmos 55%. Both evaluated methods issued decisions on all 60 pairs; neither abstained. No unresolved inference/format errors remained after accepting the unambiguous `Recipe N` answer format.', '',
'''## Protocol

- 30 distinct vials, 10 recipe IDs, 3 vials per recipe. Three folds hold out the first, second, or third vial of each recipe. The other two supply references. No target appears in its own references.
- Frames are sampled at labeled fill end minus 0.25 seconds and cropped with the existing vial detector. This uses oracle timing and does NOT evaluate online departure detection, missed events, or recipe matching.
- Color baseline: median floating-point CIELAB in the fixed inner liquid region (x 30–70%, y 65–90% of crop), Euclidean distance to the two-reference mean. The threshold maximizes training-only balanced accuracy using leave-one-reference-out positive distances and all wrong-recipe distances. This small training calibration is provisional.
- The initial ROI (y 45–85%) overlapped the conveyor rail. It was corrected after contact-sheet inspection; no grid search was performed. The initial baseline scored 53.3% recipe accuracy and 80% mismatch recall; the reported final geometry scores lower. This is an exploratory benchmark, not a pristine preregistered test.
- Each target gets its original recipe pairing and one deterministic wrong pairing: recipe index shifted by fold+1 modulo 10. Across folds the 30 negative pairs are balanced across recipe IDs. They are NOT 30 physical contaminated vials. Samples sharing a vial are not independent.
- Cosmos receives a labeled 20-reference contact sheet and a target/tank contact sheet, with at most two images. It chooses the closest recipe in 30 calls and judges supplied-recipe consistency in 60 separate calls. These are appearance-reference prompts, not the production assessment prompt, and do not include recipe volume tables. Results characterize this evaluation configuration, not all possible Cosmos prompts.
- The same labeled reference vials support both methods; Cosmos additionally sees a tank frame and confirmed source colors. Reference vials are not certified acceptable. Full crops can expose labels/hardware; contact-sheet compression and unverified camera alignment are limitations.
- Cosmos: nvidia/Cosmos-Reason2-8B, temperature 0, max_tokens 1024. Raw responses, exact prompts, model identifier, and call durations are saved. Mean request time was about 0.26 seconds; baseline timing only covers distance/decision calculation and excludes decoding, detector and feature extraction. Do not present these as an end-to-end speed comparison.

## Interpretation

The simple color baseline outperformed this Cosmos configuration. Cosmos strongly favored accepting pairings (57/60), missing 27/30 deliberately wrong assignments. The baseline caught more mismatches but rejected 12/30 original pairings. Several same-recipe vials visibly differ; some different recipes may be visually indistinguishable. Dataset recipe labels alone cannot resolve these cases as contamination.

These results measure correspondence to supplied recipe labels and controlled metadata mismatches. They do not establish chemical correctness, real contamination sensitivity, or generalization to another day. With only three examples per recipe, estimates are unstable. Do not use the results as automatic release criteria.

## Artifacts and rerun

- `predictions.csv`: every fold, target, supplied recipe, truth, prediction, threshold and decision/request duration.
- `manifest.csv`, `all_crops.jpg`, `vial_*.jpg`: extraction audit.
- `references_fold_*.jpg`: reference inputs.
- `cosmos_*.json`: raw model responses and prompts.
- `*_confusion.csv`, `metrics.json`: machine-readable results.

From repository root: `api/.venv/Scripts/python.exe api/benchmark.py --cosmos`, then `api/.venv/Scripts/python.exe api/benchmark_report.py`.
Existing response files are reused. For a changed prompt/model/protocol, use a fresh results directory; cached files are not automatically invalidated. Preserve the old run for comparison. Outputs are git-ignored.
''']
(OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print(OUT/'REPORT.md')


