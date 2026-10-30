# Serving the existing Cosmos wrapper on NVIDIA Brev

These instructions have not been executed on a Brev instance for this project.
The local camera backend stays on port 8000; inference uses local port 8001.

Existing instance: `cosmos-reasoner`, A100 80 GB PCIe, driver 565.57.01. The user
reported no `vllm` on PATH. Use this existing allocation. Reason2's documented
validated architectures are Hopper/Blackwell, so the A100 needs a smoke test.
Its memory exceeds the listed 32 GB minimum for the 8B model.

The `nvidia-smi` CUDA 12.7 field describes driver capability, not the installed
PyTorch runtime. CUDA 12.8 builds can encounter limitations on this older driver,
especially PTX compilation. If a smoke test or model startup reports an
unsupported PTX version or insufficient driver, update the instance driver via
the Brev/provider-supported path before continuing. Installing a CUDA toolkit
alone does not update the host driver. See
[CUDA compatibility limitations](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

## 1. Choose the instance and prepare the model environment

Use the [official Cosmos Reason 2 Brev walkthrough](https://nvidia-cosmos.github.io/cosmos-cookbook/getting_started/brev/reason2/reason2_on_brev.html)
to create a Launchable with the Cosmos Reason 2 repository and its linked setup
script. That walkthrough uses an H100 80 GB, a documented starting configuration
if credits allow it. Check the displayed price and available credits before
deploying. Do not provision a training cluster for this inference task.

NVIDIA lists 32 GB minimum GPU memory for Reason2-8B; context and image workload
also affect memory. A smaller allocation needs validation, not just a weight-size
calculation. See [model setup and serving requirements](https://github.com/nvidia-cosmos/cosmos-reason2#inference).
Reason2 is now in limited maintenance, with NVIDIA directing future development
toward Cosmos 3. This guide targets the model already selected by our wrapper;
model upgrades should be evaluated against the same vial examples.

Use the Brev dashboard to connect to the instance. For Windows, the documented
CLI path uses WSL; see [Brev quickstart](https://docs.nvidia.com/brev/getting-started/quickstart).
In the remote shell, verify `nvidia-smi`, activate the environment installed by
the Launchable, and verify `vllm --version`. If the setup script did not install
the environment, complete the official repository setup linked above first.
Authenticate Hugging Face with `hf auth login` (or `uvx hf auth login`) and ensure
the account can download `nvidia/Cosmos-Reason2-8B`.

## 2. Start inference on the remote machine

In the activated Linux environment, enter a dedicated inference token privately:

```bash
read -rsp 'Inference API token: ' COSMOS_API_KEY
echo
export COSMOS_API_KEY
vllm serve nvidia/Cosmos-Reason2-8B \
  --host 127.0.0.1 --port 8000 \
  --api-key "$COSMOS_API_KEY" \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image":2}' \
  --reasoning-parser qwen3
```

Wait for the server to report startup completion. Keep the remote process running
while using the application. The two-image limit matches the existing wrapper;
increase it if implementing reference-vial images in the prompt later.

## 3. Forward inference to your local computer

After `brev login` and `brev refresh`, run this locally and leave it running:

```bash
brev port-forward cosmos-reasoner --port 8001:8000
```

This is local port 8001 to remote port 8000. Use a private SSH port forward for
API calls: Brev's browser-facing shared URLs can require interactive authentication.
See [Brev connectivity](https://docs.nvidia.com/brev/cli/connectivity).
When the tunnel runs in WSL but the API runs in Windows, first check that Windows
can reach `http://localhost:8001`; localhost forwarding depends on WSL networking.
If it cannot, use an SSH tunnel in the same environment as the API, with the
connection details provided by Brev.

Set these values in local `api/.env`:

```dotenv
COSMOS_BASE_URL="http://localhost:8001/v1"
COSMOS_MODEL="nvidia/Cosmos-Reason2-8B"
COSMOS_API_KEY="the-same-dedicated-inference-token"
```

Brev account credentials, Hugging Face download credentials, and the inference
token serve different purposes. Set `COSMOS_API_KEY` explicitly; the existing
client's legacy `BREV_API_KEY` fallback is not automatic Brev-to-model access.
Do not put these tokens in frontend code or chat messages.

## 4. Verify before connecting automatic jobs

Request `GET http://localhost:8001/v1/models` with an `Authorization: Bearer ...`
header and confirm the served model ID. Then run the existing client from `api`:

```powershell
uv run python models/color_verification/verify.py --vial path/to/completed-vial.jpg --jugs path/to/tank-frame.jpg --recipe "Confirmed tank IDs, source colors and quantities here" --output assessment.json
```

The first test needs actual image paths and the confirmed tank mapping. A valid
JSON response demonstrates transport and parsing, not color-assessment accuracy.
Evaluate the output against reviewed examples before integrating automatic jobs.
Stop the GPU instance in the Brev dashboard when finished; terminating vLLM alone
does not shut down the rented machine. Check the provider's storage charges too.
