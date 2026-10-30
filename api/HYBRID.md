# Appearance deviation and possible carryover (active protocol)

This supersedes hybrid-v1 recipe matching. The intended recipe always remains
correct. No clean reference is assumed. No in-person evaluation data is collected
for training, reference building, or tuning.

api/appearance.py measures 2–3 frames at or before the crop timestamp, using a
fixed liquid ROI and median CIELAB. Short-term spread records measurement
variability. Online comparisons use only earlier measured same-recipe vials.
An initial vial without comparisons yields insufficient evidence.

The provisional tolerance is max(3 CIELAB units, 3 times temporal spread). This
engineering heuristic is not a validated quality threshold. All measurements
and source crops are retained. Color differences do not establish contamination.

After all three vials arrive, a separate retrospective finding compares the
sequence. Later-pair agreement plus first-vial deviation warrants review. If the
first vial also resembles the previous recipe's last measured output more than
both later vials do, it reports a possible carryover pattern. This does not prove
causation, clean later samples, or linear color mixing. Without an agreeing later
pair, evidence is insufficient. The UI identifies retrospective use of future
fills and when that evidence became available.

Cosmos describes current appearance and differences from earlier comparison
vials; it does not assign quality or override measurements. Tank context remains
in the input. No automatic pass/fail decision is made.

Run `python evaluate_appearance.py` from api to reproduce the descriptive audit.
See appearance_results/REPORT.md, measurements.csv and sequences.json. This uses
original recipes and labeled end times; it does not benchmark online detection.
Existing recipe-mismatch benchmark results are auxiliary and must not be reported
as carryover accuracy. Accuracy/precision/recall remain unknown without independent
defect labels. The offline audit does not score Cosmos explanations.

Restart the backend for the active protocol. The API still supports video-5
replay only. Old jobs retain their old prompts; use a new replay after restarting.

Validation: 24 backend tests and frontend build/lint pass. A live Cosmos check
returned a description but contradicted measured deviation; model explanations
remain unvalidated and cannot change findings. Intended color_purpose hints are
now omitted from model context to avoid leaking expected descriptions into the
observed-color answer. No accuracy claim follows from this prompt adjustment.

## Project description correction (supersedes earlier no-label assumptions)
project_desc.txt identifies second/third batch vials as clean; the third is a
reliable color reference. First-after-change vials are expected carryover cases.
Vial 1 is unscored for carryover because its preceding transition is unknown.
Immediate comparisons now exclude first-of-batch samples. Retrospective results
include a separate per-vial comparison to the third vial, which is not self-scored.
See final_evaluation/REPORT.md for separate LORO and retrospective metrics and
the real-image detector training issue. Prior descriptive findings remain archived.

## Ask this run

The frontend includes a read-only question panel. POST
`/api/assessments/{run}/chat` accepts a question and at most four prior messages.
`api/run_chat.py` builds a whitelist of text-only facts; images, saved prompts and
unvalidated prior Cosmos visual descriptions are not sent. Count/list questions
are answered directly from deduplicated run records. More general explanations
use the existing Cosmos configuration, with one chat request in flight at a time.
Each answer displays an authoritative timestamped snapshot separately from the
advisory model text. Counts do not silently update after an answer. Chat failures
preserve the run summary. Questions are not persisted; a new run resets chat.
No new image analysis, equipment control or history search is implemented.
Live smoke check confirmed inference works, but wording remains advisory; Cosmos
initially misdescribed an availability timestamp as a duration. The prompt now
explicitly defines that field. Do not treat model prose as verified facts.
