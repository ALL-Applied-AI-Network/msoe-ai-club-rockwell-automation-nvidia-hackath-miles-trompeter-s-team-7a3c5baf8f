# CSI plant setup and agent handoff

This guide is for Miles and the agent helping on the CSI computer. Start by getting
the existing video-5 replay working, then adapt input access for the plant's
**evaluation-only** setup. Do not assume cloning this repository connects cameras.

## 1. Before leaving the current computer

**The latest work was uncommitted when this guide was written. A clone only gets
committed, pushed files.** Review and commit/push the intended changes before travel,
or bring a reviewed source snapshot. The setup agent should verify that the latest
files listed below exist. Do not assume the remote branch already contains them.

From the repository root:

```powershell
git status --short
git diff --stat
git log -1 --oneline
```

Record the commit ID after publishing the intended version. Do not indiscriminately
add ignored files or credentials. No commit/push was performed by writing this guide.

Bring these separately through an approved transfer method:

- **Required detector:** `api/models/jar_crop/runs/train/weights/best.pt`.
  `api/.gitignore` ignores `*.pt` and `runs/`; the checkpoint is NOT in a normal clone.
  Put the known-working checkpoint in that same relative path on the new machine.
  Code selects the most recently modified `train*/weights/best.pt`, so avoid
  installing several ambiguous checkpoints. Do not retrain just to start the demo.
- Cosmos inference password through a private channel, plus access to the existing
  Brev account/instance `cosmos-reasoner`. Do not paste passwords into agent chat.
- If desired, archived results from `api/final_evaluation/`, `appearance_results/`,
  and `benchmark_results/`. They are git-ignored, optional for normal replay, and
  otherwise will not travel with a clone. They may contain images/model outputs.
- Confirm the two video files arrived as actual playable files, not missing files
  or Git LFS pointers. They are tracked in the current repository.

Do not copy `.venv` or `node_modules` between computers. Recreate them from locks.
Do not replace a shared plant machine's existing configuration without coordination.

## 2. Message to give the plant agent

> Read CSI_SETUP.md, project_desc.txt and api/HYBRID.md. Get the existing video-5
> replay running first, using the transferred detector and existing remote Cosmos
> server. Preserve current work. Check dependencies, files, ports and authenticated
> inference before changing code. We can ignore digital-twin requirements for this
> setup session; do not retrain. Plant data is evaluation-only: do not collect it
> for a reference bank, train on it, tune against its outcomes, or update thresholds.
> The app is not yet a live-camera client. Identify the plant's approved input and
> recipe/timestamp interfaces, then make the smallest isolated adapter needed for
> evaluation. Do not overwrite video-5 files or assign video-5 recipes to new data.
> No PLC writes, recipe changes, or machine-control commands are authorized.
> Keep immediate predictions separate from retrospective comparisons using later
> vials. Do not report old recipe-mismatch metrics as carryover performance.

## 3. Clone and verify the checkout

Use the plant's approved account/network access for the repository:

```powershell
git clone https://github.com/ALL-Applied-AI-Network/msoe-ai-club-rockwell-automation-nvidia-hackath-miles-trompeter-s-team-7a3c5baf8f.git
cd msoe-ai-club-rockwell-automation-nvidia-hackath-miles-trompeter-s-team-7a3c5baf8f
git log -1 --oneline
git status --short
```

Compare the commit with the one recorded before travel. Required source includes:

- `api/main.py`, `replay.py`, `assessments.py`, `appearance.py`, `hybrid.py`,
  `inspection_context.py` (all are Python imports used by the current app).
- `client/src/App.tsx`, `BatchComparison.tsx`, `batchEvidence.ts` and CSS.
- `api/content/video5_vial_recipes.json`, `api/content/tank_colors.json`.
- `api/uv.lock`, `client/bun.lock`, `project_desc.txt`.

Required replay assets:

```powershell
Test-Path api/content/vial_fill_video_5.mp4
Test-Path api/content/tank_level_video_5.mp4
Test-Path api/content/video5_vial_recipes.json
Test-Path api/content/tank_colors.json
Test-Path api/models/jar_crop/runs/train/weights/best.pt
```

All should return `True`. Existing training datasets are not needed to run replay.
`content/hybrid_references.json` is an old benchmark artifact, not required by the
active appearance pipeline. Some historical tests/evaluation scripts require it;
do not regenerate or populate it using plant evaluation data.

## 4. Local dependencies

The known-working arrangement is Windows PowerShell for the API/frontend and local
WSL for the Brev tunnel. Use IT-approved installation methods. Required tools:

- Git.
- `uv`, managing the API's Python **3.14** environment.
- Bun (development used Bun 1.4.2).
- WSL with an already working Brev CLI, if using the existing Brev tunnel method.

Verify tools, then install locked dependencies:

```powershell
git --version
uv --version
bun --version
cd api
uv sync --locked
uv run python -c "import sys, cv2, torch; print(sys.version); print('OpenCV', cv2.__version__); print('Torch', torch.__version__)"
cd ../client
bun install --frozen-lockfile
bun run build
bun run lint
cd ..
```

Dependency downloads need network access. Allow time/disk space for PyTorch and
Ultralytics. Local detection explicitly runs on CPU; the CSI machine does not need
a GPU for this replay. The separate remote Cosmos server uses a GPU and its own
Python environment. Do not upgrade locks or reinstall remote vLLM as a setup shortcut.

If the plant machine is Linux, use the same `uv`/`bun` project commands; WSL is not
needed. Replace Windows-specific paths and `curl.exe` accordingly.

## 5. Understand the four processes

| Process | Where | Port |
|---|---|---|
| Cosmos/vLLM | Existing remote Brev instance | Remote loopback 8000 |
| SSH tunnel | CSI machine's local WSL | Local 8001 to remote 8000 |
| Camera/assessment API | CSI Windows computer | Local 8000 |
| Vite frontend | CSI Windows computer | URL printed by Vite, normally 5173 |

The different local inference port avoids collision with the camera API. Keep
services on loopback by default. If ports are occupied, identify the owning process
instead of killing unrelated plant services. API port changes also require updating
the proxy in `client/vite.config.ts`; inference port changes require updating `.env`.

### A. Existing remote Cosmos server

Start/reuse the **existing** `cosmos-reasoner` instance in Brev. In its remote terminal:

```bash
source ~/cosmos-serving/bin/activate
nvidia-smi
```

If a vLLM engine is already running, reuse it; do not launch a duplicate GPU server.
Only if stopped, use the known-working launch configuration:

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

Wait for `Application startup complete`. This is a **remote terminal**. Leave it
running. Existing environment: vLLM 0.11.0, remote Python 3.12, A100 80 GB.
Startup logs may print the API key; do not share unredacted logs.

### B. Tunnel on the CSI machine

In a new Windows PowerShell terminal:

```powershell
wsl
```

Then in this **local WSL shell**, not inside `brev shell`:

```bash
brev --version
brev login
brev refresh
brev list
brev port-forward cosmos-reasoner --port 8001:8000
```

Skip login if already authenticated. Leave this terminal running. A tunnel running
on Miles's laptop does not make `localhost:8001` work on the CSI computer.

In another Windows PowerShell terminal:

```powershell
curl.exe -i --connect-timeout 5 http://127.0.0.1:8001/v1/models
```

`401 Unauthorized` is expected without a token: it verifies connectivity only.
If this fails, run the equivalent curl in another local WSL terminal. Success only
in WSL points to Windows/WSL forwarding; failure in both points to tunnel/server.
If Brev/WSL is unavailable, have the agent use the plant-approved SSH/inference
connection. Do not assume there is already a local vLLM server on the CSI machine.

### C. Private local API configuration

Create/edit `api/.env` privately (it is ignored by Git):

```dotenv
COSMOS_BASE_URL="http://127.0.0.1:8001/v1"
COSMOS_MODEL="nvidia/Cosmos-Reason2-8B"
COSMOS_API_KEY="YOUR_PRIVATE_INFERENCE_PASSWORD"
TANK_VIDEO_OFFSET_SECONDS="0"
```

The actual assessment service requires `COSMOS_API_KEY`; do not rely on the older
example file's BREV_API_KEY fallback comment. Existing process environment values
override `.env`. Restart the API after changing configuration.

From `api`, test authenticated access without printing the key:

```powershell
uv run python -c "import os, requests; from dotenv import load_dotenv; load_dotenv('.env', override=False); r=requests.get(os.environ['COSMOS_BASE_URL'].rstrip('/')+'/models', headers={'Authorization':'Bearer '+os.environ['COSMOS_API_KEY']}, timeout=15); print('HTTP',r.status_code)"
```

Expect `HTTP 200`. This checks authentication, not multimodal inference. Do not
print `.env`, request headers, or the entire environment while debugging.

### D. Start backend and frontend

Terminal 1, from repository root:

```powershell
cd api
uv run python main.py
```

Terminal 2, from repository root:

```powershell
cd client
bun run dev
```

Open the URL Vite prints. The proxy already routes `/api` to local port 8000.
API docs are at `http://127.0.0.1:8000/docs`.

## 6. Replay smoke test before touching plant inputs

1. Click **Start cameras**. Both recordings should advance together.
2. The first completed crop normally appears around 28 seconds. CPU detection may
   lag playback; pause the cameras to let processing catch up.
3. An assessment should move queued -> running -> complete. Confirm an actual
   Cosmos description arrives; HTTP 200 from `/models` alone is not enough.
4. Check the measured region, color swatch, recipe quantities, fill-check notes,
   and text error state. Green is an appearance indicator, not certified quality.
5. After three vials, inspect the batch view: previous output plus three crops,
   color distances, and explicitly retrospective third-vial comparisons. The first
   batch's preceding recipe is unknown. Review only includes uncertain batches.
6. Confirm no false claim of immediate evidence: a third-vial comparison appears
   only after that vial is measured. Reference vials are not independently scored.

History is in memory per replay. Refreshing the browser starts a new session;
restarting the API does not reload history. Jobs are persisted in the ignored
`api/assessment_runs/` directory, but there is no recovery/resume UI. Avoid repeatedly
restarting sessions during a demonstration. The videos do not automatically loop.

Optional checks, from `api`:

```powershell
uv run python -m unittest test_appearance test_assessments test_inspection_context test_replay
```

These tests need the existing video/checkpoint assets. From `client`:

```powershell
bun run build
bun run lint
bun test tests/batch-comparison.test.ts
```

Do not run every historical benchmark as a setup check: some require ignored
artifacts and some make dozens of paid remote inference calls.

## 7. Plant evaluation inputs: work still required

**The current app is hardcoded to video 5 and its recipe schedule.** It does not
connect to live cameras, a PLC, the Batch Scheduler, or arbitrary new recordings.
Do not rename plant footage to `*_video_5.mp4` to force it through this pipeline.
That would silently assign incorrect timestamps and recipes.

Before implementing an adapter, establish with plant staff:

- Is evaluation supplied as recorded files, timestamped stills, RTSP streams, or
  another read-only interface? Where are the approved paths/endpoints?
- How are the actual intended recipe, per-tank volumes, dispense order, batch
  boundaries, and fill timestamps supplied? Do not infer recipe IDs from crop count.
- Which tank colors are confirmed for this evaluation? The current constants are
  clear/orange/blue for T100/T200/T400; T300 is out of service in the supplied dataset.
- What observation/logging is permitted? No collection for training or references
  is allowed. Ask before enabling frame persistence: the existing service saves
  crop images and tank images in each assessment JSON.
- Are cap/seal frames available, and how is the same vial associated downstream?
  Same wall-clock time at two stations does not automatically identify the same vial.

Places the agent must adapt together:

| File | Current assumption to replace |
|---|---|
| `api/main.py` | Video-5 paths, replay time input, sessions and completion submissions |
| `api/assessments.py` | Video-5 recipes, timestamp matching, tank frame extraction and source identity |
| `api/appearance.py` | Reopens video 5 for past frames; fixed nozzle/ROI geometry; video-5 three-fill assumptions |
| `api/inspection_context.py` | Dataset equipment constraints and descriptive fill proxy |
| `client/src/App.tsx` | Recorded-camera playback controls and replay timing |
| `client/src/batchEvidence.ts` | Groups video-5 vial IDs into consecutive triples |
| `client/src/BatchComparison.tsx` | Explicit video-5 retrospective batch labels |

Keep the working replay as a separate mode. For live inputs, supply a bounded
past-frame buffer rather than reading future frames; pair tank frames using the
actual shared clock. Validate missing/stale frames, clock offsets and drift. Do
not silently fall back to static images or video-5 metadata. Preserve a read-only
inspection boundary: there is no authorized actuator/control integration.

Do not retrain or adjust thresholds/ROI against evaluation outcomes. Setup and
read-only connectivity checks are different from tuning on the test set. If the
new camera geometry does not support the current measurement region, report that
limitation rather than presenting unvalidated measurements as successful detection.

## 8. What the system can claim

- Active logic: multi-frame appearance measurements, earlier clean-fill comparisons,
  retrospective third-vial comparisons, recipe-history context, and a visual fill proxy.
- `project_desc.txt` identifies second/third fills as clean and first-after-change
  as expected carryover. This is dataset-provided information, not universal labels
  for all future plant runs. Vial 1 has unknown preceding context.
- Development retrospective test: 19 scored first/second vials, 8 TP / 1 FN / 3 FP /
  7 TN; 78.9% accuracy, 88.9% recall, 72.7% precision, 80% F1. This uses future clean
  third-vial references and is NOT immediate or independent plant-test performance.
- The unseen-recipe nearest-composition baseline flagged every scored vial. Do not
  present its 100% recall without its 100% false-alarm rate on clean vials.
- Cosmos has confused colors and target/reference identity. Its explanations are
  unvalidated and cannot override measured findings. A working pipeline is not
  proof of reliable reasoning.
- Visible fill checks are uncalibrated; they do not measure mL or certify overflow.
- Current detector was trained on real station imagery. Digital-twin remediation
  is explicitly out of scope for this setup visit; do not claim synthetic training.

`api/HYBRID.md` explains the current protocol. `HANDOFF.md` is chronological and
contains superseded approaches; prefer current source and the latest corrections.
Old wrong-recipe benchmarks are auxiliary experiments, not carryover accuracy.

## 9. Troubleshooting and shutdown

| Symptom | First checks |
|---|---|
| Blank/error video | Backend running; files real and readable; Vite proxy port correct |
| No checkpoint | Transfer best.pt; verify train*/weights path; do not train by default |
| Import/DLL access denied in agent sandbox | Retry through approved execution; don't immediately reinstall packages |
| Cosmos 401 | Server and local private key match; process env isn't overriding .env |
| Cosmos connection failure | Local-machine WSL tunnel, remote server, network access |
| GPU out of memory on Brev | Existing duplicate vLLM process; reuse running server |
| Yellow/pending first fill | No prior comparison or third vial yet; not necessarily a malfunction |
| Backlog grows | Pause playback; CPU detection and serial Cosmos queue need time |
| History disappears | Refresh/new replay/API restart; inspect saved JSON if permitted |
| Training script paths point to Miles's PC | Those configs are not needed for replay; do not retrain |

Stop API, Vite and local tunnel with Ctrl+C in their terminals. Coordinate with the
instance owner before stopping the shared remote server. When finished, stop the
rented GPU instance in Brev if appropriate; stopping only vLLM does not end compute
rental. Remove locally stored credentials through the plant's approved process,
and retain/delete evaluation artifacts according to their rules.

## Exporting the current run

Use **Export run CSV** beside Assessment results. It downloads the currently
loaded replay snapshot in timestamp order, including pending/error rows, recipe
quantities, immediate measurements, separate retrospective findings/reference
IDs and availability times, fill notes and processing errors. It includes neither
images nor Cosmos descriptions. Export again after all fills/queued assessments
finish for the final snapshot. Review-only filtering does not exclude export rows.
The backend still persists images in assessment JSON; CSV export does not change
that storage behavior or the plant's data-handling requirements.

## Operator questions

The new `api/run_chat.py` and `client/src/RunChat.tsx` files must be included in the
checkout. Restart the API after deploying them. Ask this run uses the same Cosmos
credentials/tunnel as assessments. Suggested count questions use backend records
without inference; open-ended explanations use Cosmos. No extra API key is needed.
Answers are per-run snapshots, advisory text cannot control the station, and chat
resets when a new replay starts. Count cards remain available on model failure.
