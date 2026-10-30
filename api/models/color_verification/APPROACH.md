# Recipe-aware color assessment: proposed next stage

This is an implementation plan, not a claim that Cosmos has been deployed or
validated on these vials. The existing `verify.py` is a starting client; the replay
API does not yet call it.

## Confirmed camera context

The user confirmed that the source tanks appear left to right as **100, 200,
300, 400**. Use this ordering when describing the tank image to Cosmos. Tank 300
is present in the image even though the video 5 recipes only use 100, 200 and 400.
The liquid identities/colors are not yet confirmed; do not infer them from IDs.

The user already has Brev credits and the instance `cosmos-reasoner`, with one
A100 80 GB PCIe, driver 565.57.01 (`nvidia-smi` reports CUDA 12.7). `vllm` was not
on the remote shell's PATH. Runtime installation and compatibility still need
validation; no model endpoint has been confirmed.

## What each part should do

1. On each completed-jar event, enqueue one immutable job containing the crop,
   video timestamp, recipe ID, and a tank frame from the same time. Keep VLM
   requests out of the camera inference lock. Retain every completion event,
   including multiple completions processed in one replay batch.
2. Match video timestamps to `content/video5_vial_recipes.json`, not to the
   detector's capture number. The file contains 30 vials and 10 recipes, each
   repeated three times. Crops occur shortly after `end_s`: for example the first
   crop is at 28.0 s while filling ends at 26.894 s. Use a validated, bounded
   departure grace interval (initially 5 s), capped before the next recipe starts;
   reject unmatched or ambiguous timestamps. Do not silently pick the nearest
   recipe from anywhere in the video.
3. Establish expected appearance from the recipe and a confirmed tank-to-liquid
   mapping. Tank IDs alone do not specify colors or dye concentrations. Treat
   `color_purpose` as an intended appearance hint, not an observed result or
   an acceptance label. Several entries have no such hint.
4. Have Cosmos describe the observed liquid color, mixing uniformity, visibility,
   and glare. Compare these observations with the expected appearance and return
   `plausible`, `implausible`, or `uncertain`, with a short evidence summary.
5. Display the recipe, expected appearance, observed appearance, verdict, and
   limitations beside the crop. Store the original images, recipe, model version,
   prompt version, and result for review. API failures remain errors, not verdicts.

## Expected and observed color

For the first version, use descriptive colors such as "pale blue, translucent"
instead of treating model-generated hex values as measurements. Cosmos is not a
spectrophotometer. A photo supports an observation of appearance under that
camera's lighting, not an exact intrinsic physical color.

For a more repeatable comparison, identify the liquid region inside the vial,
exclude the label, fixture, edges and highlights, and calculate robust color
statistics from the pixels. A swatch can represent that measured camera color.
The entire vial crop is not a valid liquid mask: averaging it includes substantial
background and hardware. Reject unusable liquid regions rather than guessing.

Build expected numerical colors from independently approved reference vials for
each recipe, under the same camera, lighting, fill volume and container geometry.
Use a color-distance method such as CIEDE2000 on comparable Lab measurements,
with thresholds fitted to accepted/rejected examples. Camera correction and
consistent exposure/white balance are necessary for stronger measurement claims.
Do not average source RGB colors by volume to predict dye mixtures.

To reduce bias, derive expected appearance without showing the target vial, and
describe the target without showing the expected answer. Compare the two in a
final assessment. The existing wrapper does these together in one request; it
does not yet implement this separation. If latency matters, start with its
qualitative verdict and explicitly evaluate how much this separation improves it.

## Evaluation before automated acceptance

Manually label the sample vials as acceptable, unacceptable, or indeterminate.
Repetition does not prove any of them are correct. Choose reference vials from
the accepted set, then evaluate on different vials. Review false accepts, false
rejects, uncertain cases, and runtime. Include poor visibility and genuinely
wrong mixtures; deliberately attaching an incorrect recipe is also a useful
consistency test, but is not a substitute for physical mixing failures.

Residual liquid, wrong tank selection, incorrect ratios and incomplete mixing
are possible explanations, not diagnoses established by color alone. Keep
operator approvals separate from the model's prior predictions in history.

## Information still needed

- Confirm the liquid/color in tanks 100, 200, 300 and 400; positions are known.
- Confirm whether the recipe notes describe intended colors and whether any
  vials are independently known to be good or faulty.
- Install and validate the inference environment on `cosmos-reasoner`.

See [BREV_SETUP.md](BREV_SETUP.md) for the deployment path.
