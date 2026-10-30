# Cosmos liquid color verification

For the proposed video-recipe integration, see [assessment approach](APPROACH.md).
For project-specific hosting instructions that avoid the camera API's port,
see [Brev setup](BREV_SETUP.md).

Accepts a cropped vial image, an image of the source jugs, a recipe string, and
optional previous recipes/results. Returns validated JSON with a `verdict`
(`plausible`, `implausible`, or `uncertain`), observed/expected color, a concise
explanation, potential causes with supporting evidence and suggested checks,
and limitations. Residual liquid from prior mixtures is considered as a hypothesis.

## Configure inference

Run `uv sync` from `api`. Add settings to `api/.env` (see `api/example.env`):

```dotenv
BREV_API_KEY="your-key"
COSMOS_BASE_URL="http://localhost:8001/v1"
COSMOS_MODEL="nvidia/Cosmos-Reason2-8B"
```

A Brev key alone does not provide a hosted Cosmos inference endpoint. Brev keys
authenticate Brev's infrastructure/CLI. Deploy Cosmos Reason on your Brev GPU
instance and expose its OpenAI-compatible chat completion server through an SSH
tunnel or HTTPS. This client sends `COSMOS_API_KEY`, falling back to `BREV_API_KEY`,
as the inference bearer token. Your server must be configured to accept that token.
Prefer a dedicated inference token in `COSMOS_API_KEY`; keep the Brev key for Brev
automation. For an unauthenticated server behind a local SSH tunnel, use
`COSMOS_API_KEY="not-used"`. Existing environment variables override `.env` values.

For example, on a GPU instance with Cosmos-compatible vLLM installed and model
access configured, launch (Linux shell; set `COSMOS_API_KEY` on the server first):

```bash
vllm serve nvidia/Cosmos-Reason2-8B --host 127.0.0.1 --port 8000 --api-key "$COSMOS_API_KEY" --limit-mm-per-prompt '{"image":2}'
```

From your computer, forward the server's port using the SSH host from Brev:

```powershell
ssh -N -L 8001:127.0.0.1:8000 YOUR_BREV_SSH_HOST
```

The model name must match the server's served model ID. The default is Reason2-8B;
you can configure another Cosmos Reason variant. Two images per prompt must be
enabled. Remote URLs require HTTPS; localhost supports HTTP for SSH tunnels.
The client does not provision GPU instances or start servers.

References: [NVIDIA Cosmos on Brev](https://nvidia-cosmos.github.io/cosmos-cookbook/getting_started/brev/reason2/reason2_on_brev.html),
[Cosmos serving](https://github.com/nvidia-cosmos/cosmos-reason2#online-serving),
[Brev API keys](https://docs.nvidia.com/brev/guides/api-keys).

## Run

From `api`, substituting your own image paths:

```powershell
uv run python models/color_verification/verify.py --vial path/to/vial.png --jugs path/to/jugs.jpg --recipe "20 mL jug A (left, blue) + 20 mL jug B (middle, yellow)" --history models/color_verification/history.example.json --output assessment.json
```

The vial can be a crop saved by `models/jar_crop/test.py`. The history example is
illustrative; replace it with actual runs or omit `--history`. History is a JSON
list ordered **oldest to newest** with `recipe`, `good` (true, false, or null for
unknown), and optional `notes`. Include observed colors and flushing information
when available. History is supplied per request, not stored or updated automatically.

Python usage (with `api` as the working directory):

```python
from models.color_verification import verify_color

result = verify_color(
    vial_image="path/to/vial.png",
    jugs_image="path/to/jugs.jpg",
    recipe="20 mL jug A (left, blue) + 20 mL jug B (middle, yellow)",
    previous_recipes=[
        {"recipe": "40 mL jug C (right, red)", "good": True,
         "notes": "Accepted red result; shared tubing not flushed."}
    ],
)
print(result.model_dump())
```

Specify jug labels or positions and amounts/ratios. Comparable lighting and visible
liquid regions improve results. Images are orientation-corrected, converted to RGB
PNG and resized to fit 1536 pixels per side, with no automatic color correction.
JPEG, PNG, WebP, and BMP inputs are accepted (up to 20 MiB and 25 million pixels).
Images and context are sent to the configured server. The result is a qualitative
visual assessment, not a calibrated color measurement or confirmation of contamination.

Transport/output errors raise `VerificationError`; bad inputs raise `ValueError`
or `OSError`. The CLI exits 1 on errors and 0 on any valid assessment, including
`implausible` or `uncertain`; inspect `verdict` to determine the result.

Run offline tests from `api`:

```powershell
uv run python -m unittest discover -s models/color_verification -p "test_*.py" -v
```
