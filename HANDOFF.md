# Codex handoff — October 29–30, 2026

## Goal and current status

The user accepted tonight's working demo and wants to improve its accuracy next.
The intended workflow is: input video → completed-vial crop → matching recipe +
tank image → Cosmos text saying whether the vial looks good and, if not, what
might have gone wrong. Preserve an **Uncertain** outcome and distinguish transport
errors from quality judgments.

The workflow has been exercised end-to-end on the first vial in video 5. The
model's judgments are **not validated**: it has misidentified source colors,
contradicted itself, and claimed dispensing ratios/order were correct without
visual evidence. Do not describe pipeline success as proof of assessment accuracy.

## What was accomplished

- Recovered the Brev setup after the user's Windows/WSL restart.
- Located the existing remote virtual environment, `~/cosmos-serving`.
  It is itself the environment, not a project containing another `.venv`.
- Confirmed vLLM 0.11.0, a working PyTorch GPU operation, and Hugging Face login.
- Started `nvidia/Cosmos-Reason2-8B` on the existing `cosmos-reasoner` instance.
- Resolved GPU memory exhaustion caused by a second vLLM server already running
  in another Brev terminal. Reuse the existing allocation; do not launch duplicates.
- Established a **local WSL** SSH tunnel and verified Windows could reach it.
  Authenticated `/v1/models` and a small text completion both returned HTTP 200.
- Tried the older structured color-verification client on `api/samples`.
  Responses omitted required JSON fields or failed to finish; the client rejected
  them correctly. A schema-constrained retry also did not produce an accepted result.
- Implemented a separate plain-text demo assessment service in `api/assessments.py`.
  It queues every completed crop, matches timestamps to recipes, sends both images,
  and saves inputs, prompt, model, and output locally.
- Connected completion events in `api/main.py` to the background worker, so model
  calls do not hold the camera-analysis lock. All completions in a batch are queued.
- Added a per-replay identifier to `CompletionTracker` for deduplication/isolation.
- Added UI assessment history with queued/running/completed/error states and retries.
- Stopped automatic video looping to avoid continuously repeating inference.
- Added regression tests and updated `api/README.md`; ignored generated assessment files.

Validation performed:

- `python -m unittest test_assessments test_replay`: **15 tests passed**.
- Frontend `bun run build` and `bun run lint`: **passed**, final lint clean.
- Actual video test processed the first 32 seconds through the detector, captured
  vial 1 around 28 seconds, matched recipe 5, and obtained/saved a Cosmos answer.
- A saved smoke-test artifact is
  `api/assessment_runs/62ce370fc555434981cb1f03a2cd50d6-1.json` if still present.
  Its answer was regenerated during prompt experimentation. It is not ground truth.
- No browser-driven UI interaction test was performed in this session.

## Startup: four separate running components

Workspace on Windows:

```text
C:\git\ai_club\msoe-ai-club-rockwell-automation-nvidia-hackath-miles-trompeter-s-team-7a3c5baf8f
```

| Component | Where it runs | Port |
| --- | --- | --- |
| Cosmos/vLLM | Remote Brev instance | Remote localhost 8000 |
| SSH tunnel | Local WSL on the laptop | Local 8001 → remote 8000 |
| FastAPI camera/assessment backend | Windows, project `api` | Local 8000 |
| React/Vite frontend | Windows, project `client` | Use the URL Vite prints, normally 5173 |

Keep all four running during the demo. Local port 8001 avoids colliding with the
camera API on local port 8000. Never put model credentials in frontend code.

### 1. Remote Brev model server

Use the existing instance **`cosmos-reasoner`**. It has an A100 80 GB PCIe,
driver 565.57.01; `nvidia-smi` reports CUDA capability 12.7. This is not the
installed PyTorch runtime version. The model did start and serve requests on this
configuration, so do not reinstall/upgrade it without a concrete reason.

Start the instance in Brev if stopped. Open its browser terminal, or connect from
local WSL with `brev shell cosmos-reasoner`. The remote prompt previously looked
like `ubuntu@brev-3ivy9l4g8`.

In the **remote Brev terminal**:

```bash
source ~/cosmos-serving/bin/activate
vllm --version
nvidia-smi
```

If `nvidia-smi` shows an existing `VLLM::EngineCore` consuming substantial memory,
find the terminal already running the server. Do not start another copy. To restart
the known server, press Ctrl+C in that terminal and confirm memory is released.
An earlier duplicate launch failed with only 18.31 GiB free because the old engine
held roughly 60 GiB.

Set the inference password privately, then launch:

```bash
read -rsp 'Inference API password: ' COSMOS_API_KEY
echo
export COSMOS_API_KEY
vllm serve nvidia/Cosmos-Reason2-8B \
  --host 127.0.0.1 \
  --port 8000 \
  --api-key "$COSMOS_API_KEY" \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image":2}' \
  --reasoning-parser qwen3
```

Wait for **`Application startup complete.`** Leave this terminal running.
Activation and environment variables are per-terminal. If `vllm` is not found,
activate `~/cosmos-serving/bin/activate` in that same terminal.

Hugging Face authentication was already working. If downloads later fail, check
`hf auth whoami` in the environment and use `hf auth login` if necessary.
Brev login, Hugging Face login, and the custom inference password are different
credentials serving different purposes.

vLLM 0.11.0 prints the `api_key` argument in startup logs. One password was shared
in chat and the user was told to replace it. Do not reproduce credentials in the
handoff or logs; redact that field from shared output. Use the current private
password consistently on the server and in the local `.env`.

### 2. Local WSL tunnel — NOT a remote Brev shell

WSL and the Brev CLI were installed during this session. Open a **new Windows
PowerShell window**, then:

```powershell
wsl
```

Inside this **local WSL shell**:

```bash
brev --version
brev login
brev refresh
brev list
brev port-forward cosmos-reasoner --port 8001:8000
```

Login is only needed if not already authenticated. Refresh updates connection
details, especially after an instance restart. Leave the tunnel terminal running.
**Do not run `brev shell` before `brev port-forward`.** The user previously ran
the tunnel on the remote machine by mistake; Windows then received HTTP 000.
If the prompt says `ubuntu@brev-3ivy9l4g8`, that is the remote machine.

In another **Windows PowerShell** window:

```powershell
curl.exe -v --connect-timeout 5 http://127.0.0.1:8001/v1/models
```

**HTTP 401 Unauthorized is the expected connectivity result without a token.**
It proves Windows → WSL → Brev routing works. HTTP 000 means no HTTP response.
For connection failures, run `curl -v http://127.0.0.1:8001/v1/models` in a second
local WSL shell: failure in both environments points to the tunnel/server;
success in WSL only points to Windows-to-WSL forwarding.

### 3. Windows backend

In project `api/.env`, retain:

```dotenv
COSMOS_BASE_URL="http://127.0.0.1:8001/v1"
COSMOS_MODEL="nvidia/Cosmos-Reason2-8B"
COSMOS_API_KEY="the-private-password-used-by-the-running-server"
```

The new demo service requires `COSMOS_API_KEY` explicitly. It does not use the
older client's `BREV_API_KEY` fallback. Never print `.env` when inspecting setup.
Existing process environment variables take precedence over dotenv; restart the
API after credential/configuration changes.

In **Windows PowerShell**, from the repository root:

```powershell
cd api
uv sync
uv run python main.py
```

The existing environment can also run directly with
`.\.venv\Scripts\python.exe main.py`. `uv sync` is primarily for initial setup or
dependency changes. Python requirement is >=3.14 in the local API project;
the remote vLLM environment separately uses Python 3.12. Do not conflate them.

Required local assets:

- `api/content/vial_fill_video_5.mp4`
- `api/content/tank_level_video_5.mp4`
- `api/content/video5_vial_recipes.json`
- `api/samples/tank_level_20260922_170432_316717 (1).jpg`
- A trained single-class vial checkpoint under
  `api/models/jar_crop/runs/train*/weights/best.pt` (newest selected).

The backend runs detection on CPU. The API explicitly selects video 5 to preserve
alignment with its recipe file; substituting arbitrary video files is not supported yet.

### 4. Windows frontend

In another Windows terminal, from the repository root:

```powershell
cd client
bun install
bun run dev
```

Open the printed Vite URL and click **Start cameras**. Vite proxies `/api` to
`http://127.0.0.1:8000`. The first assessment queues after the first departure,
around 28 seconds of video time. Detection can lag playback; pausing cameras lets
it catch up while assessment jobs continue. Assessments appear below the cameras.

For shutdown, stop local processes/tunnel as appropriate and stop the GPU instance
in the Brev dashboard when finished to stop compute charges. Stopping vLLM alone
does not stop the rented instance. Instance/storage billing may remain distinct.

## Current implementation details and limitations

- `api/replay.py`: station/departure tracking and crop selection, UUID per replay.
- `api/main.py`: video serving, bounded frame processing, job submission, list/retry APIs.
- `api/assessments.py`: prompt, recipe matching, inference, serial background queue,
  persistence. `GET /api/assessments/{run}` and
  `POST /api/assessments/{job_id}/retry` power the UI.
- `client/src/App.tsx` and `App.css`: replay controls and assessment history.
- `api/test_assessments.py`, `api/test_replay.py`: queue, timestamp, failure, and tracker checks.
- `api/models/color_verification/verify.py`: older strict-JSON client, **not used by
  tonight's demo**. Do not confuse its schema failures with the new text path.
- `api/models/color_verification/APPROACH.md` and `BREV_SETUP.md`: prior design/setup notes.

Recipe matching uses the crop timestamp, not capture count: fill start through
fill end + 5 seconds, capped before the next fill start. Overlapping intervals and
unmatched times are rejected. Five seconds is a provisional departure grace period.
The first vial's recipe is 10 mL each from 100, 200, 400, recipe ID 5.

The current tank image is a **static sample screenshot**. The tank video displayed
in the UI is NOT used for inference. Source order 100, 200, 300, 400 left-to-right
was confirmed by the user. Actual liquid/color identities and concentrations were
not confirmed. Model observations such as clear/pink/clear/blue are tentative,
not authoritative configuration. Some later model outputs incorrectly called
sources green; do not copy these guesses into ground truth.

The last three preceding recipes are included as unreviewed context. There is no
operator approval history, and earlier model judgments are not used as known-good labels.

Plain-text outputs are checked for nonempty content and normal completion, but
their requested prefix/word count/semantic consistency is not strictly enforced.
The UI displays the full text, not a validated pass/fail classification.

Jobs are saved as JSON under git-ignored `api/assessment_runs/`, including both
images as data URLs. The queue holds up to 128 pending jobs and processes one at
a time. Queue overflow is an error with retry. History is currently in memory per
replay: browser refresh starts a new session; backend restart does not reload
old history or resume jobs, although saved files remain. Daemon worker jobs can
be interrupted by shutdown. Persistence/retention and worker robustness need follow-up.

The worktree already contained many user/session modifications and untracked assets.
No commit was made. Inspect `git status` before editing; do not reset existing work.
Some Codex sandbox runs hit access-denied errors importing installed Pillow/AnyIO
files. The same code worked with approved execution outside the sandbox; do not
assume those errors require reinstalling dependencies. A requests character-detection
dependency warning appeared, but successful inference was unaffected.

## Next steps, in priority order

### 1. Provide explicit, confirmed tank colors

Ask the user/operator for the actual contents/colors of tanks 100, 200, 300, 400,
including dilution/concentration if known. Store the mapping as editable configuration
with provenance/date, and send it with every assessment. Keep confirmed identity
separate from what the camera appears to show. Include tank positions/ROIs so the
model can map the image without guessing identities from IDs.

Do not hardcode yesterday's model guesses. Unknown concentration still prevents
precise mixture-color predictions, even with correct source color names.

### 2. Use synchronized tank screenshots

For replay, extract the tank frame at the **vial crop's timestamp**, accounting for
any measured offset between the two recordings. Verify alignment instead of assuming
both recordings started together. Save the exact frame, source filename, timestamp,
and offset with the job. Capture it when preparing the immutable job, not at inference
completion, since the queue can lag substantially.

For actual live cameras, associate frames with a shared clock and define maximum
acceptable age/skew. Missing or stale tank frames must produce a visible warning/error
or uncertain assessment. Do not silently substitute the old static screenshot.
Consider cropping tank liquid regions for readability, while preserving tank IDs.

### 3. Evaluate before trusting pass/fail

- Have an operator label representative vials as acceptable, unacceptable, or
  indeterminate. Recipe repetition does not establish correctness.
- Create accepted reference images per recipe under the same lighting/camera setup;
  keep evaluation examples separate from references used in prompts.
- Include known wrong mixtures, poor visibility/glare, incomplete mixing, and
  residual-color cases where available. Wrong-recipe pairing is useful as an
  additional consistency test, not a replacement for real defective mixtures.
- Track source-color recognition, verdict accuracy, false accepts/rejects, uncertain
  rate, explanation contradictions, inference failures, and latency/backlog.
- Check all 30 vial timestamps against the recipe list, especially departure grace,
  missed detections, rewind behavior, and multiple completions in one request.
- Persist model identifier/version, prompt/configuration version, inputs, outputs,
  and human labels for reproducible comparisons.

### 4. Improve assessment reliability

Separate source/expected appearance from target-vial observation to reduce the model
rationalizing whatever target color it sees. Compare both in a final assessment,
preferably against accepted reference vials. Keep uncertainty when evidence is weak.
Do not claim exact ratios, dispense order, contamination, or chemical correctness
from photos. Suggested causes must remain hypotheses with specific follow-up checks.

Investigate the model's color errors and instruction following with controlled image
tests before further prompt tuning. The fact that the current model/server loads is
not evidence of reliable reasoning. If returning to structured outputs, validate that
constraints actually work with this vLLM/model/reasoning-parser combination before
using parsed verdicts. Keep honest errors for malformed or truncated responses.

### 5. Harden the demo after accuracy work

Add durable history/job recovery, queue visibility, retention limits, retry state,
worker survival on disk-write failures, and API/session cleanup. Add a clear way to
configure video/recipe/tank sources as a matched set. Test the UI in a browser and
exercise tunnel failure/recovery. Consider a managed remote process (e.g. tmux/service)
so the model survives browser-terminal disconnections; current startup is foreground.

## Useful verification commands

From `api`:

```powershell
uv run python -m unittest test_assessments test_replay
```

From `client`:

```powershell
bun run build
bun run lint
```

These checks verify application behavior/build health, not the scientific accuracy
of model judgments. Run a real paired-image assessment after changes to prompts,
image selection, model/server settings, or credentials.

## Tank color configuration (October 30 follow-up)

Implemented editable `api/content/tank_colors.json`. Each new assessment snapshots
this configuration, persists it, and sends it to Cosmos alongside both existing
images. Positions use the operator-confirmed left-to-right order. Colors and
concentrations remain unknown until the operator supplies them. To confirm a color,
set `color`, `confirmed: true`, `confirmed_by`, and `confirmed_at` (ISO date);
leave unknown concentration null. Changes apply to new jobs; retries retain their
original context. The prompt separates configured identity from observed appearance
and requests Uncertain for conflicts. The tank photo is still a static reference;
synchronized frame extraction remains TODO 2. No live accuracy validation performed.

## Timestamp-matched tank frames (supersedes static-photo notes above)

New assessments now extract tank_level_video_5.mp4 at the vial crop timestamp
plus TANK_VIDEO_OFFSET_SECONDS (default 0), before queueing inference. Both JPEGs
and the source filename, requested/frame timestamps, frame index, and offset are
saved with the job. Missing/out-of-range frames produce preparation errors without
falling back to a static photo. Retries retain the original captured frame.
Zero offset assumes matching recording starts; actual alignment remains unverified.
The Cosmos instructions live in api/assessments.py in the PROMPT constant.
Restart the backend to use this change. Existing jobs retain their previous inputs.

## Confirmed source colors

Operator confirmed on 2026-10-30 that tank 100 is clear, 200 is orange, and 400
is blue, constant across all days, recipes, and vials. These are now explicit in
PROMPT and tank_colors.json. Tank 300 and concentrations remain unknown. Clear
is an appearance description, not an assertion that the liquid is water.

## Completed recipe-consistency benchmark

Implemented api/benchmark.py and api/benchmark_report.py. Results are in the
ignored api/benchmark_results/ directory, including REPORT.md, predictions.csv,
metrics.json, confusion matrices, all crops and 90 cached Cosmos responses.
30 vials, 3 folds, 30 original and 30 synthetic wrong recipe pairings. Final
color baseline: recipe accuracy 13/30, mismatches detected 21/30, original
pairings rejected 12/30. Cosmos reference-sheet evaluation: recipe accuracy 5/30,
mismatches detected 3/30, original pairings rejected 0/30. No final errors or
abstentions. This benchmark uses a dedicated reference-comparison prompt, not
the production assessment prompt. It does not measure real contamination.
ROI changed after inspection to exclude the rail; report records both results.
Two artifact audit tests verify pairing balance, fold assignments and accuracy.

## Hybrid inspection implementation

api/hybrid.py freezes existing video-5 crops in content/hybrid_references.json,
measures a fixed liquid ROI, excludes the target fold during replay, calibrates
only from remaining references, and combines independent color/Cosmos evidence.
api/assessments.py uses recipe-specific reference images plus target/tank context
within two image slots. Color mismatch or visual mismatch -> review needed;
both match -> consistent; missing/uncertain evidence -> insufficient evidence.
The frontend shows the sampled region, swatch, distance, threshold and references.
See api/HYBRID.md for protocol and limitations. In-person data is evaluation-only:
never collect it for references, train on it, or tune against its outcomes.
The current API remains video-5 replay; arbitrary live inputs are not implemented.

## Active correction: appearance / carryover, not recipe matching

The correct intended recipe must never be replaced to evaluate the actual task.
Active assessment logic is now api/appearance.py. It measures multiple past/end
frames, compares only earlier observed same-recipe vials online, and produces a
separate retrospective three-vial sequence finding once later evidence exists.
Cosmos describes appearance, not pass/fail. Old hybrid.py and recipe-mismatch
benchmarks are auxiliary historical experiments, not the active decision policy.
Descriptive audit: 30 measurable vials / 10 sequences; 3 possible carryover
patterns, 1 other deviation, 2 no-clear-deviation, 4 insufficient evidence.
These are heuristic findings, NOT ground truth. Accuracy/precision/recall unknown.
See api/appearance_results/REPORT.md and api/HYBRID.md. In-person data remains
strictly evaluation-only; no reference updates or tuning against it.

## Project-description-aligned pre-test work

Project description supplies batch quality assumptions: second/third are clean;
first after recipe change carries over. Vial 1's predecessor is unknown.
api/evaluate_project.py reports LORO and retrospective third-vial scoring
separately; see api/final_evaluation/REPORT.md. Retrospective 19 scored targets:
8 TP, 1 FN, 3 FP, 7 TN. LORO nearest-composition proxy flags every target.
These are development results conditional on narrative-derived labels.
api/inspection_context.py adds recipe constraints, transition explanation and
uncalibrated visible-fill proxy; no mL measurement or control commands.
Training audit confirmed current detector uses real station imagery from Roboflow,
not digital-twin training. Twin/cap-seal assets not found; user asked for paths.
Keep this compliance issue explicit. No retraining performed.

## Current-run CSV export

Frontend Export run CSV downloads all currently loaded assessments, including
pending/errors, in timestamp order. Immediate and retrospective evidence have
separate columns; no images/model descriptions included. Snapshot includes run ID
and UTC export time. Helpers in client/src/exportRun.ts; build/lint and 7 frontend
tests pass. Re-export after later fills finish; review filter never removes rows.

## Read-only run questions
Added backend run_chat.py and frontend RunChat.tsx. Verified counts/list responses
are computed from unique vials; open-ended questions use the configured Cosmos
model with bounded text-only snapshot/history. Snapshot facts appear separately
from advisory model prose. No images or new collection; no control commands.
6 chat unit tests and 7 frontend tests passed; build/lint clean. One live Cosmos
chat request succeeded; model explanations remain unvalidated. Restart the API.

## Single-frame baseline comparison

api/evaluate_single_frame.py evaluates the same 19 retrospective targets/reference
identities using (1) latest usable single frame, fixed distance threshold 3.0;
(2) multi-frame median, fixed threshold 3.0; (3) existing multi-frame adaptive
threshold. No sweeps or tuning. Single-frame and current FlowSight produce the
same flags on every vial: TP8 FN1 FP3 TN7, 78.9% accuracy, 88.9% recall, 72.7%
precision, 80% F1. Multi-frame fixed threshold adds one false alarm (73.7% accuracy).
There is NO demonstrated detection advantage over the single-frame baseline.
Report: docs/single-frame-baseline-results.md; raw CSV/metrics under ignored
api/final_evaluation/single_frame_baseline/. These are development retrospective
results, not independent plant evaluation or Cosmos explanation accuracy.

## Expanded all-vial development evaluation

api/evaluate_all_vials.py evaluates 30 targets with no self-reference: batch
positions 1/2 use 3; position 3 uses 2. Vial 1 is predicted but unscored because
its preceding transition/outcome is unknown. 29 scored: 8 TP, 1 FN, 6 FP, 14 TN.
Accuracy 75.9%, recall 88.9%, precision 57.1%, F1 69.6%. Single-frame baseline
remains tied. Reciprocal second/third comparisons are correlated; this is not
additional independent data or stronger generalization evidence. Original 19
predictions unchanged. This separate evaluation does not alter UI reference-only
semantics. Report docs/all-vials-evaluation.md; new PNG/SVG confusion matrices in
docs/confusion-matrix-all-vials.*. Original 19-vial report/figures remain preserved.
